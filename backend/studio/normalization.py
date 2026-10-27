"""F11/F12: exact, audited transformations with null/invalid separation and lineage."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import polars as pl

from studio.contracts import (
    AggregateTransform,
    ArithmeticTransform,
    CoalesceTransform,
    DateTransform,
    DecimalTransform,
    EnumTransform,
    SchemaDefinition,
    Transform,
)
from studio.errors import DomainError
from studio.schema_mapping import TransformPlan

NORMALIZATION_REVISION = "normalization-1"


def parse_decimal(raw: str | None, locale: str) -> Decimal | None:
    """Parse confirmed locale directly into Decimal, never float or rounded zero.

    Signed decimal/grouping syntax is strict; nonfinite, exponent, >38 significant
    digits or >18 fractional digits fail. Null and empty remain absent, not zero.
    """
    if raw is None or raw == "":
        return None
    patterns = {
        "vi-VN": r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?",
        "en-US": r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?",
    }
    if locale not in patterns or not re.fullmatch(patterns[locale], raw):
        raise DomainError("INVALID_DECIMAL", "Giá trị không phải Decimal theo locale đã duyệt.")
    normalized = (
        raw.replace(".", "").replace(",", ".") if locale == "vi-VN" else raw.replace(",", "")
    )
    try:
        value = Decimal(normalized)
        _check_decimal(value)
        return value
    except InvalidOperation as exc:
        raise DomainError("INVALID_DECIMAL", "Giá trị Decimal không hợp lệ.") from exc


def _check_decimal(value: Decimal) -> None:
    exponent = value.as_tuple().exponent
    if (
        not value.is_finite()
        or len(value.as_tuple().digits) > 38
        or not isinstance(exponent, int)
        or exponent < -18
    ):
        raise DomainError(
            "DECIMAL_PRECISION_EXCEEDED", "Số vượt giới hạn Decimal, không tự làm tròn."
        )
    if value.adjusted() + 1 > 38:
        raise DomainError(
            "DECIMAL_PRECISION_EXCEEDED", "Số vượt giới hạn Decimal, không tự làm tròn."
        )


def _transform(
    raw: str | None, row: dict[str, Any], transform: Transform, plan: TransformPlan
) -> Any:
    if transform.op == "cast_string_preserve":
        return raw
    if transform.op == "trim_if_approved":
        return raw.strip() if raw is not None else None
    if isinstance(transform, (DecimalTransform, AggregateTransform)):
        return parse_decimal(raw, transform.locale)
    if isinstance(transform, DateTransform):
        if raw in (None, ""):
            return None
        try:
            parsed = datetime.strptime(str(raw), transform.format)
            if parsed.tzinfo is not None:
                raise ValueError("timezone must come from approved transform")
            zone = ZoneInfo(transform.timezone)
            # Ambiguous and nonexistent local wall times must be reviewed, never guessed.
            earlier = parsed.replace(tzinfo=zone, fold=0)
            later = parsed.replace(tzinfo=zone, fold=1)
            if (
                earlier.utcoffset() != later.utcoffset()
                or earlier.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != parsed
            ):
                raise ValueError("ambiguous/nonexistent local time")
            return earlier.astimezone(UTC)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise DomainError(
                "INVALID_DATE", "Ngày hoặc múi giờ không hợp lệ/cần xác nhận."
            ) from exc
    rules = {r.id: r for r in plan.mapping.rules}
    if isinstance(transform, EnumTransform):
        if raw is None:
            return None
        if raw not in rules[transform.mapping_id].enum_values:
            raise DomainError("UNKNOWN_ENUM", "Giá trị không có trong bảng danh mục đã duyệt.")
        return rules[transform.mapping_id].enum_values[raw]
    if isinstance(transform, CoalesceTransform):
        return next((row[f] for f in transform.fields if row[f] is not None), None)
    if isinstance(transform, ArithmeticTransform):
        values = [parse_decimal(row[f], transform.locale) for f in transform.fields]
        if any(v is None for v in values):
            raise DomainError(
                "ARITHMETIC_NULL", "Phép tính thiếu đầu vào; không thay null bằng zero."
            )
        operands = [v for v in values if v is not None]
        with localcontext() as ctx:
            ctx.prec = 80
            result = operands[0]
            for value in operands[1:]:
                result = result + value if transform.op == "add_fields" else result - value
        _check_decimal(result)
        return result
    raise DomainError("TRANSFORM_NOT_ALLOWED", "Phép biến đổi chưa được đăng ký.")


@dataclass
class NormalizationResult:
    canonical: pl.DataFrame
    errors: pl.DataFrame
    quality_status: str
    row_count: int
    valid_count: int
    invalid_count: int


def apply_transform_plan(
    frame: pl.DataFrame,
    plan: TransformPlan,
    dataset_version_id: str,
    table_id: str,
    file_id: str,
    sheet: str,
) -> NormalizationResult:
    """F11: produce typed payload and complete lineage, without modifying parsed data.

    Every source row appears exactly once (including invalid rows). Approved grouping
    replaces rows with complete source-member lists. Errors preserve raw values.
    No monetary value passes through a binary float or implicit quantization.
    """
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    targets = {f.id: f for f in plan.schema.fields}
    for row in frame.iter_rows(named=True):
        payload: dict[str, Any] = {f.id: None for f in plan.schema.fields}
        flags = []
        invalid = False
        source_id = row["_source_row_id"]
        for decision in plan.mapping.decisions:
            target = decision.candidate_target
            if target is None:
                continue
            raw = row[decision.source_field]
            try:
                value = _transform(raw, row, decision.transformation_candidate, plan)
                payload[target] = value
                if value is None:
                    code = "REQUIRED_NULL" if targets[target].required else "NULL"
                    flags.append(f"{code}:{target}")
                    errors.append(
                        {
                            "source_row_id": source_id,
                            "source_row": row["_source_row"],
                            "field": target,
                            "raw_value": raw,
                            "code": code,
                            "value_state": "NULL",
                        }
                    )
                    invalid = invalid or targets[target].required
            except DomainError as exc:
                invalid = True
                flags.append(f"{exc.code}:{target}")
                errors.append(
                    {
                        "source_row_id": source_id,
                        "source_row": row["_source_row"],
                        "field": target,
                        "raw_value": raw,
                        "code": exc.code,
                        "value_state": "INVALID",
                    }
                )
        for field in plan.schema.fields:
            if field.required and payload[field.id] is None:
                invalid = True
            if (
                field.data_type == "decimal"
                and field.currency
                and payload.get("currency") not in (None, field.currency)
            ):
                invalid = True
                flags.append(f"CURRENCY_MISMATCH:{field.id}")
                errors.append(
                    {
                        "source_row_id": source_id,
                        "source_row": row["_source_row"],
                        "field": field.id,
                        "raw_value": str(payload["currency"]),
                        "code": "CURRENCY_MISMATCH",
                        "value_state": "INVALID",
                    }
                )
        records.append(
            {
                "canonical_record_id": str(uuid5(NAMESPACE_URL, f"{plan.mapping.id}:{source_id}")),
                "dataset_version_id": dataset_version_id,
                "source_table_id": table_id,
                "source_row_id": source_id,
                "workspace_id": plan.mapping.workspace_id,
                "entity_kind": plan.schema.entity_kind,
                "business_key_components": [
                    {"field": f, "value": str(payload[f]) if payload[f] is not None else None}
                    for f in plan.schema.business_key_fields
                ],
                "source_provenance": [
                    {
                        "file_id": file_id,
                        "source_table_id": table_id,
                        "source_row_id": source_id,
                        "sheet": sheet,
                        "row": row["_source_row"],
                    }
                ],
                "mapping_revision": plan.mapping.revision,
                "normalization_revision": NORMALIZATION_REVISION,
                "quality_flags": flags,
                "invalid": invalid,
                "record_payload": payload,
            }
        )
    aggregates = [
        d
        for d in plan.mapping.decisions
        if isinstance(d.transformation_candidate, AggregateTransform)
    ]
    if aggregates:
        if len(aggregates) != 1:
            raise DomainError(
                "AGGREGATE_PLAN_INVALID", "Mỗi kế hoạch chỉ nhóm một metric đã duyệt."
            )
        decision = aggregates[0]
        transform = decision.transformation_candidate
        assert isinstance(transform, AggregateTransform)
        target = str(decision.candidate_target)
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for record in records:
            key = tuple(record["record_payload"][k] for k in transform.keys)
            if any(k is None for k in key):
                raise DomainError("AGGREGATE_NULL_KEY", "Không nhóm các dòng thiếu khóa.")
            groups.setdefault(key, []).append(record)
        combined = []
        for members in groups.values():
            representative = dict(members[0])
            payload = dict(representative["record_payload"])
            if any(m["invalid"] or m["record_payload"][target] is None for m in members):
                raise DomainError(
                    "AGGREGATE_INVALID_AMOUNT", "Nhóm có số tiền lỗi/null; cần kiểm tra trước."
                )
            for field_id in targets:
                if field_id != target and len({m["record_payload"][field_id] for m in members}) > 1:
                    raise DomainError(
                        "AGGREGATE_MIXED_VALUES", "Nhóm có giá trị khác nhau ngoài metric đã duyệt."
                    )
            with localcontext() as ctx:
                ctx.prec = 80
                payload[target] = sum((m["record_payload"][target] for m in members), Decimal(0))
            _check_decimal(payload[target])
            lineage = [p for m in members for p in m["source_provenance"]]
            representative.update(
                record_payload=payload,
                source_provenance=lineage,
                canonical_record_id=str(
                    uuid5(
                        NAMESPACE_URL, ":".join(sorted(m["canonical_record_id"] for m in members))
                    )
                ),
                source_row_id="GROUP:"
                + str(uuid5(NAMESPACE_URL, ":".join(sorted(m["source_row_id"] for m in members)))),
            )
            combined.append(representative)
        records = combined
    _validate_lineage(records, frame.height)
    canonical = _typed_frame(records, plan.schema)
    error_frame = pl.DataFrame(
        errors,
        schema={
            "source_row_id": pl.String,
            "source_row": pl.Int64,
            "field": pl.String,
            "raw_value": pl.String,
            "code": pl.String,
            "value_state": pl.String,
        },
    )
    invalid_count = sum(bool(record["invalid"]) for record in records)
    quality = validate_canonical(canonical, plan.schema)
    return NormalizationResult(
        canonical, error_frame, quality, len(records), len(records) - invalid_count, invalid_count
    )


def _validate_lineage(records: list[dict[str, Any]], source_count: int) -> None:
    members = [p["source_row_id"] for r in records for p in r["source_provenance"]]
    if len(members) != source_count or len(set(members)) != source_count:
        raise DomainError("LINEAGE_CONSERVATION_FAILED", "Lineage không bảo toàn đủ dòng nguồn.")


def _typed_frame(records: list[dict[str, Any]], schema: SchemaDefinition) -> pl.DataFrame:
    payload_types: dict[str, Any] = {}
    for field in schema.fields:
        values = [
            r["record_payload"][field.id]
            for r in records
            if r["record_payload"][field.id] is not None
        ]
        if field.data_type == "decimal":
            scale = max((max(0, -v.as_tuple().exponent) for v in values), default=0)
            if any(v.adjusted() + 1 + scale > 38 for v in values):
                raise DomainError(
                    "DECIMAL_PRECISION_EXCEEDED", "Cột vượt độ chính xác Parquet Decimal."
                )
            payload_types[field.id] = pl.Decimal(38, scale)
        elif field.data_type == "date":
            payload_types[field.id] = pl.Datetime("us", "UTC")
        else:
            payload_types[field.id] = pl.String
    if not records:
        raise DomainError("EMPTY_TABLE", "Bảng không có dòng để chuẩn hóa.")
    return pl.from_dicts(
        records,
        schema_overrides={
            "record_payload": pl.Struct(payload_types),
            "quality_flags": pl.List(pl.String),
            "business_key_components": pl.List(pl.Struct({"field": pl.String, "value": pl.String})),
        },
    )


def validate_canonical(frame: pl.DataFrame, schema: SchemaDefinition) -> str:
    """F12: required nulls and conversion errors keep dataset PARTIAL, never silent zero."""
    if frame.height == 0:
        return "FAILED"
    if frame["canonical_record_id"].n_unique() != frame.height:
        raise DomainError("CANONICAL_ID_DUPLICATE", "Định danh canonical bị trùng.")
    for row in frame.iter_rows(named=True):
        if not row["source_provenance"]:
            raise DomainError("MISSING_LINEAGE", "Canonical thiếu nguồn gốc.")
        if row["invalid"] or any(
            f.required and row["record_payload"][f.id] is None for f in schema.fields
        ):
            return "PARTIAL"
    return "READY"
