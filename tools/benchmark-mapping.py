"""Fixed business-labelled column benchmark. No AI, database, approvals or financial runs.

Install Valentine only in an explicitly supplied ignored trial directory. Each method
runs in a fresh bounded subprocess. Gold is read after ranking and never passed to a
matcher. Equal money/ID distributions deliberately prevent value-only semantic truth.
"""

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "tests/fixtures/mapping-business-specifications.json"
METHODS = ("existing", "rapidfuzz_profile", "valentine", "hybrid")
os.environ.setdefault("POLARS_MAX_THREADS", "2")
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(variable, "1")


def peak_memory() -> int:
    if os.name != "nt":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    value = Counters()
    value.cb = ctypes.sizeof(value)
    handle = ctypes.windll.kernel32.GetCurrentProcess
    handle.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(handle()), ctypes.byref(value), value.cb
    ):
        raise OSError("Cannot measure process peak working set")
    return int(value.PeakWorkingSetSize)


def dataset(domain, split, spec):
    """Independent literal business roles define values, not matcher predictions."""
    import polars as pl
    from studio.contracts import SchemaDefinition, SchemaField, SourceColumn
    from studio.profiling import profile_table

    variants = {"development": 1, "validation": 2, "holdout": 3}
    index = variants[split]
    source, target, gold, kinds = {}, {}, {}, {}
    schema_fields = []
    for field_id, canonical, vietnamese, unseen, data_type, role in domain["columns"]:
        header = ["", canonical, vietnamese, unseen][index]
        if data_type == "decimal":
            # All financial bases share values. Their meaning comes from the specification.
            values = [f"{'-' if i % 7 == 0 else ''}{100 + i}.{i % 100:02d}" for i in range(48)]
            if split == "validation":
                values = [value.replace(".", ",") for value in values]
        elif data_type == "date":
            values = [f"2026-11-{i % 27 + 1:02d}" for i in range(48)]
            if split == "validation":
                values = [f"{i % 27 + 1:02d}/11/2026" for i in range(48)]
        elif role == "currency":
            values = ["VND" if i % 3 else "USD" for i in range(48)]
        else:
            values = [f"{i:08d}" for i in range(48)]
        source[header] = values
        target[canonical] = values[3:] + values[:3]
        gold[header] = field_id
        kinds[field_id] = role
        schema_fields.append(SchemaField(id=field_id, name=canonical, data_type=data_type))
    for header, _, data_type in spec["negative_columns"]:
        source[header] = (
            [f"{100 + i}.{i % 100:02d}" for i in range(48)]
            if data_type == "decimal"
            else [f"2026-11-{i % 27 + 1:02d}" for i in range(48)]
            if data_type == "date"
            else [f"{i:08d}" for i in range(48)]
        )
        gold[header] = None
    order = list(source)
    random.Random(spec["protocol"]["seed"] + index).shuffle(order)
    frame = pl.DataFrame({header: source[header] for header in order})
    ids = [f"c{i}" for i in range(len(order))]
    profile = profile_table(
        frame.rename(dict(zip(order, ids, strict=True))),
        [
            SourceColumn(id=key, name=name, source_index=i)
            for i, (key, name) in enumerate(zip(ids, order, strict=True))
        ],
        domain["id"],
        "synthetic",
        "synthetic",
    )
    schema = SchemaDefinition(
        id="target",
        workspace_id="synthetic",
        revision=1,
        name=domain["id"],
        entity_kind=domain["id"],
        grain=domain["grain"],
        fields=schema_fields,
    )
    return frame, pl.DataFrame(target), profile, schema, gold, kinds


def ranks(method, frames, cutoff):
    from rapidfuzz.fuzz import ratio
    from studio.profiling import ALIASES, find_mapping_candidates, normalized_name

    frame, target, profile, schema, _, _ = frames
    exact = find_mapping_candidates(profile, schema)
    existing = {c.name: {key: 1.0 for key in exact[c.column_id]} for c in profile.columns}
    if method == "existing":
        return existing

    def normalized(value):
        return re.sub(r"[\s_-]+", " ", normalized_name(value)).strip()

    fuzzy = {}
    for column in profile.columns:
        candidates = {}
        for field in schema.fields:
            if column.identifier_candidate and field.data_type == "decimal":
                continue
            if field.data_type == "date" and not column.observations.get("date_formats"):
                continue
            if field.data_type == "decimal" and not column.observations.get("numeric_locales"):
                continue
            names = {field.name, field.id} | ALIASES.get(field.id, set())
            score = max(ratio(normalized(column.name), normalized(name)) for name in names) / 100
            if score >= cutoff / 100:
                candidates[field.id] = score
        fuzzy[column.name] = candidates
    if method == "rapidfuzz_profile":
        return fuzzy
    from valentine import valentine_match
    from valentine.algorithms import Coma

    matches = valentine_match(
        [frame, target], Coma(use_instances=True, max_n=5), instance_sample_size=48
    )
    name_to_id = {field.name: field.id for field in schema.fields}
    valentine = {column: {} for column in frame.columns}
    for pair, score in matches.items():
        if pair.source_column in valentine and pair.target_column in name_to_id:
            valentine[pair.source_column][name_to_id[pair.target_column]] = score
    if method == "valentine":
        return valentine
    return {
        column: {
            key: 1.0
            if key in existing[column]
            else (fuzzy[column].get(key, 0) + valentine[column].get(key, 0)) / 2
            for key in fuzzy[column].keys() | valentine[column].keys() | existing[column].keys()
        }
        for column in frame.columns
    }


