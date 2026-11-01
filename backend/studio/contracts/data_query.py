"""Truy vấn có kiểu; không nhận SQL, mã thực thi hoặc đường dẫn từ model/client."""

from typing import Literal

from pydantic import Field, JsonValue

from studio.contracts import Contract
from studio.contracts.assistant import Identifier


class QueryFilter(Contract):
    field_id: Identifier
    op: Literal["eq", "ne", "in", "gt", "gte", "lt", "lte", "between", "is_null", "contains"]
    value: str | list[str] | None = Field(default=None)


class QueryAggregation(Contract):
    op: Literal["count", "sum_decimal", "min", "max"]
    field_id: Identifier | None = None


class QuerySort(Contract):
    field_id: Identifier
    descending: bool = False


class DataQuery(Contract):
    project_id: Identifier
    source_kind: Literal["RAW_PREVIEW", "CANONICAL", "VERIFIED_RUN", "EXCEPTIONS"]
    source_id: Identifier
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


class QueryResult(Contract):
    source_kind: Literal["RAW_PREVIEW", "CANONICAL", "VERIFIED_RUN", "EXCEPTIONS"]
    project_id: str
    source_id: str
    fields: list[str]
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
    evidence_complete: bool = True
    warnings: list[str] = Field(default_factory=list)
