"""Mục tiêu, công việc và quyết định có kiểu; model không sở hữu quyền phê duyệt."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from studio.contracts import Contract, SchemaDefinition
from studio.contracts.assistant import AssistantAnswer, AssistantContext, Identifier, ToolResult
from studio.contracts.data_query import (
    DataQuery,
    QueryAggregation,
    QueryFilter,
    QueryOperations,
    QueryResult,
)
from studio.contracts.reconciliation import (
    PlanningRequest,
    PlanningSource,
    PlanningSuggestions,
    ReconciliationPlan,
)

IntentName = Literal[
    "CHECK_DATASET_STATUS",
    "EXPLORE_DATA",
    "PREPARE_NORMALIZATION",
    "RECONCILE_DATASETS",
    "QUERY_DATA",
    "EXPLAIN_RESULT",
    "SUMMARIZE_RESULTS",
    "CREATE_VISUALIZATION",
    "CONTINUE_REVIEW",
    "EXPORT_RESULT",
    "CLARIFY",
    "UNSUPPORTED",
]


class AgentIntent(Contract):
    intent: IntentName
    dataset_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    run_id: Identifier | None = None
    key_value: str | None = Field(default=None, min_length=1, max_length=200)
    result_position: int | None = Field(default=None, ge=1, le=50)
    query: DataQuery | None = None
    planning_request: PlanningRequest | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
    export_format: Literal["csv", "xlsx"] = "xlsx"


class NormalizationField(Contract):
    source_field: Identifier
    target_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    data_type: Literal["string", "decimal", "date"]
    business_key: bool = False
    semantic_metric: str | None = None
    amount_basis: str | None = None
    currency: str | None = None
    unit: str | None = None
    locale: Literal["en-US", "vi-VN"] | None = None
    date_format: str | None = None
    timezone: str | None = None
    question: str = ""


class NormalizationDraft(Contract):
    table_id: Identifier
    entity_kind: str = Field(min_length=1, max_length=100)
    grain: str = Field(min_length=1, max_length=200)
    fields: list[NormalizationField] = Field(min_length=1, max_length=40)


class MappingCheck(Contract):
    field_id: str
    name: str
    state: Literal["VERIFIED", "NEEDS_CONFIRMATION", "BLOCKED"]
    messages: list[str] = Field(default_factory=list)
    error_counts: dict[str, int] = Field(default_factory=dict)
    affected_rows: int = 0


class RelatedKeyCheck(Contract):
    table_id: str
    source_name: str
    fields: list[str]
    shared_keys: int
    left_duplicate_rows: int
    right_duplicate_rows: int
    missing_key_rows: int


class MappingAssessment(Contract):
    draft: NormalizationDraft
    source_rows: int
    verified_fields: int
    pending_fields: int
    checks: list[MappingCheck]
    questions: list[str]
    preflight_ready: bool
    predicted_invalid_rows: int | None = None
    error_counts: dict[str, int] = Field(default_factory=dict)
    source_sha256: str
    currencies: list[str] = Field(default_factory=list)
    related_keys: list[RelatedKeyCheck] = Field(default_factory=list)


class SourceColumn(Contract):
    id: str
    name: str
    type_candidates: list[str]
    null_count: int
    distinct_count: int


class TableContext(Contract):
    table_id: str
    sheet: str
    row_count: int
    columns: list[SourceColumn] = Field(max_length=40)
    canonical_id: str | None = None
    canonical_status: Literal["READY", "PARTIAL", "FAILED"] | None = None
    schema_definition: SchemaDefinition | None = None
    mapping_id: str | None = None
    paid_status_fields: list[str] = Field(default_factory=list)


class DatasetContext(Contract):
    id: str
    name: str
    status: str
    tables: list[TableContext] = Field(max_length=5)


class IntentCatalogue(Contract):
    context: AssistantContext
    project_scope: str = ""
    datasets: list[DatasetContext] = Field(max_length=5)
    run_ids: list[str] = Field(default_factory=list, max_length=20)
    confirmed_plan: ReconciliationPlan | None = None
    verified_run_fields: list[str] = Field(default_factory=list)
    verified_metric_ids: list[str] = Field(default_factory=list)
    status_values: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    previous_query: DataQuery | None = None
    previous_goal: str | None = None
    pending_question: str | None = None
    previous_groups: list[str] = Field(default_factory=list, max_length=50)


class IntentBatch(Contract):
    intents: list[AgentIntent] = Field(min_length=1, max_length=10)


class RoutingQuery(QueryOperations):
    """Model chọn một nguồn trong catalogue; không tự ghép project/kind/ID."""

    source_ref: str = Field(min_length=1, max_length=64)
    filters: list[QueryFilter] = Field(max_length=8)
    aggregations: list[QueryAggregation] = Field(max_length=5)
    group_by: list[Identifier] = Field(max_length=3)
    currency_field: Identifier | None


class ReconciliationSelection(Contract):
    """Chọn phạm vi đã lưu hoặc facts mới cần review, không dựng lại approved plan."""

    left_canonical_id: Identifier
    right_canonical_id: Identifier
    confirmed_run_id: Identifier | None = None
    period_start: date | None = None
    period_end: date | None = None
    timezone: str | None = Field(default=None, max_length=100)
    left_source: PlanningSource | None = None
    right_source: PlanningSource | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class RoutingIntent(Contract):
    intent: IntentName
    dataset_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    run_id: Identifier | None = None
    key_value: str | None = Field(default=None, min_length=1, max_length=200)
    result_position: int | None = Field(default=None, ge=1, le=50)
    query: RoutingQuery | None = None
    reconciliation: ReconciliationSelection | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
    export_format: Literal["csv", "xlsx"] = "xlsx"


class RoutingBatch(Contract):
    intents: list[RoutingIntent] = Field(min_length=1, max_length=10)


class WorkflowStep(Contract):
    tool: Literal[
        "interpret_user_request",
        "parse",
        "propose_mapping",
        "run_normalization",
        "prepare_reconciliation_plan",
        "run_approved_reconciliation",
        "start_export",
        "query_dataset",
        "read_verified_facts",
    ]
    resource_id: str
    job_id: str | None = None
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED"]
    result_id: str | None = None


class ProgressBlock(Contract):
    type: Literal["progress"] = "progress"
    text: str


class DatasetBlock(Contract):
    type: Literal["dataset_summary"] = "dataset_summary"
    dataset_id: str
    canonical_id: str
    table_id: str
    name: str
    rows: int
    invalid_rows: int
    status: str
    transformations: list[str]


class TableBlock(Contract):
    type: Literal["table"] = "table"
    result: QueryResult


class FactsBlock(Contract):
    type: Literal["facts"] = "facts"
    result: ToolResult
    answer: AssistantAnswer | None = None


class ChartPoint(Contract):
    label: str
    value: str


class ChartBlock(Contract):
    type: Literal["chart"] = "chart"
    title: str
    unit: str
    points: list[ChartPoint] = Field(max_length=50)
    source_refs: list[str]
    verification_status: str
    completeness: Literal["COMPLETE", "TRUNCATED"] = "COMPLETE"
    population: int
    population_definition: str
    period_start: str | None = None
    period_end: str | None = None
    timezone: str | None = None


class DownloadBlock(Contract):
    type: Literal["download"] = "download"
    export_id: str
    run_id: str
    format: Literal["csv", "xlsx"]


ResultBlock = Annotated[
    ProgressBlock | DatasetBlock | TableBlock | FactsBlock | ChartBlock | DownloadBlock,
    Field(discriminator="type"),
]


class ClarificationOption(Contract):
    """A server-built choice of an existing approved query metric; never approval."""

    id: str
    label: str
    intent: AgentIntent


class ReviewRequest(Contract):
    id: str
    kind: Literal["MAPPING", "RECONCILIATION", "CLARIFICATION"]
    question: str
    reason: str
    resource_id: str
    resource_label: str | None = None
    fingerprint: str
    nonce: str
    expires_at: datetime
    state: Literal["OPEN", "DECIDED", "INVALIDATED"] = "OPEN"
    expected_effects: list[str]
    normalization_draft: NormalizationDraft | None = None
    extraction_review_required: bool | None = None
    plan: ReconciliationPlan | None = None
    suggestions: PlanningSuggestions | None = None
    planning_request: PlanningRequest | None = None
    decision_sha256: str | None = None
    result_id: str | None = None
    pending_reply_job_id: str | None = None
    reply_questions: list[str] = Field(default_factory=list, max_length=5)
    reply_intent: AgentIntent | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    options: list[ClarificationOption] = Field(default_factory=list, max_length=5)


class QuerySelection(Contract):
    """Last displayed page, separate from immutable original result blocks."""

    query: DataQuery
    group_ids: list[str] = Field(default_factory=list, max_length=50)


class WorkflowState(Contract):
    intent: AgentIntent | None = None
    steps: list[WorkflowStep] = Field(default_factory=list, max_length=12)
    reviews: list[ReviewRequest] = Field(default_factory=list, max_length=10)
    blocks: list[ResultBlock] = Field(default_factory=list, max_length=30)
    model_calls: int = 0
    error_code: str | None = None
    confirmed_mapping_ids: list[str] = Field(default_factory=list, max_length=10)
    confirmed_contract_id: str | None = None
    dataset_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    query_selection: QuerySelection | None = None


class WorkflowView(Contract):
    id: str
    conversation_id: str
    context: AssistantContext
    state: Literal[
        "CREATED",
        "RUNNING",
        "WAITING_REVIEW",
        "COMPLETED",
        "PARTIAL",
        "FAILED",
        "BLOCKED",
        "CANCELLED_BEFORE_NEXT_STEP",
    ]
    detail: WorkflowState
    updated_at: datetime


class MappingReviewDecision(Contract):
    type: Literal["MAPPING"]
    draft: NormalizationDraft
    extraction_reviewed: bool = False


class PlanReviewDecision(Contract):
    type: Literal["RECONCILIATION"]
    plan: ReconciliationPlan


class ClarificationDecision(Contract):
    type: Literal["CLARIFICATION"]
    intent: AgentIntent


class ReviewDecision(Contract):
    review_id: Identifier
    nonce: str = Field(min_length=16, max_length=64)
    fingerprint: str = Field(pattern="^[a-f0-9]{64}$")
    decision: Annotated[
        MappingReviewDecision | PlanReviewDecision | ClarificationDecision,
        Field(discriminator="type"),
    ]


class ReviewReply(Contract):
    review_id: Identifier
    nonce: str = Field(min_length=16, max_length=64)
    fingerprint: str = Field(pattern="^[a-f0-9]{64}$")
    text: str = Field(min_length=1, max_length=2000)


class ReviewInterpretation(Contract):
    """Mapping/rule là preview; clarification có intent phải kiểm lại, không cấp approval."""

    draft: NormalizationDraft | None = None
    plan: ReconciliationPlan | None = None
    intent: AgentIntent | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
