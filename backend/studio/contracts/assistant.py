"""Hợp đồng Assistant: context rõ ràng, tools chỉ đọc và facts có nguồn bất biến."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from studio.contracts import Contract
from studio.contracts.reconciliation import (
    ExceptionCase,
    MatchGroup,
    MetricSnapshot,
    ReconciliationContract,
    VerifiedRun,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ToolName = Literal[
    "list_datasets",
    "get_run_summary",
    "get_metric_breakdown",
    "list_exceptions",
    "get_match_evidence",
    "get_rule",
    "get_workflow_status",
]
ClaimKind = Literal[
    "VERIFIED_FACT",
    "SUPPORTED_INTERPRETATION",
    "HYPOTHESIS",
    "UNKNOWN",
    "INSUFFICIENT_EVIDENCE",
]


class AssistantContext(Contract):
    project_id: Identifier
    run_id: Identifier | None = None
    dataset_id: Identifier | None = None
    group_id: Identifier | None = None
    case_id: Identifier | None = None

    @model_validator(mode="after")
    def group_requires_run(self) -> "AssistantContext":
        if (self.group_id or self.case_id) and not self.run_id:
            raise ValueError("EXPLICIT_RUN_REQUIRED")
        return self


class ToolRequest(Contract):
    name: ToolName
    context: AssistantContext
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=20, ge=1, le=50)
    metric_id: str | None = Field(default=None, max_length=100)


class DatasetItem(Contract):
    id: str
    name: str
    status: str


class WorkflowStatus(Contract):
    dataset_count: int
    ready_canonical_count: int
    mapping_review_count: int
    active_job_count: int
    approved_rule_ids: list[str]
    questions: list[str]


class ToolResult(Contract):
    name: ToolName
    workspace_id: str
    project_id: str
    run_id: str | None
    datasets: list[DatasetItem] = Field(default_factory=list, max_length=50)
    run: VerifiedRun | None = None
    snapshot: MetricSnapshot | None = None
    exceptions: list[ExceptionCase] = Field(default_factory=list, max_length=50)
    group: MatchGroup | None = None
    rule: ReconciliationContract | None = None
    workflow: WorkflowStatus | None = None
    total: int = 0
    truncated: bool = False


class FactReference(Contract):
    id: str
    run_id: str
    snapshot_id: str
    group_id: str | None = None
    member_id: str | None = None
    file_id: str | None = None
    source_table_id: str | None = None
    sheet: str | None = None
    row: int | None = None


class VerifiedFact(Contract):
    id: str
    label: str
    value: str
    reference_ids: list[str] = Field(min_length=1, max_length=102)
    metric_id: str | None = None
    currency: str | None = None


class AnswerFactSet(Contract):
    id: str
    workspace_id: str
    context: AssistantContext
    verification_status: Literal["VERIFIED", "PARTIAL_VERIFIED", "INSUFFICIENT_EVIDENCE"]
    snapshot: MetricSnapshot | None = None
    rule_id: str | None = None
    rule_revision: int | None = None
    facts: list[VerifiedFact] = Field(default_factory=list, max_length=40)
    references: list[FactReference] = Field(default_factory=list, max_length=102)
    evidence_complete: bool = True


class AnswerClaim(Contract):
    classification: ClaimKind
    fact_id: str | None = None
    code: Literal["FACT", "MISMATCH_NOT_CAUSE", "CHECK_SOURCE", "MISSING_EVIDENCE"]


class ModelAnswer(Contract):
    """Model chọn facts/diễn giải allowlist; không được sinh tiền, citations hay prose tự do."""

    fact_set_id: str
    claims: list[AnswerClaim] = Field(min_length=1, max_length=20)


class AnswerLine(Contract):
    classification: ClaimKind
    text: str
    fact_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list)


class WorkflowProposal(Contract):
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    approved_rule_ids: list[str]
    questions: list[str]
    action: Literal["OPEN_RECONCILIATION"] = "OPEN_RECONCILIATION"
    confirmation_required: Literal[True] = True


class AssistantAnswer(Contract):
    status: Literal["ANSWERED", "INSUFFICIENT_EVIDENCE", "PROVIDER_UNAVAILABLE", "REVIEW_REQUIRED"]
    mode: Literal["DETERMINISTIC", "GEMINI", "MOCK", "CACHE"]
    fact_set: AnswerFactSet
    lines: list[AnswerLine]
    proposal: WorkflowProposal | None = None
    suggestions: list[
        Literal["OPEN_EXCEPTIONS", "OPEN_EVIDENCE", "OPEN_RULE", "OPEN_DATA", "OPEN_REPORT"]
    ]
    provider: str | None = None
    model: str | None = None
    request_count: int = 0
    prompt_revision: str = "assistant-grounded-1"


class MessageInput(Contract):
    conversation_id: Identifier
    text: str = Field(min_length=1, max_length=2000)
    context: AssistantContext


class ConversationInput(Contract):
    context: AssistantContext
    title: str = Field(default="Hội thoại đối soát", min_length=1, max_length=100)


class ConversationView(Contract):
    id: str
    context: AssistantContext
    title: str
    created_at: datetime
    archived: bool


class MessageView(Contract):
    id: str
    role: Literal["user", "assistant"]
    text: str
    context: AssistantContext
    answer: AssistantAnswer | None = None
    created_at: datetime