def evaluate(method, spec, splits):
    results = []
    wall, cpu = time.perf_counter(), time.process_time()
    for split in splits:
        for domain in spec["domains"]:
            frames = dataset(domain, split, spec)
            start = time.perf_counter()
            ranked = ranks(method, frames, spec["protocol"]["rapidfuzz_cutoff"])
            elapsed = (time.perf_counter() - start) * 1000
            for header, gold in frames[4].items():
                candidates = sorted(
                    ranked.get(header, {}).items(), key=lambda item: (-item[1], item[0])
                )[:5]
                tie = len(candidates) > 1 and abs(candidates[0][1] - candidates[1][1]) < 1e-12
                chosen = candidates[0][0] if candidates and not tie else None
                results.append(
                    dict(
                        domain=domain["id"],
                        split=split,
                        header=header,
                        gold=gold,
                        predicted=chosen,
                        tied=tie,
                        candidates=candidates,
                        role=frames[5].get(gold),
                        latency_ms=elapsed,
                    )
                )
    return dict(
        method=method,
        columns=results,
        wall_seconds=time.perf_counter() - wall,
        cpu_seconds=time.process_time() - cpu,
        peak_process_bytes=peak_memory(),
    )


def summarize(records):
    expected = [record for record in records if record["gold"] is not None]
    proposed = [record for record in records if record["predicted"] is not None]
    correct = sum(record["predicted"] == record["gold"] for record in proposed)
    return dict(
        columns=len(records),
        labelled_positive=len(expected),
        proposals=len(proposed),
        correct=correct,
        f1=2 * correct / (len(proposed) + len(expected)) if proposed or expected else None,
        precision_at_1=correct / len(proposed) if proposed else None,
        recall_at_1=correct / len(expected) if expected else None,
        recall_at_3=sum(
            record["gold"] in [key for key, _ in record["candidates"][:3]] for record in expected
        )
        / len(expected)
        if expected
        else None,
        recall_at_5=sum(
            record["gold"] in [key for key, _ in record["candidates"]] for record in expected
        )
        / len(expected)
        if expected
        else None,
        false_positives=sum(record["predicted"] != record["gold"] for record in proposed),
        negative_false_proposals=sum(record["gold"] is None for record in proposed),
        missed_keys=sum(
            record["role"] == "key" and record["predicted"] != record["gold"] for record in expected
        ),
        wrong_basis=sum(
            record["role"] not in {"key", "date", "currency"}
            and record["predicted"] not in {None, record["gold"]}
            for record in expected
        ),
        abstentions=sum(record["predicted"] is None for record in records),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--method", choices=METHODS)
    parser.add_argument(
        "--split", choices=("all", "development", "validation", "holdout"), default="all"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runtime/automation-mapping-benchmark.json"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "backend"))
    if args.dependencies and args.method not in {"existing", "rapidfuzz_profile"}:
        sys.path.insert(0, str(args.dependencies.resolve()))
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    splits = spec["protocol"]["splits"] if args.split == "all" else [args.split]
    if args.method:
        print(json.dumps(evaluate(args.method, spec, splits), ensure_ascii=False))
        return
    # Explicit, local NLTK corpus for Coma. No download to user/global model caches.
    import nltk

    corpus = ROOT / "runtime/automation-nltk"
    corpus.mkdir(exist_ok=True)
    assert nltk.download("stopwords", download_dir=str(corpus), quiet=True)
    os.environ["NLTK_DATA"] = str(corpus)
    subprocesses = []
    for method in METHODS:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--method",
            method,
            "--split",
            args.split,
            "--spec",
            str(args.spec.resolve()),
        ]
        if args.dependencies:
            command += ["--dependencies", str(args.dependencies.resolve())]
        output = subprocess.run(
            command, check=True, capture_output=True, text=True, encoding="utf-8", timeout=180
        )
        subprocesses.append(json.loads(output.stdout))
    for result in subprocesses:
        grouped = defaultdict(list)
        timings = {}
        for row in result["columns"]:
            grouped[(row["split"], row["domain"])].append(row)
            timings[(row["split"], row["domain"])] = row["latency_ms"]
        result["per_domain"] = {
            f"{split}/{domain}": summarize(rows) for (split, domain), rows in grouped.items()
        }
        result["summary"] = summarize(result["columns"])
        result["latency"] = dict(
            samples=len(timings),
            p50_ms=statistics.median(timings.values()),
            p95_ms=statistics.quantiles(timings.values(), n=100, method="inclusive")[94],
        )
    report = dict(
        spec_sha256=hashlib.sha256(args.spec.read_bytes()).hexdigest(),
        protocol=spec["protocol"],
        source_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        benchmark_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        methods=subprocesses,
        trial_packages=[
            dict(name=dist.metadata["Name"], version=dist.version)
            for dist in importlib.metadata.distributions(path=[str(args.dependencies)])
        ]
        if args.dependencies
        else [],
        auto_approval_evaluation="NOT_MEASURED: candidate benchmark never calls approval APIs",
        grain_evaluation="NOT_MEASURED: no column matcher here proposes grain/timezone/coverage",
    )
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                result["method"]: dict(
                    summary=result["summary"],
                    latency=result["latency"],
                    peak_process_bytes=result["peak_process_bytes"],
                )
                for result in subprocesses
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
