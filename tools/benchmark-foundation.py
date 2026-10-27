"""Reproducible synthetic local stage benchmark; no AI or business data."""

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("POLARS_MAX_THREADS", "2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def measure(size: int) -> dict[str, object]:
    from decimal import Decimal

    import polars as pl
    from studio.config import Settings
    from studio.contracts import MappingDecision, MappingRevision, SchemaDefinition, SchemaField
    from studio.normalization import apply_transform_plan
    from studio.parsing import ParseConfig, inspect_upload, parse_to_artifacts
    from studio.profiling import profile_table, source_signature
    from studio.schema_mapping import compile_transform_plan

    with tempfile.TemporaryDirectory(prefix="studio-benchmark-") as folder:
        root = Path(folder)
        source = root / "synthetic.csv"
        source.write_text(
            "Order ID,Gross amount\n"
            + "".join(
                f"{i:08d},{'invalid' if i % 1000 == 999 else '1234.50'}\n" for i in range(size)
            ),
            encoding="utf-8",
        )
        config = Settings(_env_file=None, max_rows=100000)
        start = time.perf_counter()
        with source.open("rb") as stream:
            inspected = inspect_upload(stream, source.name, "text/csv", config)
        parsed = parse_to_artifacts(source, inspected, ParseConfig(), config)[0]
        parsed.frame = parsed.frame.with_columns(
            pl.Series("_source_row_id", [f"r{i}" for i in range(size)])
        )
        parse_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        profile = profile_table(parsed.frame, parsed.columns, "table", "workspace", "parsed")
        profile_ms = (time.perf_counter() - start) * 1000
        schema = SchemaDefinition(
            id="schema",
            workspace_id="workspace",
            name="Synthetic",
            revision=1,
            entity_kind="order",
            grain="one synthetic source row",
            fields=[
                SchemaField(id="reference_id", name="Reference", data_type="string"),
                SchemaField(
                    id="amount",
                    name="Gross",
                    data_type="decimal",
                    semantic_metric="synthetic_gross",
                    amount_basis="gross",
                    currency="VND",
                    unit="VND",
                ),
            ],
        )
        decisions = [
            MappingDecision.model_validate(
                {
                    "source_field": col,
                    "candidate_target": target,
                    "decision": "APPROVED",
                    "evidence_ids": [f"table:{col}"],
                    "grain_assumption": schema.grain,
                    "transformation_candidate": transform,
                }
            )
            for col, target, transform in [
                ("c1", "reference_id", {"op": "cast_string_preserve"}),
                ("c2", "amount", {"op": "parse_decimal", "locale": "en-US"}),
            ]
        ]
        mapping = MappingRevision(
            id="mapping",
            workspace_id="workspace",
            source_table_id="table",
            source_signature=source_signature(profile),
            schema_id="schema",
            schema_revision=1,
            business_scope="synthetic",
            revision=1,
            status="APPROVED",
            approved_by="synthetic-owner",
            decisions=decisions,
        )
        start = time.perf_counter()
        result = apply_transform_plan(
            parsed.frame,
            compile_transform_plan(mapping, schema, profile),
            "version",
            "table",
            "file",
            "CSV",
        )
        result.canonical.write_parquet(root / "canonical.parquet")
        result.errors.write_parquet(root / "errors.parquet")
        normalize_ms = (time.perf_counter() - start) * 1000
        assert result.row_count == size and result.invalid_count == size // 1000
        assert result.canonical["record_payload"].to_list()[0]["amount"] == Decimal("1234.50")
        peak_mib = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t)
                    for name in [
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    ]
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
            memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            memory_info.restype = wintypes.BOOL
            if not memory_info(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                raise RuntimeError("Windows peak memory measurement failed")
            peak_mib = counters.PeakWorkingSetSize / 1048576
        return {
            "rows": size,
            "parse_ms": parse_ms,
            "profile_ms": profile_ms,
            "normalize_write_ms": normalize_ms,
            "peak_process_mib": peak_mib,
            "ai_calls": 0,
        }


def main() -> None:
    if len(sys.argv) == 2:
        print(json.dumps(measure(int(sys.argv[1]))))
        return
    report = []
    for size in [1000, 10000, 50000]:
        runs = [
            json.loads(subprocess.check_output([sys.executable, __file__, str(size)], text=True))
            for _ in range(3)
        ]
        item = {"rows": size, "repetitions": 3, "polars_threads": 2}
        for stage in ["parse_ms", "profile_ms", "normalize_write_ms"]:
            values = [run[stage] for run in runs]
            item[stage] = {
                "p50": round(statistics.median(values), 2),
                "p95_observed": round(
                    statistics.quantiles(values, n=20, method="inclusive")[18], 2
                ),
            }
        measured_peaks = [
            run["peak_process_mib"] for run in runs if run["peak_process_mib"] is not None
        ]
        item["peak_process_mib"] = round(max(measured_peaks), 2) if measured_peaks else None
        report.append(item)
    output = Path("runtime/benchmarks.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
