"""Human decisions over a checksum-verified source and a specific canonical snapshot."""

from decimal import Decimal, localcontext
from typing import Any, Literal

import polars as pl
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.config import settings
from studio.contracts import (
    AggregateTransform,
    ArithmeticTransform,
    CanonicalDataset,
    CoalesceTransform,
    Contract,
    DatasetProfile,
    ParsedTableArtifact,
    SchemaDefinition,
)
from studio.database import (
    ArtifactRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    QualityDecisionRow,
    SchemaRow,
    TableRow,
    VersionRow,
)
from studio.errors import DomainError
from studio.normalization import NORMALIZATION_REVISION, _transform
from studio.repository import get_scoped, mapping_contract
from studio.schema_mapping import TransformPlan, compile_transform_plan
from studio.storage import checksum, storage_path


class QualityInput(Contract):
    canonical_id: str
    source_row_id: str
    field: str
    code: str
    action: Literal["REPLACE", "EXCLUDE", "KEEP_PENDING"]
    reason: str = Field(min_length=1, max_length=500)
    replacement: str | None = Field(default=None, max_length=2048)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_replacement(self) -> "QualityInput":
        if self.action == "REPLACE":
            if not self.replacement or not self.replacement.strip():
                raise ValueError("Cần nhập giá trị thay thế.")
        elif self.replacement is not None:
            raise ValueError("Chỉ thao tác sửa mới nhận giá trị thay thế.")
        return self


def artifact_scan(artifact: ArtifactRow) -> pl.LazyFrame:
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256:
        raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Artifact không khớp checksum.", 409)
    return pl.scan_parquet(path)


def decision_history(db: Session, table_id: str, revision: int) -> list[QualityDecisionRow]:
    return list(
        db.scalars(
            select(QualityDecisionRow)
            .where(
                QualityDecisionRow.source_table_id == table_id,
                QualityDecisionRow.revision <= revision,
            )
            .order_by(QualityDecisionRow.revision)
        )
    )


def adjustments(
    decisions: list[QualityDecisionRow],
) -> tuple[dict[str, dict[str, str]], set[str]]:
    replacements: dict[str, dict[str, str]] = {}
    excluded: set[str] = set()
    for entry in decisions:
        request = entry.request
        row_id = request["source_row_id"]
        if request["action"] == "REPLACE":
            replacements.setdefault(row_id, {})[entry.evidence["source_field"]] = request[
                "replacement"
            ]
        elif request["action"] == "EXCLUDE":
            excluded.add(row_id)
    return replacements, excluded


def adjusted_frame(
    frame: pl.DataFrame,
    replacements: dict[str, dict[str, str]],
    excluded: set[str],
) -> pl.DataFrame:
    for field in sorted({key for values in replacements.values() for key in values}):
        values = {row_id: row[field] for row_id, row in replacements.items() if field in row}
        frame = frame.with_columns(
            pl.col("_source_row_id")
            .replace_strict(
                values,
                default=pl.col(field),
                return_dtype=pl.String,
            )
            .alias(field)
        )
    return frame.filter(~pl.col("_source_row_id").is_in(sorted(excluded))) if excluded else frame


def excluded_amounts(
    rows: pl.DataFrame,
    plan: TransformPlan,
) -> tuple[list[dict[str, str]], bool]:
    if rows.is_empty():
        return [], False
    by_target = {item.candidate_target: item for item in plan.mapping.decisions}
    metrics = [
        field
        for field in plan.schema.fields
        if field.data_type == "decimal" and field.id in by_target
    ]
    totals: dict[tuple[str, str], Decimal] = {}
    incomplete = not metrics
    with localcontext() as context:
        context.prec = 80
        for row in rows.iter_rows(named=True):
            for field in metrics:
                decision = by_target[field.id]
                try:
                    currency_column = by_target.get("currency")
                    declared_currency = (
                        _transform(
                            row[currency_column.source_field],
                            row,
                            currency_column.transformation_candidate,
                            plan,
                        )
                        if currency_column
                        else None
                    )
                    currency = declared_currency or field.currency
                    value = _transform(
                        row[decision.source_field], row, decision.transformation_candidate, plan
                    )
                    if (
                        not isinstance(value, Decimal)
                        or not currency
                        or (field.currency and currency != field.currency)
                    ):
                        incomplete = True
                        continue
                except DomainError:
                    incomplete = True
                    continue
                key = (field.id, currency)
                totals[key] = totals.get(key, Decimal(0)) + value
    return [
        {"field": field, "currency": currency, "amount": str(amount)}
        for (field, currency), amount in sorted(totals.items())
    ], incomplete


