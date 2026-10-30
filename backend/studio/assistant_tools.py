"""Bảy tools chỉ đọc: kiểm quyền/context trước query và giới hạn dữ liệu tại backend."""

import hashlib
import json
from threading import Timer
from typing import Any

import duckdb
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.contracts.assistant import (
    AnswerFactSet,
    AssistantContext,
    DatasetItem,
    FactReference,
    ToolRequest,
    ToolResult,
    VerifiedFact,
    WorkflowStatus,
)
from studio.contracts.reconciliation import (
    ExceptionCase,
    MatchGroup,
    ReconciliationContract,
    VerifiedRun,
)
from studio.database import DatasetRow, ExceptionRow, ProjectRow, ReconciliationContractRow, RunRow
from studio.errors import DomainError
from studio.reconciliation_repository import _connection, result_path, run_contract
from studio.repository import get_scoped


def scoped_context(db: Session, actor: Actor, context: AssistantContext) -> RunRow | None:
    """Không phân biệt missing/foreign resource; group/case luôn thuộc đúng explicit run."""
    get_scoped(db, ProjectRow, context.project_id, actor)
    run = None
    if context.dataset_id:
        dataset = get_scoped(db, DatasetRow, context.dataset_id, actor)
        if dataset.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.run_id:
        run = get_scoped(db, RunRow, context.run_id, actor)
        if run.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.case_id:
        case = get_scoped(db, ExceptionRow, context.case_id, actor)
        if (
            case.project_id != context.project_id
            or case.run_id != context.run_id
            or (context.group_id and case.match_group_id != context.group_id)
        ):
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.group_id and run:
        if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"}:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Run chưa có evidence đã xác minh.", 409)
        exact_group(run, context.group_id)
    return run


