"""Simple exact-key benchmark, total input records stated explicitly; no cloud."""

import ctypes
import json
import statistics
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))


def measure(total: int) -> dict[str, object]:
    from reconciliation_cases import plan
    from studio.contracts.reconciliation import CanonicalRecord
    from studio.reconciliation_engine import match_records
    from studio.verification import verify_result

    inputs = []
    for side in ("left", "right"):
        rows = []
        for i in range(total // 2):
            rows.append(
                CanonicalRecord(
                    id=f"{side}-{i}",
                    invalid=False,
                    quality_flags=[],
                    payload=dict(
                        platform="Shopee",
                        shop_id="SHOP-A",
                        order_id=f"{i:08d}",
                        event_date=datetime(2026, 10, 1, tzinfo=UTC),
                        currency="VND",
                        gross_amount=Decimal("12.75"),
                    ),
                    provenance=[
                        dict(
                            file_id=side,
                            source_table_id=side,
                            source_row_id=f"{side}-{i}",
                            sheet="CSV",
                            row=i + 2,
                        )
                    ],
                )
            )
        inputs.append(rows)
    started = time.perf_counter()
    result = match_records(plan(), *inputs)
    matching = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    checks = verify_result(plan(), *inputs, result)
    verification = (time.perf_counter() - started) * 1000
    assert all(c.passed for c in checks) and len(result.groups) == total // 2

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    memory = ctypes.windll.psapi.GetProcessMemoryInfo
    memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    assert memory(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return dict(
        total_input_records=total,
        rows_per_source=total // 2,
        matching_ms=matching,
        verification_ms=verification,
        peak_mib=counters.PeakWorkingSetSize / 1048576,
        exact_groups=len(result.groups),
        fuzzy_candidates=0,
        review_cases=0,
        cloud_calls=0,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(measure(int(sys.argv[1]))))
    else:
        report = []
        for size in (1000, 10000, 50000):
            runs = [
                json.loads(
                    subprocess.check_output([sys.executable, __file__, str(size)], text=True)
                )
                for _ in range(3)
            ]
            summary = dict(total_input_records=size, rows_per_source=size // 2, repetitions=3)
            for stage in ("matching_ms", "verification_ms"):
                values = [r[stage] for r in runs]
                summary[stage] = dict(
                    p50=round(statistics.median(values), 2),
                    p95=round(statistics.quantiles(values, n=20, method="inclusive")[18], 2),
                )
            summary.update(
                peak_mib=round(max(r["peak_mib"] for r in runs), 2),
                exact_groups=size // 2,
                fuzzy_candidates=0,
                review_cases=0,
                cloud_calls=0,
            )
            report.append(summary)
        (ROOT / "runtime" / "reconciliation-benchmark.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
