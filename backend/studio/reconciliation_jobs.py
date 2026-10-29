"""Handlers on the existing queue; fences and source locks guard atomic publication."""

import hashlib
import time
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.ai_gateway import GeminiProvider
from studio.config import settings
from studio.contracts import WorkspacePolicy
from studio.contracts.reconciliation import (
    ExceptionCase,
    ReconciliationContract,
    ReconciliationPlan,
)
from studio.database import (
    AuditRow,
    CanonicalRow,
    ExceptionRow,
    JobRow,
    PlanRow,
    ReconciliationContractRow,
    RunRow,
    TableRow,
    TraceRow,
    WorkspaceRow,
    identifier,
)
from studio.errors import DomainError
from studio.reconciliation_contracts import validate_reconciliation_contract
from studio.reconciliation_engine import match_records
from studio.reconciliation_planner import PLANNER_REVISION, propose_plan
from studio.reconciliation_repository import (
    load_canonical_records,
    selected_catalogue,
    write_match_artifact,
)
from studio.repository import reserve_gemini_request
from studio.verification import calculate_metric_snapshot, verify_result

Fence = Callable[[Session, str, str], JobRow]
Finish = Callable[[Session, JobRow, dict[str, Any]], None]


def execute_reconciliation(
    job_id: str, token: str, factory: Any, fence: Fence, finish: Finish
) -> None:
    """Write draft bytes, verify independently, lock dependencies and publish in one commit.

    Crash leaves unreferenced bytes. A replay sees the existing logical run and
    cannot create a second snapshot or cases. Failed verification never has metrics.
    """
    with factory() as db:
        job = fence(db, job_id, token)
        run = db.get(RunRow, job.payload["run_id"])
        assert run is not None
        if run.status in {"VERIFIED", "PARTIAL_VERIFIED", "VERIFICATION_FAILED"}:
            finish(db, job, {"run_id": run.id, "verification_status": run.status})
            db.commit()
            return
        rule = db.get(ReconciliationContractRow, run.contract_id)
        assert rule is not None
        contract = ReconciliationContract.model_validate(rule.definition)
        actor = Actor("worker", job.workspace_id, "editor")
        cats = selected_catalogue(
            db,
            actor,
            job.project_id,
            [contract.plan.left.canonical_id, contract.plan.right.canonical_id],
        )
        validate_reconciliation_contract(contract.plan, cats, actor.workspace_id, job.project_id)
        left, right = [load_canonical_records(db, actor, c.canonical) for c in cats]
        run_id, project_id, workspace_id = run.id, run.project_id, run.workspace_id
        run.status = "RUNNING"
        db.commit()
    started = time.monotonic()
    result = match_records(contract.plan, left, right)
    match_ms = int((time.monotonic() - started) * 1000)
    key = f"{workspace_id}/runs/{run_id}/{identifier()}/matches.parquet"
    digest = write_match_artifact(settings.storage_root, key, result)
    started = time.monotonic()
    checks = verify_result(contract.plan, left, right, result)
    verified = all(c.passed for c in checks)
    snapshot = (
        calculate_metric_snapshot(
            run_id, contract.id, contract.revision, contract.plan, left, right, result
        )
        if verified
        else None
    )
    verify_ms = int((time.monotonic() - started) * 1000)
    with factory() as db:
        job = fence(db, job_id, token)
        # Mapping approval locks TableRow too. Hold the same ordered locks until publication.
        for source in sorted(cats, key=lambda c: c.canonical.source_table_id):
            table = db.scalar(
                select(TableRow)
                .where(TableRow.id == source.canonical.source_table_id)
                .with_for_update()
            )
            canonical = db.get(CanonicalRow, source.canonical.id)
            if (
                table is None
                or canonical is None
                or canonical.stale
                or table.active_mapping_id != source.canonical.mapping_revision_id
            ):
                raise DomainError(
                    "STALE_CANONICAL", "Nguồn thay đổi trong khi chạy; cần duyệt lại."
                )
        run = db.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
        assert run is not None
        run.result_key, run.result_sha256 = key, digest
        run.result_metadata = dict(
            partition_counts=result.partition_counts,
            warnings=result.warnings,
            matching_ms=match_ms,
            verification_ms=verify_ms,
        )
        run.checks = [c.model_dump(mode="json") for c in checks]
        run.metric_snapshot = snapshot.model_dump(mode="json") if snapshot else None
        run.status = (
            "VERIFICATION_FAILED"
            if not verified
            else (
                "PARTIAL_VERIFIED"
                if any(
                    g.linkage_state in {"INVALID", "PENDING"}
                    or g.comparison_state == "NOT_COMPARABLE"
                    for g in result.groups
                )
                or any(
                    s.completeness != "CONFIRMED" for s in (contract.plan.left, contract.plan.right)
                )
                else "VERIFIED"
            )
        )
        if verified:
            for group in result.groups:
                evidence = [f"{m.side}:{m.canonical_id}:{m.record_id}" for m in group.members]
                for issue in group.exception_types:
                    case = ExceptionCase(
                        id=str(uuid5(NAMESPACE_URL, f"{run_id}:{group.id}:{issue}")),
                        workspace_id=workspace_id,
                        project_id=project_id,
                        run_id=run_id,
                        match_group_id=group.id,
                        type=issue,
                        severity_basis="Deterministic rule classification; no AI risk score",
                        evidence_ids=evidence,
                        rule_id=contract.id,
                    )
                    db.add(
                        ExceptionRow(
                            id=case.id,
                            workspace_id=workspace_id,
                            project_id=project_id,
                            run_id=run_id,
                            match_group_id=group.id,
                            type=issue,
                            definition=case.model_dump(mode="json"),
                        )
                    )
        db.add(
            AuditRow(
                workspace_id=workspace_id,
                actor_id="worker",
                action="RECONCILIATION_PUBLISHED"
                if verified
                else "RECONCILIATION_VERIFICATION_FAILED",
                resource_id=run_id,
            )
        )
        finish(db, job, {"run_id": run_id, "verification_status": run.status})
        db.commit()