def exact_group(run: RunRow, group_id: str) -> MatchGroup:
    """ID tham số hóa, checksum bắt buộc, không nhận SQL/path do người dùng/model sinh."""
    with _connection() as connection:
        path = result_path(run)
        timer = Timer(3, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            found = connection.execute(
                "SELECT group_json FROM read_parquet(?) WHERE group_id = ? LIMIT 1",
                [str(path), group_id],
            ).fetchone()
        except duckdb.Error as exc:
            raise DomainError(
                "TOOL_UNAVAILABLE", "Không truy xuất được evidence trong giới hạn.", 503
            ) from exc
        finally:
            timer.cancel()
    if found is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy group trong context.", 404)
    group = MatchGroup.model_validate_json(found[0])
    if group.id != group_id:
        raise DomainError("EVIDENCE_SCOPE_INVALID", "Nguồn không khớp group.")
    if len(group.members) > 100 or sum(len(m.evidence) for m in group.members) > 100:
        raise DomainError(
            "EVIDENCE_LIMIT", "Nhóm quá lớn; mở evidence có phân trang để kiểm tra.", 409
        )
    return group


def read_tool(db: Session, actor: Actor, request: ToolRequest) -> ToolResult:
    """F28: output DTO allowlist; không gọi provider và không ghi database."""
    context = request.context
    db.execute(text("SET LOCAL statement_timeout = '2500ms'"))
    row = scoped_context(db, actor, context)
    result = ToolResult(
        name=request.name,
        workspace_id=actor.workspace_id,
        project_id=context.project_id,
        run_id=context.run_id,
    )
    if request.name == "list_datasets":
        query = select(DatasetRow).where(
            DatasetRow.workspace_id == actor.workspace_id,
            DatasetRow.project_id == context.project_id,
        )
        result.total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        result.datasets = [
            DatasetItem(id=r.id, name=r.name[:255], status=r.status)
            for r in db.scalars(
                query.order_by(DatasetRow.created_at.desc(), DatasetRow.id)
                .offset(request.offset)
                .limit(request.limit)
            )
        ]
        result.truncated = result.total > request.offset + len(result.datasets)
        return result
    if request.name == "get_workflow_status":
        from studio.database import CanonicalRow, TableRow, VersionRow

        tables = (
            select(TableRow.id)
            .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
            .join(DatasetRow, VersionRow.dataset_id == DatasetRow.id)
            .where(DatasetRow.project_id == context.project_id)
        )
        ready = (
            db.scalar(
                select(func.count())
                .select_from(CanonicalRow)
                .where(
                    CanonicalRow.workspace_id == actor.workspace_id,
                    CanonicalRow.source_table_id.in_(tables),
                    CanonicalRow.stale.is_(False),
                    CanonicalRow.contract["quality_status"].astext == "READY",
                )
            )
            or 0
        )
        reviews = (
            db.scalar(
                select(func.count())
                .select_from(TableRow)
                .where(TableRow.id.in_(tables), TableRow.active_mapping_id.is_(None))
            )
            or 0
        )
        rules = list(
            db.scalars(
                select(ReconciliationContractRow.id)
                .where(
                    ReconciliationContractRow.workspace_id == actor.workspace_id,
                    ReconciliationContractRow.project_id == context.project_id,
                )
                .order_by(ReconciliationContractRow.created_at.desc(), ReconciliationContractRow.id)
                .limit(20)
            )
        )
        from studio.database import JobRow

        active = (
            db.scalar(
                select(func.count())
                .select_from(JobRow)
                .where(
                    JobRow.workspace_id == actor.workspace_id,
                    JobRow.project_id == context.project_id,
                    JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
                )
            )
            or 0
        )
        result.workflow = WorkflowStatus(
            dataset_count=db.scalar(
                select(func.count())
                .select_from(DatasetRow)
                .where(DatasetRow.project_id == context.project_id)
            )
            or 0,
            ready_canonical_count=ready,
            mapping_review_count=reviews,
            active_job_count=active,
            approved_rule_ids=rules,
            questions=["Xác nhận nguồn, kỳ có năm, timezone và coverage trước khi tạo kế hoạch."],
        )
        return result
    if row is None or row.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or not row.metric_snapshot:
        raise DomainError("INSUFFICIENT_EVIDENCE", "Chọn run đã xác minh để tra cứu facts.", 409)
    verified = VerifiedRun.model_validate(run_contract(row).model_dump())
    if request.name == "get_run_summary":
        result.run = verified
    elif request.name == "get_metric_breakdown":
        allowed = {
            "full_match_rate",
            "linkage_rate",
            "exception_rate",
            "automation_coverage",
            "review_rate",
            *(m.metric_id for m in verified.metric_snapshot.monetary),
        }
        if request.metric_id and request.metric_id not in allowed:
            raise DomainError(
                "INSUFFICIENT_EVIDENCE", "Metric không có trong snapshot của run.", 409
            )
        result.snapshot = verified.metric_snapshot
    elif request.name == "list_exceptions":
        cases_query = select(ExceptionRow).where(
            ExceptionRow.workspace_id == actor.workspace_id,
            ExceptionRow.project_id == context.project_id,
            ExceptionRow.run_id == row.id,
        )
        result.total = db.scalar(select(func.count()).select_from(cases_query.subquery())) or 0
        result.exceptions = [
            ExceptionCase.model_validate(
                r.definition
                | dict(
                    workflow_state=r.workflow_state,
                    notes=r.notes[:500],
                    reviewed_by=r.reviewed_by,
                    reviewed_at=r.reviewed_at,
                )
            )
            for r in db.scalars(
                cases_query.order_by(ExceptionRow.id).offset(request.offset).limit(request.limit)
            )
        ]
        result.truncated = result.total > request.offset + len(result.exceptions)
    elif request.name == "get_match_evidence":
        group_id = context.group_id
        if context.case_id:
            group_id = get_scoped(db, ExceptionRow, context.case_id, actor).match_group_id
        if not group_id:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Chọn group hoặc ngoại lệ cụ thể.", 409)
        result.group = exact_group(row, group_id)
    elif request.name == "get_rule":
        rule = get_scoped(db, ReconciliationContractRow, row.contract_id, actor)
        if rule.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy rule trong context.", 404)
        result.rule = ReconciliationContract.model_validate(rule.definition)
    return result


def build_fact_set(db: Session, actor: Actor, context: AssistantContext) -> AnswerFactSet:
    """Facts chỉ copy từ VerifiedRun/MetricSnapshot/comparison, không tính lại KPI/tiền."""
    row = scoped_context(db, actor, context)
    values: dict[str, Any] = dict(
        workspace_id=actor.workspace_id,
        business_scope=get_scoped(db, ProjectRow, context.project_id, actor).business_scope,
        context=context,
        verification_status="INSUFFICIENT_EVIDENCE",
        facts=[],
        references=[],
    )
    if row and row.status in {"VERIFIED", "PARTIAL_VERIFIED"} and row.metric_snapshot:
        summary = read_tool(db, actor, ToolRequest(name="get_run_summary", context=context)).run
        assert summary is not None
        snapshot = summary.metric_snapshot
        rule = read_tool(db, actor, ToolRequest(name="get_rule", context=context)).rule
        assert rule is not None
        if (
            snapshot.run_id != row.id
            or snapshot.rule_id != rule.id
            or snapshot.rule_revision != rule.revision
        ):
            raise DomainError("EVIDENCE_SCOPE_INVALID", "Snapshot không khớp run/rule revision.")
        base_ref = FactReference(id=snapshot.id, run_id=row.id, snapshot_id=snapshot.id)
        refs = [base_ref]
        facts = [
            VerifiedFact(
                id="run_status",
                label="Trạng thái run",
                value=row.status,
                reference_ids=[base_ref.id],
            )
        ]
        for metric in (
            "full_match_rate",
            "linkage_rate",
            "exception_rate",
            "automation_coverage",
            "review_rate",
        ):
            rate = getattr(snapshot, metric)
            facts.append(
                VerifiedFact(
                    id=metric,
                    label={
                        "full_match_rate": "Tỷ lệ khớp đã xác minh",
                        "linkage_rate": "Tỷ lệ liên kết",
                        "exception_rate": "Tỷ lệ ngoại lệ",
                        "automation_coverage": "Mức tự động hóa",
                        "review_rate": "Tỷ lệ cần review",
                    }[metric],
                    value=(
                        f"{rate.percent if rate.percent is not None else 'N/A'} "
                        f"({rate.numerator}/{rate.denominator})"
                    ),
                    reference_ids=[base_ref.id],
                    metric_id=metric,
                )
            )
        for i, money in enumerate(snapshot.monetary):
            facts.append(
                VerifiedFact(
                    id=f"variance_{i}",
                    label="Lệch tuyệt đối / lệch có dấu",
                    value=f"{money.absolute_variance} / {money.signed_variance} {money.currency}",
                    reference_ids=[base_ref.id],
                    metric_id=money.metric_id,
                    currency=money.currency,
                )
            )
        if context.group_id or context.case_id:
            group = read_tool(
                db, actor, ToolRequest(name="get_match_evidence", context=context)
            ).group
            assert group is not None
            group_ref = FactReference(
                id=group.id, run_id=row.id, snapshot_id=snapshot.id, group_id=group.id
            )
            refs.append(group_ref)
            for member in group.members:
                for source in member.evidence:
                    refs.append(
                        FactReference(
                            id=f"{group.id}:{source.source_row_id}:{source.row}",
                            run_id=row.id,
                            snapshot_id=snapshot.id,
                            group_id=group.id,
                            member_id=member.record_id,
                            file_id=source.file_id,
                            source_table_id=source.source_table_id,
                            sheet=source.sheet,
                            row=source.row,
                        )
                    )
            evidence_ids = list(dict.fromkeys(r.id for r in refs[1:]))
            facts.append(
                VerifiedFact(
                    id="comparison",
                    label="Kết luận so sánh",
                    value=f"{group.linkage_state} + {group.comparison_state}",
                    reference_ids=evidence_ids,
                )
            )
            for i, comparison in enumerate(group.comparisons):
                facts.append(
                    VerifiedFact(
                        id=f"comparison_{i}",
                        label="Trái / phải / delta / tolerance",
                        value=(
                            f"{comparison.left_amount} / {comparison.right_amount} / "
                            f"{comparison.delta} / {comparison.tolerance} {comparison.currency}"
                        ),
                        reference_ids=evidence_ids,
                        metric_id=comparison.metric_id,
                        currency=comparison.currency,
                    )
                )
        values.update(
            verification_status=row.status,
            snapshot=snapshot,
            rule_id=rule.id,
            rule_revision=rule.revision,
            facts=facts,
            references=list({r.id: r for r in refs}.values()),
        )
    body = AnswerFactSet(id="pending", **values)
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json", exclude={"id"}), sort_keys=True).encode()
    ).hexdigest()
    return body.model_copy(update={"id": digest})
