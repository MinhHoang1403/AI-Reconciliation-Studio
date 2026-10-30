"""Đo typed evidence query 1k/10k/50k trên Parquet tổng hợp; không gọi AI/ghi metadata."""

import gc
import json
import resource
import statistics
import tempfile
import time
from pathlib import Path

import polars as pl
from sqlalchemy import select, text
from studio.access import Actor
from studio.assistant_tools import build_fact_set, exact_group, read_tool
from studio.config import settings
from studio.contracts.assistant import AssistantContext, ToolRequest
from studio.database import MembershipRow, ProjectRow, RunRow, SessionFactory
from studio.storage import checksum


def elapsed(task):
    started = time.perf_counter()
    result = task()
    return (time.perf_counter() - started) * 1000, result


def summary(values):
    return dict(
        samples=len(values),
        p50_ms=round(statistics.median(values), 3),
        p95_observed_ms=round(statistics.quantiles(values, n=20, method="inclusive")[18], 3),
    )


def main():
    report = dict(synthetic_parquet=[], cloud_requests=0, cost_estimate=None)
    with tempfile.TemporaryDirectory(prefix="studio-assistant-bench-") as folder:
        previous = settings.storage_root
        settings.storage_root = Path(folder)
        try:
            for size in (1000, 10000, 50000):
                rows = []
                for i in range(size):
                    group = dict(
                        id=f"group-{i:08d}",
                        key=[f"{i:08d}"],
                        linkage_state="LINKED",
                        comparison_state="AMOUNT_MISMATCH",
                        comparisons=[
                            dict(
                                metric_id="synthetic_gross",
                                currency="VND",
                                unit="VND",
                                left_amount="12.75",
                                right_amount="10.00",
                                delta="2.75",
                                absolute_variance="2.75",
                                tolerance="0",
                                state="AMOUNT_MISMATCH",
                            )
                        ],
                        members=[
                            dict(
                                side=side,
                                canonical_id=side,
                                record_id=f"{side}-{i}",
                                evidence=[
                                    dict(
                                        file_id=side,
                                        source_table_id=side,
                                        source_row_id=f"{side}-{i}",
                                        sheet="CSV",
                                        row=i + 2,
                                    )
                                ],
                            )
                            for side in ("left", "right")
                        ],
                        exception_types=["AMOUNT_MISMATCH"],
                        candidates=[],
                        algorithm="synthetic-exact",
                    )
                    rows.append(dict(group_id=group["id"], group_json=json.dumps(group)))
                path = Path(folder) / "matches.parquet"
                write_ms, _ = elapsed(
                    lambda rows=rows, path=path: pl.DataFrame(rows).write_parquet(path)
                )
                del rows
                gc.collect()
                run = RunRow(
                    id="synthetic",
                    workspace_id="synthetic",
                    project_id="synthetic",
                    result_key=path.name,
                    result_sha256=checksum(path),
                )
                timings = []
                for _ in range(10):
                    duration, found = elapsed(
                        lambda run=run, size=size: exact_group(run, f"group-{size - 1:08d}")
                    )
                    assert str(found.comparisons[0].delta) == "2.75" and len(found.members) == 2
                    timings.append(duration)
                report["synthetic_parquet"].append(
                    dict(
                        groups=size,
                        source_records=size * 2,
                        artifact_bytes=path.stat().st_size,
                        write_ms=round(write_ms, 3),
                        evidence=summary(timings),
                        process_peak_mib=round(
                            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
                        ),
                    )
                )
        finally:
            settings.storage_root = previous
    with SessionFactory() as db:
        member = db.scalar(
            select(MembershipRow)
            .where(MembershipRow.role == "owner")
            .order_by(MembershipRow.workspace_id, MembershipRow.actor_id)
            .limit(1)
        )
        assert member
        actor = Actor(member.actor_id, member.workspace_id, member.role)
        # Explicitly synthetic project only; do not expose or benchmark user data.
        run = db.scalar(
            select(RunRow)
            .join(ProjectRow, RunRow.project_id == ProjectRow.id)
            .where(
                RunRow.workspace_id == actor.workspace_id,
                ProjectRow.business_scope == "synthetic-reconciliation-acceptance",
                RunRow.status.in_(["VERIFIED", "PARTIAL_VERIFIED"]),
            )
            .order_by(RunRow.id)
            .limit(1)
        )
        if run:
            context = AssistantContext(project_id=run.project_id, run_id=run.id)
            timings = []
            fact_times = []
            for _ in range(10):
                duration, _ = elapsed(
                    lambda: read_tool(
                        db, actor, ToolRequest(name="get_run_summary", context=context)
                    )
                )
                timings.append(duration)
                duration, _ = elapsed(lambda: build_fact_set(db, actor, context))
                fact_times.append(duration)
            report["actual_synthetic_run_tool"] = summary(timings)
            report["actual_synthetic_fact_set"] = summary(fact_times)
            plan = db.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM reconciliation_runs "
                    "WHERE id=:id AND project_id=:project AND workspace_id=:workspace"
                ),
                dict(id=run.id, project=run.project_id, workspace=actor.workspace_id),
            ).scalar_one()[0]
            report["database_query"] = dict(
                total_cost=plan["Plan"]["Total Cost"],
                actual_execution_ms=plan["Execution Time"],
                actual_rows=plan["Plan"]["Actual Rows"],
                shared_hit_blocks=plan["Plan"]["Shared Hit Blocks"],
            )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
