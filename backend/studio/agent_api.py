"""Review API buộc quyết định con người vào owner, nonce, expiry và source revision."""

import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.agent_intents import validate_intents
from studio.agent_preparation import approval_from_draft, validate_draft
from studio.agent_workflows import (
    advance,
    digest,
    lock_review_sources,
    own_workflow,
    review_fingerprint,
    save,
    view,
    wait_for,
)
from studio.assistant_tools import agent_catalogue
from studio.config import AGENT_UPLOAD_EXTENSIONS, settings
from studio.contracts import DatasetProfile
from studio.contracts.agent import (
    ClarificationDecision,
    IntentBatch,
    MappingAssessment,
    MappingReviewDecision,
    NormalizationDraft,
    PlanReviewDecision,
    QuerySelection,
    ReviewDecision,
    ReviewDraftUpdate,
    ReviewReply,
    ReviewRequest,
    ReviewToken,
    TableBlock,
    WorkflowState,
    WorkflowView,
)
from studio.contracts.assistant import AssistantContext
from studio.contracts.data_query import DataQuery, QueryResult, SourceRowRequest, SourceRowResult
from studio.contracts.reconciliation import PlanProposal
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    ConversationRow,
    JobRow,
    MappingRow,
    MessageRow,
    PlanRow,
    ProjectRow,
    TableRow,
    now,
)
from studio.errors import DomainError
from studio.parsing import inspect_upload
from studio.repository import enqueue_job, get_scoped, project_for_table