def _context(
    db: Session,
    actor: Actor,
    table: TableRow,
    canonical_id: str,
) -> tuple[CanonicalRow, CanonicalDataset, MappingRow, pl.LazyFrame]:
    canonical = get_scoped(db, CanonicalRow, canonical_id, actor)
    if canonical.source_table_id != table.id:
        raise DomainError("ARTIFACT_SCOPE_MISMATCH", "Kết quả không thuộc bảng này.", 404)
    contract = CanonicalDataset.model_validate(canonical.contract)
    mapping = get_scoped(db, MappingRow, canonical.mapping_id, actor)
    errors = get_scoped(db, ArtifactRow, contract.error_artifact.id, actor)
    if (
        errors.kind != "errors"
        or errors.sha256 != contract.error_artifact.sha256
        or errors.dataset_version_id != table.dataset_version_id
    ):
        raise DomainError("ARTIFACT_REF_INVALID", "Artifact lỗi không khớp tham chiếu.", 409)
    return canonical, contract, mapping, artifact_scan(errors)


def _current(table: TableRow, canonical: CanonicalRow) -> bool:
    return (
        not canonical.stale
        and canonical.mapping_id == table.active_mapping_id
        and canonical.normalization_revision == NORMALIZATION_REVISION
        and canonical.quality_revision == table.quality_revision
    )


def _source_field(mapping: MappingRow, issue: dict[str, Any]) -> tuple[str | None, bool]:
    decision = next(
        (
            item
            for item in mapping_contract(mapping).decisions
            if item.candidate_target == issue["field"]
        ),
        None,
    )
    if decision is None or issue["code"] == "CURRENCY_MISMATCH":
        return None, False
    return decision.source_field, not isinstance(
        decision.transformation_candidate,
        (AggregateTransform, ArithmeticTransform, CoalesceTransform),
    )


