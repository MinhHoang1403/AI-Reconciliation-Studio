"""Typed handoff contracts. No storage paths or arbitrary provider JSON in public DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    PROFILED = "PROFILED"
    PREPARING = "PREPARING"
    EXPLORATION_ONLY = "EXPLORATION_ONLY"
    NEEDS_MAPPING_REVIEW = "NEEDS_MAPPING_REVIEW"
    MAPPED = "MAPPED"
    NORMALIZING = "NORMALIZING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    BLOCKED = "BLOCKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MappingStatus(StrEnum):
    PROPOSED = "PROPOSED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class WorkspacePolicy(Contract):
    mode: Literal["LOCAL_ONLY", "CLOUD_ALLOWED"] = "LOCAL_ONLY"
    allow_external_ai: bool = False
    external_request_budget: int | None = Field(default=0, ge=0)
    allow_cloud_parsing: bool = False
    parser_request_budget: int = Field(default=0, ge=0)
    parser_allowed_sha256: list[Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]] = Field(
        default_factory=list, max_length=2
    )


class Workspace(Contract):
    id: str
    name: str
    policy: WorkspacePolicy


class ProjectClassification(StrEnum):
    WORK = "WORK"
    TEST = "TEST"
    UNKNOWN = "UNKNOWN"


class Project(Contract):
    id: str
    workspace_id: str
    name: str
    business_scope: str
    classification: ProjectClassification = ProjectClassification.UNKNOWN


class Dataset(Contract):
    id: str
    workspace_id: str
    project_id: str
    name: str
    status: DatasetStatus


class DatasetVersion(Contract):
    id: str
    dataset_id: str
    file_id: str
    revision: int = Field(ge=1)
    parser_revision: str
    parse_config: dict[str, str | int | bool]


class ArtifactRef(Contract):
    id: str
    workspace_id: str
    dataset_version_id: str
    kind: Literal["raw", "parsed", "canonical", "errors", "document"]
    sha256: str
    revision: str
    quality: str


class FileArtifact(Contract):
    id: str
    workspace_id: str
    owner_id: str
    sha256: str
    filename: str
    media_type: str
    size: int


class EvidenceRef(Contract):
    id: str
    workspace_id: str
    file_id: str
    source_table_id: str
    sheet: str
    row: int | None = None
    column: str | None = None
    page: int | None = None


class SourceColumn(Contract):
    id: str
    name: str
    source_index: int


class ParsedTableArtifact(Contract):
    source_table_id: str
    artifact: ArtifactRef
    row_count: int
    columns: list[SourceColumn]
    sheet: str
    header_row: int
    provenance: list[EvidenceRef]
    warnings: list[str]
    parser_revision: str


class ColumnProfile(Contract):
    column_id: str
    name: str
    null_count: int
    empty_count: int
    distinct_count: int
    duplicate_count: int
    type_candidates: list[str]
    min_value: str | None = None
    max_value: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    samples: list[str | None]
    evidence_ids: list[str]
    identifier_candidate: bool
    observations: dict[str, int | str | list[str] | dict[str, int]] = Field(default_factory=dict)


class DatasetProfile(Contract):
    source_table_id: str
    workspace_id: str
    artifact_id: str
    row_count: int
    columns: list[ColumnProfile]
    key_candidates: list[list[str]]
    revision: str = "profile-1"


class SchemaField(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    data_type: Literal["string", "decimal", "date", "enum"]
    required: bool = False
    semantic_metric: str | None = None
    amount_basis: str | None = None
    currency: str | None = None
    unit: str | None = None


class SchemaDefinition(Contract):
    id: str
    workspace_id: str
    name: str
    revision: int = Field(ge=1)
    entity_kind: str
    grain: str
    fields: list[SchemaField] = Field(min_length=1, max_length=200)
    business_key_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_fields(self) -> "SchemaDefinition":
        ids = [f.id for f in self.fields]
        if len(ids) != len(set(ids)) or not set(self.business_key_fields) <= set(ids):
            raise ValueError("SCHEMA_FIELDS_INVALID")
        return self


class StringTransform(Contract):
    op: Literal["cast_string_preserve"]


class TrimTransform(Contract):
    op: Literal["trim_if_approved"]
    approved: Literal[True]


class DecimalTransform(Contract):
    op: Literal["parse_decimal"]
    locale: Literal["vi-VN", "en-US"]


class DateTransform(Contract):
    op: Literal["parse_date"]
    format: str = Field(min_length=2, max_length=40)
    timezone: str = Field(min_length=1, max_length=60)


class SourceDateTransform(Contract):
    op: Literal["parse_calendar_date", "parse_offset_timestamp"]
    format: str = Field(min_length=2, max_length=40)


class EnumTransform(Contract):
    op: Literal["normalize_enum"]
    mapping_id: str


class CoalesceTransform(Contract):
    op: Literal["coalesce_with_rule"]
    fields: list[str] = Field(min_length=1, max_length=20)
    rule_id: str


class ArithmeticTransform(Contract):
    op: Literal["add_fields", "subtract_fields"]
    fields: list[str] = Field(min_length=2, max_length=20)
    locale: Literal["vi-VN", "en-US"]
    rule_id: str


class AggregateTransform(Contract):
    op: Literal["aggregate_by"]
    keys: list[str] = Field(min_length=1, max_length=20)
    metric: str
    rule_id: str
    locale: Literal["vi-VN", "en-US"]


Transform = Annotated[
    StringTransform
    | TrimTransform
    | DecimalTransform
    | DateTransform
    | SourceDateTransform
    | EnumTransform
    | CoalesceTransform
    | ArithmeticTransform
    | AggregateTransform,
    Field(discriminator="op"),
]


class MappingDecision(Contract):
    source_field: str
    candidate_target: str | None
    decision: MappingStatus
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    grain_assumption: str
    transformation_candidate: Transform
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)
    reasoning: str = Field(default="", max_length=600)


class SchemaProposal(Contract):
    entity_kind: str = Field(max_length=100)
    grain: str = Field(max_length=100)
    status: Literal["PROPOSED", "UNKNOWN", "AMBIGUOUS"]
    decisions: list[MappingDecision] = Field(max_length=200)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=20)


class MappingPolicyApplication(Contract):
    revision: Literal["automatic-preparation-1"]
    source_artifact_id: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_rows: int = Field(ge=1)
    invalid_rows: int = Field(ge=0)
    error_counts: dict[str, int]
    currency_basis: Literal["SOURCE", "WORKSPACE_VND", "VND_SCOPE"]
    applied_at: datetime


class MappingRevision(Contract):
    id: str
    workspace_id: str
    source_table_id: str
    source_signature: str
    schema_id: str
    schema_revision: int
    business_scope: str
    revision: int = Field(ge=1)
    status: MappingStatus
    decisions: list[MappingDecision]
    approved_by: str | None = None
    approved_at: datetime | None = None
    rules: list["ApprovedTransformRule"] = Field(default_factory=list)
    policy_application: MappingPolicyApplication | None = Field(
        default=None, exclude_if=lambda application: application is None
    )


class ApprovedTransformRule(Contract):
    id: str
    operation: Literal[
        "normalize_enum", "coalesce_with_rule", "add_fields", "subtract_fields", "aggregate_by"
    ]
    fields: list[str]
    enum_values: dict[str, str] = Field(default_factory=dict)
    metric: str | None = None
    currency: str | None = None
    unit: str | None = None
    grain: str | None = None
    approved_by: str
    evidence_ids: list[str] = Field(min_length=1)


class SourceQualityCounts(Contract):
    """Distinct source rows per reason. One row may contribute to several reasons."""

    invalid_amount: int = 0
    missing_amount: int = 0
    invalid_date: int = 0
    missing_key: int = 0
    currency_mismatch: int = 0
    other: int = 0


SOURCE_QUALITY_LABELS = {
    "invalid_amount": "Không đọc được số tiền",
    "missing_amount": "Thiếu số tiền",
    "invalid_date": "Thiếu ngày hoặc ngày không hợp lệ",
    "missing_key": "Thiếu khóa bắt buộc",
    "currency_mismatch": "Ngoài phạm vi tiền tệ",
    "other": "Lỗi chất lượng khác",
}


def source_quality_reason(
    code: str, field: str, amounts: set[str], dates: set[str], keys: set[str]
) -> str | None:
    if code == "NULL":
        return None
    if code == "CURRENCY_MISMATCH":
        return "currency_mismatch"
    if field in amounts:
        return "missing_amount" if code == "REQUIRED_NULL" else "invalid_amount"
    if field in dates:
        return "invalid_date"
    if field in keys and code == "REQUIRED_NULL":
        return "missing_key"
    return "other"


class CanonicalDataset(Contract):
    id: str
    workspace_id: str
    dataset_version_id: str
    source_table_id: str
    schema_id: str
    schema_revision: int
    grain: str
    entity_kind: str
    mapping_revision_id: str
    normalization_revision: str
    quality_revision: int = 0
    excluded_source_rows: int = 0
    excluded_amounts: list[dict[str, str]] = Field(default_factory=list)
    excluded_amounts_unavailable: bool = False
    source_row_count: int | None = None
    row_count: int
    valid_count: int
    invalid_count: int
    quality_status: Literal["READY", "PARTIAL", "FAILED"]
    artifact: ArtifactRef
    error_artifact: ArtifactRef
    stale: bool = False


class ErrorEnvelope(Contract):
    code: str
    message_vi: str
    details: dict[str, str]
    retryable: bool
    correlation_id: str