def decide(db: Session, actor: Actor, workflow_id: str, body: ReviewDecision) -> WorkflowView:
    """Một transaction duy nhất: reauthorize → approval → state → next-job enqueue."""
    row = own_workflow(db, actor, workflow_id, lock=True)
    require_editor(actor, db, row.id)
    state = WorkflowState.model_validate(row.detail)
    review = next((r for r in state.reviews if r.id == body.review_id), None)
    if review is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy yêu cầu xác nhận.", 404)
    if (
        not secrets.compare_digest(review.nonce, body.nonce)
        or not secrets.compare_digest(review.fingerprint, body.fingerprint)
        or body.decision.type != review.kind
    ):
        raise DomainError("STALE_CONTEXT", "Xác nhận không còn phù hợp; hãy mở lại thẻ.", 409)
    decision_payload = body.decision.model_dump(mode="json")
    if isinstance(body.decision, PlanReviewDecision) and not body.decision.invalid_rows_reviewed:
        # Preserve the digest of decisions saved before this additive acknowledgement.
        decision_payload.pop("invalid_rows_reviewed")
    decision_hash = digest(decision_payload)
    if review.state == "DECIDED":
        if decision_hash != review.decision_sha256:
            raise DomainError("IDEMPOTENCY_CONFLICT", "Quyết định này đã có nội dung khác.", 409)
        return view(row)
    if review.pending_reply_job_id:
        raise DomainError(
            "REVIEW_REPLY_PENDING", "Đang đọc câu trả lời; chờ bản diễn giải để xác nhận.", 409
        )
    lock_review_sources(db, actor, review)
    if (
        row.state not in {"WAITING_REVIEW", "RUNNING"}
        or review.state != "OPEN"
        or review.expires_at <= now()
        or review.fingerprint
        != review_fingerprint(db, actor, review.kind, review.resource_id, review.evidence_refs)
    ):
        raise DomainError("STALE_CONTEXT", "Nguồn hoặc thời hạn xác nhận đã thay đổi.", 409)
    if isinstance(body.decision, MappingReviewDecision):
        from studio.api import apply_mapping_approval

        draft = body.decision.draft
        if draft.table_id != review.resource_id:
            raise DomainError("STALE_CONTEXT", "Quyết định không thuộc bảng đang chờ.", 409)
        table = get_scoped(db, TableRow, draft.table_id, actor)
        mapping_id = db.scalar(
            select(MappingRow.id)
            .where(
                MappingRow.source_table_id == table.id,
                MappingRow.workspace_id == actor.workspace_id,
            )
            .order_by(MappingRow.revision.desc())
            .limit(1)
        )
        if not mapping_id:
            raise DomainError("REVIEW_REQUIRED", "Chưa có proposal cho bảng này.")
        from studio.mapping_verification import assess_table_mapping

        assessment = assess_table_mapping(db, actor, draft)
        if not assessment.preflight_ready:
            raise DomainError("MAPPING_PREFLIGHT_REQUIRED", "; ".join(assessment.questions))
        approval = approval_from_draft(
            draft, DatasetProfile.model_validate(table.profile), body.decision.extraction_reviewed
        )
        approved = apply_mapping_approval(mapping_id, approval, db, actor)
        state.confirmed_mapping_ids.append(approved.id)
        review.result_id = approved.id
    elif isinstance(body.decision, PlanReviewDecision):
        from studio.reconciliation_api import approve_plan

        plan = body.decision.plan
        expected = review.planning_request
        if not expected or (plan.left.canonical_id, plan.right.canonical_id) != (
            expected.left.canonical_id,
            expected.right.canonical_id,
        ):
            raise DomainError("STALE_CONTEXT", "Nguồn đối soát khác yêu cầu đang chờ.", 409)
        # Giữ nguyên proposal AI; quyết định sửa rule là một bản có nguồn HUMAN_REVIEW.
        proposal = PlanRow(
            workspace_id=actor.workspace_id,
            project_id=row.project_id,
            origin="HUMAN_REVIEW",
            created_by=actor.id,
            proposal=PlanProposal(status="PROPOSED", plan=plan).model_dump(mode="json"),
        )
        db.add(proposal)
        db.flush()
        contract = approve_plan(
            proposal.id, db, actor, invalid_rows_reviewed=body.decision.invalid_rows_reviewed
        )
        state.confirmed_contract_id = contract.id
        review.result_id = contract.id
    elif isinstance(body.decision, ClarificationDecision):
        context = AssistantContext.model_validate(row.context)
        catalogue = agent_catalogue(db, actor, context, state.dataset_ids, workflow_id=row.id)
        if review.options and not any(
            option.intent == body.decision.intent for option in review.options
        ):
            raise DomainError("STALE_CONTEXT", "Lựa chọn không thuộc câu hỏi đang chờ.", 409)
        validated = validate_intents(
            IntentBatch(intents=[body.decision.intent]).model_dump_json(),
            [row.goal],
            catalogue,
        )
        state.intent = validated[0]
    review.state, review.decision_sha256 = "DECIDED", decision_hash
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            action="AGENT_CLARIFICATION_ANSWERED"
            if review.kind == "CLARIFICATION"
            else "AGENT_REVIEW_DECIDED",
            resource_id=review.id,
        )
    )
    row.state = "RUNNING"
    save(row, state)
    advance(db, row)
    db.flush()
    return view(row)


def editable_review(
    db: Session, actor: Actor, workflow_id: str, binding: ReviewToken, *, renew: bool = False
) -> tuple[AgentWorkflowRow, WorkflowState, ReviewRequest]:
    """Fence draft writes with the same owner, source locks and nonce as approval.

    Only an explicit renewal may cross expiry, and only with unchanged source state.
    No provider request, approval, normalization or financial job is started here.
    """
    row = own_workflow(db, actor, workflow_id, lock=True)
    require_editor(actor, db, row.id)
    state = WorkflowState.model_validate(row.detail)
    review = next((r for r in state.reviews if r.id == binding.review_id), None)
    if review is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy thẻ xác nhận.", 404)
    if review.pending_reply_job_id:
        raise DomainError("REVIEW_REPLY_PENDING", "Chờ câu trả lời đang được xử lý.", 409)
    lock_review_sources(db, actor, review)
    if (
        row.state not in {"WAITING_REVIEW", "RUNNING"}
        or review.state != "OPEN"
        or not secrets.compare_digest(review.nonce, binding.nonce)
        or not secrets.compare_digest(review.fingerprint, binding.fingerprint)
        or (not renew and review.expires_at <= now())
        or review.fingerprint
        != review_fingerprint(db, actor, review.kind, review.resource_id, review.evidence_refs)
    ):
        raise DomainError("STALE_CONTEXT", "Thẻ hoặc nguồn đã thay đổi; hãy mở lại thẻ.", 409)
    return row, state, review