def read_issues(
    db: Session,
    actor: Actor,
    table_id: str,
    canonical_id: str,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    table = get_scoped(db, TableRow, table_id, actor)
    canonical, contract, mapping, errors = _context(db, actor, table, canonical_id)
    actionable = errors.filter(pl.col("code") != "NULL")
    rows = actionable.select("source_row_id", "source_row").unique().sort("source_row")
    total = rows.select(pl.len()).collect().item()
    issue_counts = {
        row["code"]: row["len"]
        for row in actionable.select("source_row_id", "code")
        .unique()
        .group_by("code")
        .len()
        .collect()
        .iter_rows(named=True)
    }
    ids = rows.slice(offset, limit).collect()["source_row_id"].to_list()
    grouped: dict[str, list[dict[str, Any]]] = {row_id: [] for row_id in ids}
    for issue in actionable.filter(pl.col("source_row_id").is_in(ids)).collect().to_dicts():
        source_field, editable = _source_field(mapping, issue)
        grouped[issue["source_row_id"]].append(
            {**issue, "source_field": source_field, "editable": editable}
        )
    history = decision_history(db, table_id, canonical.quality_revision)
    reviewed = {
        item.request["source_row_id"]: item
        for item in history
        if item.request["source_row_id"] in grouped
    }
    version = db.get(VersionRow, table.dataset_version_id)
    assert version is not None
    dataset = get_scoped(db, DatasetRow, version.dataset_id, actor)
    parsed = ParsedTableArtifact.model_validate(table.parsed_contract)
    names = {column.id: column.name for column in parsed.columns}
    schema = get_scoped(db, SchemaRow, mapping.schema_id, actor)
    targets = {field["id"]: field["name"] for field in schema.definition["fields"]}
    original = {}
    if ids:
        raw = get_scoped(db, ArtifactRow, table.artifact_id, actor)
        original = {
            row["_source_row_id"]: row
            for row in artifact_scan(raw)
            .filter(pl.col("_source_row_id").is_in(ids))
            .collect()
            .to_dicts()
        }
    for issues in grouped.values():
        for issue in issues:
            issue["source_label"] = names.get(issue["source_field"])
            issue["target_label"] = targets.get(issue["field"], issue["field"])
            issue["original_value"] = original.get(issue["source_row_id"], {}).get(
                issue["source_field"], issue["raw_value"]
            )
    latest = db.scalar(
        select(CanonicalRow.id).where(
            CanonicalRow.source_table_id == table.id,
            CanonicalRow.mapping_id == table.active_mapping_id,
            CanonicalRow.quality_revision == table.quality_revision,
            CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
            CanonicalRow.stale.is_(False),
        )
    )
    recent = decision_history(db, table_id, table.quality_revision)[-1:] if latest is None else []
    job = db.get(JobRow, recent[0].job_id) if recent and recent[0].job_id else None
    return {
        "dataset": dataset.name,
        "sheet": table.sheet,
        "current": _current(table, canonical) and actor.role in {"owner", "editor"},
        "invalid_records": contract.invalid_count,
        "valid_records": contract.valid_count,
        "quality_status": contract.quality_status,
        "excluded_source_rows": contract.excluded_source_rows,
        "excluded_amounts": contract.excluded_amounts,
        "excluded_amounts_unavailable": contract.excluded_amounts_unavailable,
        "latest_id": latest,
        "job": {"id": job.id, "status": job.status} if job else None,
        "decision_history": [
            {
                "source_row": entry.evidence["source_row"],
                "field": names.get(entry.evidence["source_field"]),
                "original_value": entry.evidence["original_value"],
                "replacement": entry.request["replacement"],
                "action": entry.request["action"],
                "reason": entry.request["reason"],
                "revision": entry.revision,
            }
            for entry in reversed(history[-20:])
        ],
        "total": total,
        "issue_counts": issue_counts,
        "items": [
            {
                "source_row_id": row_id,
                "source_row": issues[0]["source_row"],
                "issues": issues,
                "pending_reason": (
                    reviewed[row_id].request["reason"]
                    if row_id in reviewed and reviewed[row_id].request["action"] == "KEEP_PENDING"
                    else None
                ),
            }
            for row_id, issues in grouped.items()
        ],
    }


def count_processing_issues(
    db: Session, actor: Actor, table_id: str, canonical_id: str, currency: str | None
) -> tuple[int, list[int]]:
    """Count distinct physical rows in the current error artifact, within one revision."""
    table = get_scoped(db, TableRow, table_id, actor)
    canonical, _, mapping, errors = _context(db, actor, table, canonical_id)
    if not _current(table, canonical):
        raise DomainError("STALE_CONTEXT", "Bản chuẩn hóa đã thay đổi.", 409)
    if currency:
        matches = errors.filter(
            (pl.col("code") == "CURRENCY_MISMATCH") & (pl.col("raw_value") == currency)
        )
    else:
        schema = get_scoped(db, SchemaRow, mapping.schema_id, actor)
        fields = {f["id"] for f in schema.definition["fields"] if f["data_type"] == "decimal"}
        matches = errors.filter(
            pl.col("code").is_in(["INVALID_DATE", "DATE_OFFSET_MISMATCH"])
            | (
                pl.col("field").is_in(sorted(fields))
                & pl.col("code").is_in(
                    ["INVALID_DECIMAL", "DECIMAL_PRECISION_EXCEEDED", "REQUIRED_NULL"]
                )
            )
        )
    rows = matches.select("source_row").unique().sort("source_row").collect()["source_row"]
    return len(rows), rows.head(10).to_list()


def record_decision(
    db: Session,
    actor: Actor,
    table_id: str,
    body: QualityInput,
    request_key: str,
) -> tuple[QualityDecisionRow, str, str]:
    table = get_scoped(db, TableRow, table_id, actor)
    require_editor(actor, db, table_id)
    db.refresh(table, with_for_update=True)
    version = db.get(VersionRow, table.dataset_version_id)
    assert version is not None
    dataset = get_scoped(db, DatasetRow, version.dataset_id, actor)
    previous = db.scalar(
        select(QualityDecisionRow).where(
            QualityDecisionRow.source_table_id == table.id,
            QualityDecisionRow.actor_id == actor.id,
            QualityDecisionRow.request_key == request_key,
        )
    )
    request = body.model_dump(mode="json")
    if previous is not None:
        if previous.request != request:
            raise DomainError("IDEMPOTENCY_CONFLICT", "Mã thao tác đã dùng cho nội dung khác.", 409)
        return previous, dataset.id, table.active_mapping_id or ""

    canonical, _, mapping, errors = _context(db, actor, table, body.canonical_id)
    if not _current(table, canonical):
        raise DomainError(
            "QUALITY_SNAPSHOT_CHANGED", "Kết quả đã đổi. Hãy mở lỗi trong bản hiện hành.", 409
        )
    found = (
        errors.filter(
            (pl.col("source_row_id") == body.source_row_id)
            & (pl.col("field") == body.field)
            & (pl.col("code") == body.code)
            & (pl.col("code") != "NULL")
        )
        .collect()
        .to_dicts()
    )
    if len(found) != 1:
        raise DomainError(
            "QUALITY_ISSUE_NOT_FOUND", "Không xác định được lỗi đã chọn trong kết quả.", 422
        )
    issue = found[0]
    field, editable = _source_field(mapping, issue)
    raw = get_scoped(db, ArtifactRow, table.artifact_id, actor)
    original = (
        artifact_scan(raw)
        .filter(pl.col("_source_row_id") == body.source_row_id)
        .collect()
        .to_dicts()
    )
    if len(original) != 1:
        raise DomainError(
            "QUALITY_SOURCE_ROW_INVALID", "Không xác định được dòng trong nguồn gốc.", 409
        )
    if body.action == "REPLACE":
        if not field or not editable:
            raise DomainError(
                "QUALITY_REPLACEMENT_UNSUPPORTED",
                "Trường này phụ thuộc quy tắc hoặc nhiều cột. Hãy kiểm tra ánh xạ.",
                422,
            )
        schema = get_scoped(db, SchemaRow, mapping.schema_id, actor)
        plan = compile_transform_plan(
            mapping_contract(mapping),
            SchemaDefinition.model_validate(schema.definition),
            DatasetProfile.model_validate(table.profile),
        )
        decision = next(
            item for item in plan.mapping.decisions if item.candidate_target == body.field
        )
        row = {**original[0], field: body.replacement}
        result = _transform(body.replacement, row, decision.transformation_candidate, plan)
        if result is None:
            raise DomainError(
                "QUALITY_REPLACEMENT_INVALID", "Giá trị thay thế vẫn rỗng sau khi chuẩn hóa.", 422
            )
    if (
        body.action == "EXCLUDE"
        and table.row_count <= canonical.contract.get("excluded_source_rows", 0) + 1
    ):
        raise DomainError(
            "QUALITY_EXCLUSION_EMPTY", "Phải giữ ít nhất một dòng nguồn trong phạm vi.", 422
        )
    table.quality_revision += 1
    db.execute(
        update(CanonicalRow)
        .where(CanonicalRow.source_table_id == table.id, CanonicalRow.stale.is_(False))
        .values(stale=True)
    )
    dataset.status = "PARTIAL"
    entry = QualityDecisionRow(
        source_table_id=table.id,
        revision=table.quality_revision,
        actor_id=actor.id,
        request_key=request_key,
        request=request,
        evidence={
            **issue,
            "source_field": field,
            "original_value": original[0].get(field) if field else None,
        },
    )
    db.add(entry)
    db.flush()
    return entry, dataset.id, mapping.id
