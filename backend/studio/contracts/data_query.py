"""Truy vấn có kiểu; không nhận SQL, mã thực thi hoặc đường dẫn từ model/client."""

from typing import Literal

from pydantic import Field, JsonValue

from studio.contracts import Contract, SourceQualityCounts
from studio.contracts.assistant import Identifier


class QueryFilter(Contract):
    field_id: Identifier
    op: Literal["eq", "ne", "in", "gt", "gte", "lt", "lte", "between", "is_null", "contains"]
    value: str | list[str] | None = Field(default=None)


class QueryAggregation(Contract):
    op: Literal["count", "count_distinct", "sum_decimal", "min", "max"]
    field_id: Identifier | None = None


class QuerySort(Contract):
    field_id: Identifier
    descending: bool = False


class QueryOperations(Contract):
    """Các phép đọc dùng chung; quyền và nguồn do boundary riêng xác định."""

    select_fields: list[Identifier] = Field(default_factory=list, max_length=20)
    filters: list[QueryFilter] = Field(default_factory=list, max_length=8)
    aggregations: list[QueryAggregation] = Field(default_factory=list, max_length=5)
    group_by: list[Identifier] = Field(default_factory=list, max_length=3)
    sort: list[QuerySort] = Field(default_factory=list, max_length=3)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=25, ge=1, le=50)
    null_policy: Literal["PRESERVE"] = "PRESERVE"
    result_scope: Literal["ALL_MATCHING"] = "ALL_MATCHING"
    currency_field: Identifier | None = None
    metric_id: Identifier | None = None


QuerySourceKind = Literal[
    "RAW_PREVIEW",
    "PREPARED",
    "PREPARED_FINDINGS",
    "PREPARED_ISSUES",
    "CANONICAL",
    "VERIFIED_RUN",
    "EXCEPTIONS",
]


class DataQuery(QueryOperations):
    project_id: Identifier
    source_kind: QuerySourceKind
    source_id: Identifier
    source_measure_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    calendar_bucket: Literal["day", "month"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    ranking_size: int | None = Field(
        default=None, ge=1, le=50, exclude_if=lambda value: value is None
    )


class SourceMeasure(Contract):
    field_id: Identifier
    name: str
    semantic_metric: str
    amount_basis: str
    currency: str
    unit: str
    grain: str


class SourceQueryEvidence(Contract):
    source_name: str
    canonical_id: Identifier
    mapping_id: Identifier
    schema_revision: int
    grain: str
    measure: SourceMeasure | None = None
    source_rows: int
    invalid_rows: int
    excluded_rows: int
    matching_rows: int
    counted_rows: int
    valid_rows: int | None = Field(default=None, exclude_if=lambda value: value is None)
    out_of_scope_rows: int | None = Field(default=None, exclude_if=lambda value: value is None)
    quality_counts: SourceQualityCounts | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    ranking_ties: int | None = Field(default=None, exclude_if=lambda value: value is None)
    observed_first: str | None = None
    observed_last: str | None = None
    sql: str


class QueryResult(Contract):
    source_kind: QuerySourceKind
    project_id: str
    source_id: str
    fields: list[str]
    field_labels: dict[str, str] = Field(default_factory=dict)
    rows: list[dict[str, JsonValue]]
    total_count: int
    offset: int
    limit: int
    truncated: bool
    input_count: int
    query: DataQuery
    result_scope: Literal["ALL_MATCHING"] = "ALL_MATCHING"
    verification_status: Literal["RAW_UNVERIFIED", "CANONICAL", "VERIFIED", "PARTIAL_VERIFIED"]
    source_refs: list[str]
    measure_units: dict[str, str] = Field(default_factory=dict)
    quality_status: str | None = None
    evidence_complete: bool = True
    warnings: list[str] = Field(default_factory=list)
    source_evidence: SourceQueryEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class SourceRowRequest(Contract):
    project_id: Identifier
    table_id: Identifier
    row: int = Field(ge=1, le=1000000)


class SourceRowResult(Contract):
    rows: list[dict[str, JsonValue]] = Field(max_length=1)