def build_router(database: Callable[..., Any], current_actor: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix="/api/agent", tags=["Agent"])
    DB = Annotated[Session, Depends(database)]
    User = Annotated[Actor, Depends(current_actor)]
    Key = Annotated[str, Header(min_length=1, max_length=160, alias="Idempotency-Key")]

    @router.post("/mapping-preflight", response_model=MappingAssessment)
    def mapping_preflight(body: NormalizationDraft, db: DB, actor: User) -> MappingAssessment:
        from studio.mapping_verification import assess_table_mapping

        return assess_table_mapping(db, actor, body)

    @router.post("/source-rows", response_model=SourceRowResult)
    def source_row(body: SourceRowRequest, db: DB, actor: User) -> SourceRowResult:
        import time

        import polars as pl

        from studio.data_query import _collect_bounded, json_value
        from studio.database import ArtifactRow
        from studio.storage import checksum, storage_path

        table = get_scoped(db, TableRow, body.table_id, actor)
        if project_for_table(db, table).id != body.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Dòng nguồn không thuộc dự án.", 404)
        artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
        path = storage_path(settings.storage_root, artifact.storage_key)
        if checksum(path) != artifact.sha256:
            raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Nguồn không khớp checksum.")
        frame = _collect_bounded(
            pl.scan_parquet(path)
            .filter(pl.col("_source_row") == body.row)
            .select([c["id"] for c in table.parsed_contract["columns"]])
            .head(1),
            time.monotonic() + settings.agent_query_timeout_seconds,
        )
        names = {c["id"]: f"{c['name']} ({c['id']})" for c in table.parsed_contract["columns"]}
        return SourceRowResult(
            rows=[{names[k]: json_value(v) for k, v in row.items()} for row in frame.to_dicts()]
        )

    @router.post("/attachments", status_code=202)
    def attachments(
        db: DB,
        actor: User,
        key: Key,
        files: Annotated[list[UploadFile], File()],
        project_id: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        from studio.api import persist_uploads

        require_editor(actor, db)
        if not 1 <= len(files) <= settings.agent_max_upload_files:
            raise DomainError(
                "TOO_MANY_FILES",
                f"Mỗi lần đính kèm cần từ 1 đến {settings.agent_max_upload_files} tệp CSV/XLSX.",
            )
        inspections = [
            inspect_upload(f.file, f.filename or "", f.content_type or "", settings) for f in files
        ]
        if any(i.extension not in AGENT_UPLOAD_EXTENSIONS for i in inspections):
            raise DomainError("AGENT_FILE_TYPE_UNSUPPORTED", "Chat hiện nhận CSV và XLSX.")
        request_hash = digest([project_id, [(i.sha256, i.filename) for i in inspections]])
        identity = f"agent-attachments:{actor.workspace_id}:{actor.id}:{key}"
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": identity}
        )
        bootstrap_id = str(uuid5(NAMESPACE_URL, identity))
        project: ProjectRow | None
        if project_id:
            project = get_scoped(db, ProjectRow, project_id, actor)
        else:
            project = db.get(ProjectRow, bootstrap_id)
            if project is None:
                project = ProjectRow(
                    id=bootstrap_id,
                    workspace_id=actor.workspace_id,
                    name="Dữ liệu mới",
                    business_scope=f"UNCONFIRMED:{bootstrap_id}",
                )
                db.add(project)
                db.flush()
                db.add(
                    AuditRow(
                        workspace_id=actor.workspace_id,
                        actor_id=actor.id,
                        action="PROJECT_SCOPE_UNCONFIRMED",
                        resource_id=project.id,
                    )
                )
        receipt = enqueue_job(
            db,
            actor.workspace_id,
            project.id,
            "attachment_receipt",
            identity,
            dict(actor_id=actor.id, request_sha256=request_hash),
        )
        if receipt.status == "SUCCEEDED":
            assert receipt.result is not None
            return receipt.result
        uploaded = persist_uploads(db, actor, project.id, files, request_ai_mapping=False)
        result = dict(
            project_id=project.id,
            project_name=project.name,
            scope_confirmed=not project.business_scope.startswith("UNCONFIRMED:"),
            **uploaded,
        )
        receipt.status, receipt.result = "SUCCEEDED", result
        db.commit()
        return result

    @router.get("/workflows/{workflow_id}", response_model=WorkflowView)
    def workflow(workflow_id: str, db: DB, actor: User) -> WorkflowView:
        return view(own_workflow(db, actor, workflow_id))

    @router.get("/tables/{table_id}/mapping-reviews", response_model=list[WorkflowView])
    def mapping_reviews(table_id: str, db: DB, actor: User) -> list[WorkflowView]:
        """Expose the existing actor-owned draft to both Chat and Data Manager."""
        table = get_scoped(db, TableRow, table_id, actor)
        project = project_for_table(db, table)
        rows = db.scalars(
            select(AgentWorkflowRow)
            .join(ConversationRow, AgentWorkflowRow.conversation_id == ConversationRow.id)
            .where(
                AgentWorkflowRow.workspace_id == actor.workspace_id,
                AgentWorkflowRow.project_id == project.id,
                AgentWorkflowRow.actor_id == actor.id,
                ConversationRow.deleted_at.is_(None),
                AgentWorkflowRow.detail.contains(
                    {"reviews": [dict(kind="MAPPING", resource_id=table.id, state="OPEN")]}
                ),
            )
            .order_by(AgentWorkflowRow.updated_at.desc())
            .limit(10)
        )
        return [view(own_workflow(db, actor, row.id)) for row in rows]

    @router.post("/workflows/{workflow_id}/draft", response_model=WorkflowView)
    def save_draft(
        workflow_id: str, body: ReviewDraftUpdate, db: DB, actor: User, key: Key
    ) -> WorkflowView:
        row, state, review = editable_review(db, actor, workflow_id, body)
        if body.check_planning_scope and (
            review.kind != "RECONCILIATION" or body.planning_request is None or review.plan
        ):
            raise DomainError("INVALID_REVIEW_DRAFT", "Chỉ kiểm tra phạm vi đang thiếu.", 422)
        if sum(v is not None for v in (body.draft, body.plan, body.planning_request)) != 1:
            raise DomainError("INVALID_REVIEW_DRAFT", "Chỉ lưu một bản nháp đúng loại thẻ.", 422)
        if body.draft is not None and review.kind == "MAPPING":
            table = get_scoped(db, TableRow, review.resource_id, actor)
            validate_draft(body.draft, table.id, DatasetProfile.model_validate(table.profile))
            review.normalization_draft = body.draft
        elif review.kind == "RECONCILIATION" and (body.plan or body.planning_request):
            from studio.contracts.reconciliation import PlanningRequest
            from studio.reconciliation_contracts import validate_reconciliation_contract
            from studio.reconciliation_planner import preview_plan, validate_planning_request
            from studio.reconciliation_repository import selected_catalogue

            request = PlanningRequest.from_plan(body.plan) if body.plan else body.planning_request
            assert request is not None
            expected = review.planning_request
            if not expected or (request.left.canonical_id, request.right.canonical_id) != (
                expected.left.canonical_id,
                expected.right.canonical_id,
            ):
                raise DomainError("AI_INVALID_SOURCE", "Không được đổi nguồn đang chờ.", 422)
            cats = selected_catalogue(
                db,
                actor,
                row.project_id,
                [
                    request.left.canonical_id,
                    request.right.canonical_id,
                ],
            )
            validate_planning_request(request, cats, actor.workspace_id, row.project_id)
            if body.check_planning_scope:
                from studio.agent_tools import JobReference, PlanAction, execute_tool
                from studio.reconciliation_planner import missing_confirmations

                if missing_confirmations(request) or state.intent is None:
                    raise DomainError(
                        "REVIEW_REQUIRED", "Cần xác nhận kỳ, ngày và độ đầy đủ của hai nguồn.", 422
                    )
                reference = execute_tool(
                    db,
                    actor,
                    PlanAction(
                        name="prepare_reconciliation_plan",
                        context=AssistantContext.model_validate(row.context),
                        request=request,
                    ),
                    f"{row.id}:scope:{review.id}:{digest(request.model_dump(mode='json'))}",
                )
                assert isinstance(reference, JobReference)
                review.state = "INVALIDATED"
                state.intent.planning_request = request
                wait_for(
                    db,
                    row,
                    state,
                    "prepare_reconciliation_plan",
                    request.left.canonical_id,
                    reference,
                )
                save(row, state)
                db.add(
                    AuditRow(
                        workspace_id=actor.workspace_id,
                        actor_id=actor.id,
                        action="AGENT_PLANNING_SCOPE_CONFIRMED",
                        resource_id=review.id,
                    )
                )
                db.commit()
                return view(row)
            plan = body.plan or preview_plan(
                request, review.suggestions, cats[0].canonical.entity_kind, review.plan
            )
            if plan:
                validate_reconciliation_contract(plan, cats, actor.workspace_id, row.project_id)
            review.planning_request, review.plan = request, plan
        else:
            raise DomainError("INVALID_REVIEW_DRAFT", "Bản nháp khác loại thẻ đang chờ.", 422)
        review.nonce, review.expires_at = secrets.token_hex(16), now() + timedelta(minutes=30)
        save(row, state)
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="AGENT_DRAFT_SAVED",
                resource_id=review.id,
            )
        )
        db.commit()
        return view(row)

    @router.post("/workflows/{workflow_id}/renew-review", response_model=WorkflowView)
    def renew_review(
        workflow_id: str, body: ReviewToken, db: DB, actor: User, key: Key
    ) -> WorkflowView:
        row, state, review = editable_review(db, actor, workflow_id, body, renew=True)
        review.nonce, review.expires_at = secrets.token_hex(16), now() + timedelta(minutes=30)
        save(row, state)
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="AGENT_REVIEW_RENEWED",
                resource_id=review.id,
            )
        )
        db.commit()
        return view(row)

    @router.post("/workflows/{workflow_id}/query-pages", response_model=QueryResult)
    def query_page(workflow_id: str, body: DataQuery, db: DB, actor: User) -> QueryResult:
        """Remember displayed page for follow-up; original result and run stay unchanged."""
        from studio.data_query import execute_query

        row = own_workflow(db, actor, workflow_id, lock=True)
        state = WorkflowState.model_validate(row.detail)
        core = body.model_dump(exclude={"offset", "sort"})
        if not any(
            isinstance(block, TableBlock)
            and block.result.query.model_dump(exclude={"offset", "sort"}) == core
            for block in state.blocks
        ):
            raise DomainError(
                "STALE_CONTEXT", "Trang dữ liệu không thuộc kết quả hội thoại này.", 409
            )
        result = execute_query(db, actor, body)
        state.query_selection = QuerySelection(
            query=result.query,
            group_ids=[str(r["group_id"]) for r in result.rows if r.get("group_id")],
        )
        save(row, state)
        db.commit()
        return result

    @router.post("/workflows/{workflow_id}/decisions", response_model=WorkflowView)
    def decision(
        workflow_id: str, body: ReviewDecision, db: DB, actor: User, key: Key
    ) -> WorkflowView:
        result = decide(db, actor, workflow_id, body)
        db.commit()
        return result

    @router.post("/workflows/{workflow_id}/replies", status_code=202)
    def reply(workflow_id: str, body: ReviewReply, db: DB, actor: User, key: Key) -> dict[str, str]:
        row = own_workflow(db, actor, workflow_id, lock=True)
        require_editor(actor, db, row.id)
        payload = dict(
            workflow_id=row.id,
            conversation_id=row.conversation_id,
            reply=body.model_dump(mode="json", exclude_none=True),
        )
        if body.model_choice is not None:
            payload["model_choice"] = body.model_choice
        existing = db.scalar(
            select(JobRow).where(
                JobRow.workspace_id == actor.workspace_id,
                JobRow.idempotency_key == f"agent-review:{actor.id}:{key}",
            )
        )
        if existing:
            if existing.kind != "agent_review" or existing.payload != payload:
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "Mã trả lời đã dùng với nội dung khác.", 409
                )
            return dict(job_id=existing.id, status=existing.status)
        from studio.assistant_api import check_model_choice

        check_model_choice(db, actor, body.model_choice)
        state = WorkflowState.model_validate(row.detail)
        review = next((r for r in state.reviews if r.id == body.review_id), None)
        if review:
            lock_review_sources(db, actor, review)
        if (
            review is None
            or review.state != "OPEN"
            or row.state != "WAITING_REVIEW"
            or not secrets.compare_digest(review.nonce, body.nonce)
            or not secrets.compare_digest(review.fingerprint, body.fingerprint)
            or review.expires_at <= now()
            or review.fingerprint
            != review_fingerprint(db, actor, review.kind, review.resource_id, review.evidence_refs)
        ):
            raise DomainError("STALE_CONTEXT", "Thẻ xác nhận không còn phù hợp.", 409)
        if review.pending_reply_job_id:
            existing = get_scoped(db, JobRow, review.pending_reply_job_id, actor)
            if existing.idempotency_key != f"agent-review:{actor.id}:{key}":
                raise DomainError("REVIEW_REPLY_PENDING", "Câu trả lời trước còn xử lý.", 409)
        job = enqueue_job(
            db,
            actor.workspace_id,
            row.project_id,
            "agent_review",
            f"agent-review:{actor.id}:{key}",
            payload,
        )
        review.pending_reply_job_id = job.id
        from studio.assistant_api import own_conversation

        conversation = own_conversation(db, actor, row.conversation_id)
        message_id = str(uuid5(NAMESPACE_URL, f"agent-review-message:{job.id}"))
        if db.get(MessageRow, message_id) is None:
            db.add(
                MessageRow(
                    id=message_id,
                    conversation_id=row.conversation_id,
                    job_id=job.id,
                    role="user",
                    text=body.text,
                    context=conversation.context,
                )
            )
        save(row, state)
        db.commit()
        return dict(job_id=job.id, status=job.status)

    @router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowView)
    def cancel(workflow_id: str, db: DB, actor: User, key: Key) -> WorkflowView:
        row = own_workflow(db, actor, workflow_id, lock=True)
        if row.state not in {
            "COMPLETED",
            "FAILED",
            "BLOCKED",
            "PARTIAL",
            "CANCELLED_BEFORE_NEXT_STEP",
        }:
            row.state = "CANCELLED_BEFORE_NEXT_STEP"
            row.updated_at = now()
            db.add(
                AuditRow(
                    workspace_id=actor.workspace_id,
                    actor_id=actor.id,
                    action="AGENT_CANCELLED_BEFORE_NEXT_STEP",
                    resource_id=row.id,
                )
            )
        db.commit()
        return view(row)

    return router