def execute_planning(job_id: str, token: str, factory: Any, fence: Fence, finish: Finish) -> None:
    from studio.contracts.reconciliation import PlanningRequest

    with factory() as db:
        job = fence(db, job_id, token)
        draft = (
            PlanningRequest.model_validate(job.payload["request"])
            if "request" in job.payload
            else PlanningRequest.from_plan(ReconciliationPlan.model_validate(job.payload["draft"]))
        )
        actor = Actor("worker", job.workspace_id, "editor")
        cats = selected_catalogue(
            db, actor, job.project_id, [draft.left.canonical_id, draft.right.canonical_id]
        )
        workspace = db.get(WorkspaceRow, actor.workspace_id)
        assert workspace is not None
        policy = WorkspacePolicy.model_validate(workspace.policy)
        workspace_id, project_id = job.workspace_id, job.project_id
        db.rollback()
    provider = GeminiProvider(settings)
    started, outcome = time.monotonic(), "VALIDATED_PROPOSAL"

    def reserve() -> bool:
        with factory() as db:
            fence(db, job_id, token)
            lock = int.from_bytes(
                hashlib.sha256(b"studio:gemini-request-budget").digest()[:8], "big", signed=True
            )
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            # Task-specific lifetime cap supplements unchanged global/workspace ceilings.
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(AuditRow)
                    .where(AuditRow.action == "RECONCILIATION_PLANNER_ATTEMPT")
                )
                or 0
            )
            if count >= 2:
                return False
            allowed = reserve_gemini_request(db, workspace_id, job_id, settings)
            if allowed:
                db.add(
                    AuditRow(
                        workspace_id=workspace_id,
                        actor_id="worker",
                        action="RECONCILIATION_PLANNER_ATTEMPT",
                        resource_id=job_id,
                    )
                )
            db.commit()
            return allowed

    try:
        # An expired/reclaimed AI job cannot consume another two attempts after unknown delivery.
        with factory() as db:
            prior = db.scalar(
                select(AuditRow.id).where(
                    AuditRow.resource_id == job_id,
                    AuditRow.action == "RECONCILIATION_PLANNER_ATTEMPT",
                )
            )
            if prior:
                raise DomainError(
                    "AI_DELIVERY_UNKNOWN", "Job AI đã gửi; không tự gửi lại sau recovery."
                )
        proposal = propose_plan(provider, cats, draft, policy, reserve, workspace_id, project_id)
        with factory() as db:
            job = fence(db, job_id, token)
            row = PlanRow(
                workspace_id=workspace_id,
                project_id=project_id,
                origin="GEMINI",
                created_by=job.payload["actor_id"],
                proposal=proposal.model_dump(mode="json"),
            )
            db.add(row)
            db.flush()
            finish(
                db, job, {"plan_id": row.id, "source": "GEMINI", "proposal_status": proposal.status}
            )
            db.commit()
    except DomainError as exc:
        outcome = exc.code
        raise
    finally:
        provider.close()
        with factory() as db:
            db.add(
                TraceRow(
                    workspace_id=workspace_id,
                    job_id=job_id,
                    provider="GEMINI",
                    task_id="propose_reconciliation_contract",
                    prompt_revision=PLANNER_REVISION,
                    usage=provider.usage,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome=outcome,
                )
            )
            db.commit()
