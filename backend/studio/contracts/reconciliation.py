"""Approved reconciliation boundaries; decimal values never accept binary floats.

Plans grant no execution authority. Approval binds scoped canonical revisions;
verified publication requires independent checks and a single immutable snapshot.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from studio.contracts import (
    CanonicalDataset,
    Contract,
    DatasetProfile,
    MappingRevision,
    SchemaDefinition,
)


def exact_decimal(value: Any) -> Any:
    if isinstance(value, float | bool):
        raise ValueError("BINARY_FLOAT_FORBIDDEN")
    return value


Money = Annotated[Decimal, BeforeValidator(exact_decimal), Field(allow_inf_nan=False)]
LinkageState = Literal["LINKED", "UNMATCHED", "AMBIGUOUS", "INVALID", "OUT_OF_SCOPE", "PENDING"]
ComparisonState = Literal[
    "EQUAL",
    "WITHIN_TOLERANCE",
    "AMOUNT_MISMATCH",
    "ATTRIBUTE_MISMATCH",
    "NOT_COMPARABLE",
    "NOT_EVALUATED",
]
WorkflowState = Literal["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED_WITH_REASON"]


class SourceSelection(Contract):
    canonical_id: str
    role: str = Field(min_length=1, max_length=100)
    date_field: str
    time_basis: str = Field(min_length=1, max_length=100)
    currency_field: str | None = None
    filters: dict[str, str] = Field(default_factory=dict, max_length=8)
    coverage_start: date
    coverage_end: date
    completeness: Literal["CONFIRMED", "INCOMPLETE", "UNKNOWN"]
    snapshot_at: datetime
    settlement_due_at: datetime | None = None


class FieldPair(Contract):
    left: str
    right: str


class ComparisonMetric(FieldPair):
    metric_id: str = Field(min_length=1, max_length=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit: str = Field(min_length=1, max_length=40)
    amount_basis: str = Field(min_length=1, max_length=100)
    sign_convention: Literal["SOURCE_SIGNED"]
    absolute_tolerance: Money = Field(default=Decimal(0), ge=0, max_digits=38, decimal_places=18)
    relative_tolerance: Money | None = Field(default=None, ge=0, le=1, decimal_places=18)
    rounding_scale: int | None = Field(default=None, ge=0, le=18)
    rounding_mode: Literal["HALF_UP", "HALF_EVEN"] = "HALF_EVEN"


class ReconciliationPlan(Contract):
    name: str = Field(min_length=1, max_length=160)
    entity_kind: str = Field(min_length=1, max_length=100)
    left: SourceSelection
    right: SourceSelection
    join_keys: list[FieldPair] = Field(min_length=1, max_length=8)
    comparison_metrics: list[ComparisonMetric] = Field(min_length=1, max_length=5)
    attributes: list[FieldPair] = Field(default_factory=list, max_length=8)
    comparison_grain: str = Field(min_length=1, max_length=200)
    cardinality: Literal["ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE"]
    aggregation: Literal["NONE", "SUM_SIGNED"]
    period_start: date
    period_end: date
    timezone: str
    effective_from: date
    effective_to: date | None = None
    allow_partial: bool = False
    duplicate_policy: Literal["REVIEW"] = "REVIEW"
    fuzzy_fields: list[FieldPair] = Field(default_factory=list, max_length=2)
    fuzzy_block_keys: list[FieldPair] = Field(default_factory=list, max_length=4)
    fuzzy_min_score: int = Field(default=85, ge=0, le=100)
    fuzzy_top_k: int = Field(default=3, ge=1, le=5)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unambiguous_structure(self) -> "ReconciliationPlan":
        if (
            self.left.canonical_id == self.right.canonical_id
            or self.period_start >= self.period_end
        ):
            raise ValueError("SOURCES_OR_PERIOD_INVALID")
        if self.effective_to is not None and self.effective_from >= self.effective_to:
            raise ValueError("EFFECTIVE_PERIOD_INVALID")
        for side in ("left", "right"):
            keys = [getattr(p, side) for p in self.join_keys]
            if len(keys) != len(set(keys)):
                raise ValueError("DUPLICATE_JOIN_FIELD")
        ids = [m.metric_id for m in self.comparison_metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_METRIC")
        return self


class PlanProposal(Contract):
    status: Literal["PROPOSED", "UNKNOWN", "NEEDS_REVIEW"]
    plan: ReconciliationPlan | None = None
    missing_requirements: list[str] = Field(default_factory=list, max_length=30)
    reasoning: str = Field(default="", max_length=2000)


class ReconciliationContract(Contract):
    id: str
    workspace_id: str
    project_id: str
    revision: int = Field(ge=1)
    plan: ReconciliationPlan
    status: Literal["APPROVED"] = "APPROVED"
    approved_by: str
    approved_at: datetime


class SourceCatalogue(Contract):
    project_id: str
    name: str
    canonical: CanonicalDataset
    schema_definition: SchemaDefinition
    identifier_fields: list[str]
    profile: DatasetProfile | None = None
    mapping: MappingRevision | None = None


class SourceLocation(Contract):
    file_id: str
    source_table_id: str
    source_row_id: str
    sheet: str
    row: int


class CanonicalRecord(Contract):
    id: str
    payload: dict[str, Any]
    invalid: bool
    quality_flags: list[str]
    provenance: list[SourceLocation] = Field(min_length=1)


class MatchMember(Contract):
    side: Literal["left", "right"]
    canonical_id: str
    record_id: str
    evidence: list[SourceLocation] = Field(min_length=1)


class ComparisonResult(Contract):
    metric_id: str
    currency: str
    unit: str
    left_amount: Money | None = None
    right_amount: Money | None = None
    delta: Money | None = None
    absolute_variance: Money | None = None
    tolerance: Money | None = None
    state: ComparisonState


class CandidateLink(Contract):
    left_record_id: str
    right_record_id: str
    score: float = Field(ge=0, le=100)
    status: Literal["REVIEW_ONLY"] = "REVIEW_ONLY"
    field_pairs: list[FieldPair]


class MatchGroup(Contract):
    id: str
    key: list[str | None]
    members: list[MatchMember] = Field(min_length=1)
    linkage_state: LinkageState
    comparison_state: ComparisonState
    comparisons: list[ComparisonResult] = Field(default_factory=list)
    exception_types: list[str] = Field(default_factory=list)
    candidates: list[CandidateLink] = Field(default_factory=list)
    algorithm: str


class MatchResult(Contract):
    engine_revision: str
    groups: list[MatchGroup]
    partition_counts: dict[str, dict[str, int]]
    warnings: list[str] = Field(default_factory=list)


class RateMetric(Contract):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percent: str | None


class MonetarySummary(Contract):
    metric_id: str
    currency: str
    unit: str
    comparable_groups: int
    signed_variance: Money
    absolute_variance: Money


class MetricSnapshot(Contract):
    id: str
    run_id: str
    revision: str
    rule_id: str
    rule_revision: int
    period_start: date
    period_end: date
    timezone: str
    source_canonical_ids: list[str]
    comparison_unit: str
    eligible_definition: str
    eligible_units: int
    full_match_rate: RateMetric
    linkage_rate: RateMetric
    exception_rate: RateMetric
    automation_coverage: RateMetric
    review_rate: RateMetric
    monetary: list[MonetarySummary]
    linkage_counts: dict[str, int]
    comparison_counts: dict[str, int]
    excluded_counts: dict[str, int]
    unresolved_cases_at_run: int


class VerificationCheck(Contract):
    name: str
    passed: bool
    details: str


class ReconciliationRun(Contract):
    id: str
    workspace_id: str
    project_id: str
    contract_id: str
    status: Literal[
        "DRAFT", "RUNNING", "VERIFICATION_FAILED", "PARTIAL_VERIFIED", "VERIFIED", "BLOCKED"
    ]
    engine_revision: str
    source_refs: list[CanonicalDataset]
    checks: list[VerificationCheck] = Field(default_factory=list)
    metric_snapshot: MetricSnapshot | None = None
    result_ref: "RunArtifactRef | None" = None


class RunArtifactRef(Contract):
    id: str
    workspace_id: str
    project_id: str
    run_id: str
    kind: Literal["matches"] = "matches"
    sha256: str
    revision: str


class VerifiedRun(ReconciliationRun):
    status: Literal["PARTIAL_VERIFIED", "VERIFIED"]
    metric_snapshot: MetricSnapshot


class ExceptionCase(Contract):
    id: str
    workspace_id: str
    project_id: str
    run_id: str
    match_group_id: str
    type: str
    severity_basis: str
    workflow_state: WorkflowState = "OPEN"
    notes: str = Field(default="", max_length=2000)
    evidence_ids: list[str]
    rule_id: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
