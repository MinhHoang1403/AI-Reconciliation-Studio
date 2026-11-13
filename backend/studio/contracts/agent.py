"""Mục tiêu, công việc và quyết định có kiểu; model không sở hữu quyền phê duyệt."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from studio.config import ModelChoice
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
    PlanningCandidate,
    PlanningRequest,
    PlanningSource,
    PlanningSourceEvidence,
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


class WorkflowPair(Contract):
    left_dataset_id: Identifier
    right_dataset_id: Identifier


class ReconciliationSequence(Contract):
    pairs: list[WorkflowPair] = Field(min_length=1, max_length=2)
    period_start: date | None = None
    period_end: date | None = None
    timezone: str | None = None


class SequenceResolution(Contract):
    sequence: ReconciliationSequence | None
    question: str | None


class SequenceProgress(Contract):
    sequence: ReconciliationSequence
    pair_index: int = Field(default=0, ge=0, le=2)
    step_start: int = Field(default=0, ge=0, le=20)
    review_start: int = Field(default=0, ge=0, le=10)
    stage: Literal["NORMALIZE", "RECONCILE", "EXPORT"] = "NORMALIZE"
    propose_pairs: bool = False
    planning_canonicals: dict[str, str] = Field(default_factory=dict, max_length=3)


class AgentIntent(Contract):
    intent: IntentName
    dataset_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    run_id: Identifier | None = None
    key_value: str | None = Field(default=None, min_length=1, max_length=200)
    result_position: int | None = Field(default=None, ge=1, le=50)
    query: DataQuery | None = None
    source_queries: list[DataQuery] = Field(
        default_factory=list, max_length=5, exclude_if=lambda value: not value
    )
    compare_source_totals: bool = Field(default=False, exclude_if=lambda value: not value)
    planning_request: PlanningRequest | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
    export_format: Literal["csv", "xlsx"] = "xlsx"
    export_scope: Literal["FULL_RUN", "DISPLAYED_QUERY"] | None = None

    @model_validator(mode="after")
    def restore_export_scope(self) -> "AgentIntent":
        """Stored exports use legacy query fields; API retains an explicit typed scope."""
        if self.intent == "EXPORT_RESULT":
            if self.export_scope is None:
                self.export_scope = "DISPLAYED_QUERY" if self.query is not None else "FULL_RUN"
            elif self.export_scope == "FULL_RUN" and self.query is not None:
                raise ValueError("Whole-run export cannot contain a displayed query")
        return self


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
    date_kind: Literal["calendar", "offset", "local"] | None = None
    date_formats: list[str] = Field(default_factory=list)


class MappingKeyCandidate(Contract):
    field_id: str
    name: str
    reference: bool
    missing_rows: int
    duplicate_rows: int


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
    currency_counts: dict[str, int] = Field(default_factory=dict)
    key_candidates: list[MappingKeyCandidate] = Field(default_factory=list)
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
    column_count: int | None = None
    prepared_artifact_id: str | None = None
    automatic_preparation: bool = Field(default=False, exclude_if=lambda value: not value)
    columns: list[SourceColumn] = Field(max_length=40)
    canonical_id: str | None = None
    canonical_status: Literal["READY", "PARTIAL", "FAILED"] | None = None
    schema_definition: SchemaDefinition | None = None
    mapping_id: str | None = None
    paid_status_fields: list[str] = Field(default_factory=list)
    approved_status_values: dict[str, list[str]] = Field(default_factory=dict)


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
    verified_pairs: dict[str, tuple[str, str]] = Field(default_factory=dict)
    status_values: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    previous_query: DataQuery | None = None
    previous_source_queries: list[DataQuery] = Field(default_factory=list, max_length=5)
    earlier_source_total: DataQuery | None = None
    previous_source_year: int | None = None
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
    source_measure_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    calendar_bucket: Literal["day", "month"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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
    export_scope: Literal["FULL_RUN", "DISPLAYED_QUERY"] | None = None


class RoutingBatch(Contract):
    intents: list[RoutingIntent] = Field(min_length=1, max_length=10)


class WorkflowStep(Contract):
    tool: Literal[
        "interpret_user_request",
        "parse",
        "propose_mapping",
        "reuse_mapping",
        "automatic_preparation",
        "run_normalization",
        "prepare_reconciliation_plan",
        "run_approved_reconciliation",
        "compare_observed",
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


class QualityDraft(Contract):
    source_row_id: str
    field: str
    code: str
    value: str
    reason: str
    row_index: int


class DatasetBlock(Contract):
    type: Literal["dataset_summary"] = "dataset_summary"
    dataset_id: str
    canonical_id: str
    table_id: str
    name: str
    rows: int
    invalid_rows: int
    excluded_rows: int = 0
    status: str
    transformations: list[str]
    show_issue_rows: bool = Field(default=False, exclude_if=lambda value: not value)
    quality_draft: QualityDraft | None = None


class TableBlock(Contract):
    type: Literal["table"] = "table"
    result: QueryResult
    title: str | None = Field(default=None, exclude_if=lambda value: value is None)


class SourceStatusLine(Contract):
    name: str
    sheet: str | None = None
    status: str
    original_rows: int | None
    canonical_rows: int | None
    valid_rows: int | None
    invalid_rows: int | None
    excluded_rows: int | None


class SourceStatusBlock(Contract):
    type: Literal["source_status"] = "source_status"
    source_count: int
    ready_count: int
    items: list[SourceStatusLine]
    totals: SourceStatusLine | None = None


class SourceValueChange(Contract):
    field: str
    original: str | None
    processed: str | None
    outcome: str


class SourceComparisonBlock(Contract):
    type: Literal["source_comparison"] = "source_comparison"
    name: str
    row: int
    scope: Literal["CANONICAL", "PREPARED", "RAW"]
    fields: list[SourceValueChange]


class FactsBlock(Contract):
    type: Literal["facts"] = "facts"
    result: ToolResult
    answer: AssistantAnswer | None = None
    observation: "ObservedPairSummary | None" = Field(
        default=None, exclude_if=lambda value: value is None
    )


class ObservedPairSummary(Contract):
    pair: str
    source_names: tuple[str, str]
    observed_start: date
    observed_end: date
    duplicate_keys: int = Field(ge=0)


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
    displayed_query: bool = False
    discrepancies_only: bool = False
    source_table: bool = Field(default=False, exclude_if=lambda value: not value)


ResultBlock = Annotated[
    ProgressBlock
    | DatasetBlock
    | TableBlock
    | SourceStatusBlock
    | SourceComparisonBlock
    | FactsBlock
    | ChartBlock
    | DownloadBlock,
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
    planning_candidates: list[PlanningCandidate] = Field(default_factory=list, max_length=5)
    source_evidence: list[PlanningSourceEvidence] = Field(default_factory=list, max_length=2)
    scope_check_pending: bool = False
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
    observed_comparison: Literal["REQUESTED", "DECLARED"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    observed_canonicals: dict[str, Identifier] = Field(
        default_factory=dict, max_length=3, exclude_if=lambda value: not value
    )
    intent: AgentIntent | None = None
    prepare_upload: bool = False
    steps: list[WorkflowStep] = Field(default_factory=list, max_length=20)
    reviews: list[ReviewRequest] = Field(default_factory=list, max_length=10)
    blocks: list[ResultBlock] = Field(default_factory=list, max_length=30)
    model_calls: int = 0
    model_choice: ModelChoice | None = None
    error_code: str | None = None
    confirmed_mapping_ids: list[str] = Field(default_factory=list, max_length=10)
    confirmed_contract_id: str | None = None
    dataset_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    query_selection: QuerySelection | None = None
    export_query: DataQuery | None = None
    source_export_bound: bool = Field(default=False, exclude_if=lambda value: not value)
    sequence_progress: SequenceProgress | None = None
    sequence_clarifications: list[str] = Field(default_factory=list, max_length=4)
    resumable_job_id: str | None = None

    @model_validator(mode="after")
    def restore_pinned_export(self) -> "WorkflowState":
        """Legacy native exports stored their scope only in export_query."""
        if (
            self.intent
            and self.intent.intent == "EXPORT_RESULT"
            and self.export_query is not None
            and self.intent.query is None
        ):
            self.intent.query = self.export_query.model_copy(deep=True)
            self.intent.export_scope = "DISPLAYED_QUERY"
        return self


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
    invalid_rows_reviewed: bool = False


class ClarificationDecision(Contract):
    type: Literal["CLARIFICATION"]
    intent: AgentIntent


class ReviewToken(Contract):
    review_id: Identifier
    nonce: str = Field(min_length=16, max_length=64)
    fingerprint: str = Field(pattern="^[a-f0-9]{64}$")


class ReviewDecision(ReviewToken):
    decision: Annotated[
        MappingReviewDecision | PlanReviewDecision | ClarificationDecision,
        Field(discriminator="type"),
    ]


class MappingReviewBatch(Contract):
    decisions: list[ReviewDecision] = Field(min_length=2, max_length=3)


class ReviewDraftUpdate(ReviewToken):
    draft: NormalizationDraft | None = None
    plan: ReconciliationPlan | None = None
    planning_request: PlanningRequest | None = None
    check_planning_scope: bool = False


class ReviewReply(ReviewToken):
    text: str = Field(min_length=1, max_length=2000)
    model_choice: ModelChoice | None = None


class ReviewInterpretation(Contract):
    """Mapping/rule là preview; clarification có intent phải kiểm lại, không cấp approval."""

    draft: NormalizationDraft | None = None
    plan: ReconciliationPlan | None = None
    intent: AgentIntent | None = None
    planning_request: PlanningRequest | None = None
    suggestions: PlanningSuggestions | None = None
    questions: list[str] = Field(default_factory=list, max_length=5)
