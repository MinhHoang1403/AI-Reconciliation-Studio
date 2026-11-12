"""Kiểm chứng draft trên toàn bảng, không approval hoặc công bố canonical."""

import re
from collections import Counter
from typing import Any, Literal
from uuid import uuid4

import polars as pl
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.agent_preparation import (
    approval_from_draft,
    profiled_fields,
    profiled_type,
    tax_amount_basis,
    validate_draft,
)
from studio.contracts import DatasetProfile, MappingRevision, SourceColumn
from studio.contracts.agent import (
    MappingAssessment,
    MappingCheck,
    MappingKeyCandidate,
    NormalizationDraft,
    RelatedKeyCheck,
)
from studio.contracts.api import ApprovalInput, NormalizationPreflight
from studio.date_parsing import (
    date_format,
    date_zone,
    parse_date,
    parse_source_date,
    source_date_operation,
)
from studio.errors import DomainError
from studio.normalization import apply_transform_plan, parse_decimal
from studio.profiling import (
    field_name_tokens,
    normalized_name,
    observed_amount_basis,
    observed_decimal_locale,
    profile_table,
)
from studio.schema_mapping import TransformPlan, compile_transform_plan

UNKNOWN = {"", "unknown", "ambiguous", "n/a", "none", "needs_review"}
AUTOMATIC_PREPARATION_REVISION = "automatic-preparation-1"
KEY_GRAINS = (
    ({"sale", "line"}, "Bán hàng", "Một dòng hàng trên đơn bán"),
    ({"receipt"}, "Thu ngân", "Một phiếu thu"),
    ({"journal", "entry"}, "Kế toán", "Một bút toán"),
)


def suggest_row_key(draft: NormalizationDraft, candidates: list[MappingKeyCandidate]) -> None:
    selected = {f.source_field for f in draft.fields if f.business_key}
    references = {c.field_id for c in candidates if c.reference}
    if selected - references:
        return
    matches = []
    for candidate in candidates:
        if candidate.reference or candidate.missing_rows or candidate.duplicate_rows:
            continue
        tokens = set(field_name_tokens(candidate.name))
        for role, entity, grain in KEY_GRAINS:
            if role | {"id"} <= tokens and not tokens & {"customer", "supplier", "sku"}:
                matches.append((candidate.field_id, entity, grain, role))
    if len(matches) != 1:
        return
    field_id, entity, grain, role = matches[0]
    if draft.grain.strip().casefold() in UNKNOWN:
        draft.grain = grain
    elif draft.grain != grain and not role <= set(field_name_tokens(draft.grain)):
        return
    if draft.entity_kind.strip().casefold() in UNKNOWN:
        draft.entity_kind = entity
    for field in draft.fields:
        field.business_key = field.source_field == field_id


def assess_mapping(
    draft: NormalizationDraft,
    frame: pl.DataFrame,
    profile: DatasetProfile,
    source_sha: str,
    *,
    enrich: bool = False,
    preserve_timezone: bool = False,
    automatic: bool = False,
) -> MappingAssessment:
    """Đo toàn bảng; chỉ enrich bản đề xuất, không sửa quyết định đã được người dùng chọn.

    [D] Chỉ format/locale duy nhất có bằng chứng mới được điền. Grain, timezone,
    gross/net của amount mơ hồ vẫn cần xác nhận. Không dùng confidence của LLM.
    """
    if not enrich:
        validate_draft(draft, profile.source_table_id, profile)
    draft = draft.model_copy(deep=True)
    fresh = profile_table(
        frame,
        [
            SourceColumn(id=c.column_id, name=c.name, source_index=i + 1)
            for i, c in enumerate(profile.columns)
        ],
        profile.source_table_id,
        profile.workspace_id,
        profile.artifact_id,
    )
    columns = {c.column_id: c for c in fresh.columns}
    if enrich:
        for field in draft.fields:
            column = columns.get(field.source_field)
            if column is None:
                continue
            if field.data_type == "decimal" and column.identifier_candidate:
                field.data_type = "string"
                field.semantic_metric = field.amount_basis = field.currency = field.unit = None
                field.locale = None
            elif (
                field.data_type == "string"
                and not field.business_key
                and tax_amount_basis(column.name)
            ):
                field.data_type = profiled_type(column, normalized_name(column.name))
        validate_draft(draft, profile.source_table_id, fresh)
    checks = []
    questions = []
    key_candidates = [
        MappingKeyCandidate(
            field_id=c.column_id,
            name=f.name,
            reference=bool(
                set(field_name_tokens(c.name)) & {"reference", "order", "tracking"}
                and not {"sale", "line"} <= set(field_name_tokens(c.name))
            ),
            missing_rows=c.null_count + c.empty_count,
            duplicate_rows=c.duplicate_count,
        )
        for f in draft.fields
        if f.data_type == "string"
        and ((c := columns[f.source_field]).identifier_candidate or f.business_key)
    ]
    currency_columns = [c for c in fresh.columns if field_name_tokens(c.name) == ("currency",)]
    currency_counts: Counter[str] = Counter()
    for column in currency_columns:
        currency_counts.update(value for value in frame[column.column_id].drop_nulls() if value)
    currencies = set(currency_counts)
    foreign_hint = any(
        re.search(
            r"\b(?:usd|eur|gbp|jpy|cny|krw|sgd|thb|aud|cad|chf|hkd)\b|[\$€£¥]",
            normalized_name(c.name).replace("_", " "),
        )
        or (
            isinstance(observed := c.observations.get("currency_counts"), dict)
            and set(observed) - {"VND"}
        )
        for c in fresh.columns
    )
    if enrich and len(currency_columns) == 1:
        currency_field = next(
            f for f in draft.fields if f.source_field == currency_columns[0].column_id
        )
        # Bind the new proposal to the existing per-row currency check. Keep
        # the raw column and any existing conflicting target intact.
        if currency_field.data_type == "string" and not any(
            f.target_id == "currency" and f is not currency_field for f in draft.fields
        ):
            currency_field.target_id = "currency"
    currency_bound = len(currency_columns) == 1 and any(
        f.target_id == "currency"
        and f.data_type == "string"
        and f.source_field == currency_columns[0].column_id
        for f in draft.fields
    )
    if enrich:
        suggest_row_key(draft, key_candidates)
    for f in draft.fields:
        c = columns[f.source_field]
        notes: list[str] = []
        pending: list[str] = []
        errors: Counter[str] = Counter()
        name = normalized_name(c.name).replace("_", " ")
        dates = c.observations.get("date_formats", {})
        date_options = (
            sorted(dates, key=lambda fmt: dates[fmt], reverse=True)
            if isinstance(dates, dict)
            else []
        )
        date_kind = None
        if enrich:
            if f.data_type == "date" and not preserve_timezone:
                f.timezone = None
            # Khóa khách hàng không tự trở thành khóa giao dịch; uniqueness không chứng minh grain.
            if f.business_key and (
                (
                    any(w in name for w in ("customer", "khach"))
                    and not any(w in normalized_name(draft.grain) for w in ("customer", "khach"))
                )
                or any(w in name for w in ("status", "trang thai", "description"))
                or c.null_count
                or c.empty_count
            ):
                f.business_key = False
                notes.append("Đã bỏ gợi ý khóa: chưa có bằng chứng khóa theo ý nghĩa mỗi dòng.")
            if isinstance(dates, dict) and dates and not c.identifier_candidate:
                maximum = max(dates.values())
                best = [fmt for fmt, count in dates.items() if count == maximum]
                if len(best) == 1 and (
                    f.data_type == "date"
                    or set(field_name_tokens(c.name)) & {"date", "timestamp", "time"}
                ):
                    f.data_type, f.date_format = "date", best[0]
                    notes.append(f"Ngày đọc được: {maximum}/{c.observations['nonempty_count']}.")
                elif f.data_type == "date" and len(best) > 1:
                    f.date_format = None
            if f.data_type == "decimal":
                locales = c.observations.get("numeric_locales", {})
                if automatic:
                    f.locale = observed_decimal_locale(
                        frame[f.source_field], locales if isinstance(locales, dict) else {}
                    )
                elif isinstance(locales, dict) and locales:
                    maximum = max(locales.values())
                    best = [loc for loc, count in locales.items() if count == maximum]
                    if maximum and len(best) == 1:
                        f.locale = best[0]  # type: ignore[assignment]
                    elif maximum and len(best) > 1:
                        equivalent = True
                        for value in frame[f.source_field]:
                            try:
                                if parse_decimal(value, "en-US") != parse_decimal(value, "vi-VN"):
                                    equivalent = False
                                    break
                            except DomainError:
                                continue
                        f.locale = "en-US" if equivalent else None
                    elif f.locale is None and maximum == 0:
                        pending.append(
                            "Không tìm thấy định dạng số có thể đọc; kiểm tra cột nguồn."
                        )
                if (
                    currency_bound
                    and len(currencies) == 1
                    and all(re.fullmatch(r"[A-Z]{3}", code) for code in currencies)
                ):
                    code = next(iter(currencies))
                    f.unit = code if not f.unit or f.unit == f.currency else f.unit
                    f.currency = code
                elif currency_columns:
                    # Không chọn đa số, mã không đúng dạng hoặc cột bị xung đột.
                    f.currency = f.unit = None
                elif not foreign_hint and not f.currency:
                    f.currency = "VND"
                    f.unit = f.unit or "VND"
                basis = (f.amount_basis or "").strip().casefold()
                tax_basis = tax_amount_basis(c.name)
                if tax_basis:
                    f.amount_basis = tax_basis
                    f.semantic_metric = f.target_id
                elif name in {"amount", "total", "so tien", "tong"} or (
                    basis in {"gross", "net"} and observed_amount_basis(c.name) != basis
                ):
                    f.amount_basis = None
        if (
            f.business_key
            and any(w in name for w in ("customer", "khach"))
            and not any(w in normalized_name(draft.grain) for w in ("customer", "khach"))
        ):
            pending.append(
                "Mã khách hàng chưa có bằng chứng làm khóa cho grain này. "
                "Kiểm tra và bỏ chọn khóa nếu không phù hợp."
            )
        if f.business_key:
            notes.append(
                f"Khóa đề xuất: {c.null_count + c.empty_count} giá trị thiếu; "
                f"{c.duplicate_count} giá trị lặp. Cần kiểm tra grain."
            )
        if f.data_type == "date":
            operation = None
            if not f.date_format:
                pending.append("Chọn định dạng ngày dựa vào dữ liệu nguồn.")
            else:
                try:
                    canonical_format = date_format(f.date_format)
                    operation = source_date_operation(canonical_format)
                    date_kind = {
                        "parse_calendar_date": "calendar",
                        "parse_offset_timestamp": "offset",
                        "parse_date": "local",
                    }[operation]
                    if enrich:
                        f.date_format = canonical_format
                except DomainError as exc:
                    pending.append(exc.message_vi)
            if operation == "parse_date":
                if not f.timezone:
                    pending.append("Xác nhận múi giờ của thời điểm nguồn; UTC là đề xuất mặc định.")
                else:
                    try:
                        date_zone(f.timezone)
                    except DomainError as exc:
                        pending.append(exc.message_vi)
            if f.date_format and operation and not pending:
                for value in frame[f.source_field]:
                    try:
                        if operation == "parse_date":
                            assert f.timezone is not None
                            parse_date(value, f.date_format, f.timezone)
                        else:
                            parse_source_date(value, f.date_format, operation)
                    except DomainError as exc:
                        errors[exc.code] += 1
        elif f.data_type == "decimal":
            if any(
                (value or "").strip().casefold() in UNKNOWN
                for value in (f.semantic_metric, f.amount_basis, f.currency, f.unit, f.locale)
            ):
                pending.append("Xác nhận ý nghĩa, cơ sở số tiền và tiền tệ còn thiếu.")
            if currency_columns and not currency_bound:
                pending.append("Cần ánh xạ cột tiền tệ để kiểm tra đơn vị trên từng dòng.")
            if len(currencies) > 1:
                notes.append(
                    "Nguồn có nhiều tiền tệ: "
                    + ", ".join(sorted(currencies))
                    + ". Field tiền dùng một tiền tệ; giá trị khác là CURRENCY_MISMATCH. "
                    "Không chuyển đổi hoặc loại bỏ."
                )
            if f.locale:
                for value in frame[f.source_field]:
                    try:
                        parse_decimal(value, f.locale)
                    except DomainError as exc:
                        errors[exc.code] += 1
        if errors and sum(errors.values()) == frame.height - c.null_count - c.empty_count:
            pending.append(
                "Toàn bộ giá trị có dữ liệu không chuyển được; sửa đề xuất trước khi duyệt."
            )
        questions.extend(pending)
        checks.append(
            MappingCheck(
                field_id=f.source_field,
                name=f.name,
                state=(
                    "BLOCKED"
                    if errors
                    and sum(errors.values()) == frame.height - c.null_count - c.empty_count
                    else "NEEDS_CONFIRMATION"
                    if pending
                    else "VERIFIED"
                ),
                messages=notes + pending,
                error_counts=dict(errors),
                affected_rows=sum(errors.values()),
                date_kind=date_kind,
                date_formats=date_options if f.data_type == "date" else [],
            )
        )
    if draft.entity_kind.strip().lower() in {
        "unknown",
        "ambiguous",
        "",
    } or draft.grain.strip().lower() in {"unknown", "ambiguous", ""}:
        questions.append("Xác nhận loại dữ liệu và mỗi dòng đại diện cho điều gì.")
    result = MappingAssessment(
        draft=draft,
        source_rows=frame.height,
        verified_fields=sum(c.state == "VERIFIED" for c in checks),
        pending_fields=sum(c.state != "VERIFIED" for c in checks),
        checks=checks,
        questions=list(dict.fromkeys(questions)),
        preflight_ready=not questions,
        source_sha256=source_sha,
        currencies=sorted(currencies),
        currency_counts=dict(currency_counts),
        key_candidates=key_candidates,
    )
    if not questions:
        approval = approval_from_draft(draft, fresh, True, automatic=automatic)
        # Mapping chỉ tồn tại trong bộ nhớ để dùng chung compiler; không ghi approval giả vào DB.
        decisions = [d.model_copy(update={"decision": "APPROVED"}) for d in approval.decisions]
        mapping = MappingRevision(
            id=str(uuid4()),
            workspace_id=fresh.workspace_id,
            source_table_id=draft.table_id,
            source_signature="preflight",
            schema_id=approval.schema_definition.id,
            schema_revision=1,
            business_scope="preflight",
            revision=1,
            status="APPROVED",
            decisions=decisions,
            approved_by="preflight-only",
        )
        plan = compile_transform_plan(mapping, approval.schema_definition, fresh)
        invalid, counts, _ = preflight_rows(frame, plan)
        result.predicted_invalid_rows = invalid
        result.error_counts = dict(counts)
    return result


def automatic_mapping(
    frame: pl.DataFrame,
    profile: DatasetProfile,
    source_sha: str,
    *,
    currency_scope: str,
) -> tuple[MappingAssessment, Literal["SOURCE", "WORKSPACE_VND", "VND_SCOPE"]]:
    """[D] Only independently observed structure can authorize an automatic mapping.

    Model output never enters this gate. Unknown grain, an unproven currency,
    missing monetary semantics or local timestamps remain in the prepared view.
    """
    draft = NormalizationDraft(
        table_id=profile.source_table_id,
        entity_kind="unknown",
        grain="unknown",
        fields=profiled_fields(profile),
    )
    columns = {c.column_id: c for c in profile.columns}
    for field in draft.fields:
        if field.data_type == "decimal" and (
            basis := observed_amount_basis(columns[field.source_field].name)
        ):
            field.amount_basis, field.semantic_metric = basis, field.target_id
    assessment = assess_mapping(draft, frame, profile, source_sha, enrich=True, automatic=True)
    money = [field for field in assessment.draft.fields if field.data_type == "decimal"]
    currency_basis: Literal["SOURCE", "WORKSPACE_VND", "VND_SCOPE"] = "SOURCE"
    if not assessment.currencies:
        currency_basis = "WORKSPACE_VND"
        if currency_scope != "VND":
            assessment.preflight_ready = False
            assessment.questions.append("Chưa có quy ước tiền tệ cho nguồn này.")
    elif (
        len(assessment.currencies) > 1
        and currency_scope == "VND"
        and "VND" in assessment.currencies
        and all(re.fullmatch(r"[A-Z]{3}", code) for code in assessment.currencies)
    ):
        currency_basis = "VND_SCOPE"
        for field in money:
            field.currency = field.unit = "VND"
        assessment = assess_mapping(assessment.draft, frame, profile, source_sha, automatic=True)
    if (
        not money
        or not any(field.business_key for field in assessment.draft.fields)
        or not any(field.data_type == "date" for field in assessment.draft.fields)
        or any(check.date_kind == "local" for check in assessment.checks)
        or assessment.predicted_invalid_rows == frame.height
        or bool(assessment.currencies and sum(assessment.currency_counts.values()) != frame.height)
    ):
        assessment.preflight_ready = False
        assessment.questions.append("Cần căn cứ về mã nhận diện dòng, ngày và chỉ tiêu tiền.")
    return assessment, currency_basis


def assess_table_mapping(
    db: Session,
    actor: Actor,
    draft: NormalizationDraft,
    *,
    enrich: bool = False,
    preserve_timezone: bool = False,
) -> MappingAssessment:
    """Đọc artifact scoped/checksum, không ghi DB hoặc gọi provider."""
    from studio.config import settings
    from studio.database import ArtifactRow, TableRow
    from studio.repository import get_scoped
    from studio.storage import checksum, storage_path

    table = get_scoped(db, TableRow, draft.table_id, actor)
    artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256:
        raise DomainError("PARSED_CHECKSUM_MISMATCH", "Dữ liệu nguồn không khớp checksum.")
    frame = pl.read_parquet(path)
    result = assess_mapping(
        draft,
        frame,
        DatasetProfile.model_validate(table.profile),
        artifact.sha256,
        enrich=enrich,
        preserve_timezone=preserve_timezone,
    )
    from sqlalchemy import select

    from studio.database import DatasetRow, VersionRow
    from studio.repository import project_for_table
    from studio.resource_lifecycle import active_source

    project = project_for_table(db, table)
    others = db.execute(
        select(TableRow, DatasetRow.name)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .join(DatasetRow, DatasetRow.id == VersionRow.dataset_id)
        .where(
            DatasetRow.project_id == project.id,
            active_source(),
            TableRow.id != table.id,
            TableRow.workspace_id == actor.workspace_id,
        )
        .limit(6)
    ).all()
    # Chỉ phân tích phạm vi nhỏ; không tự chọn một vài nguồn trong project lớn.
    if len(others) <= 5:
        for other, name in others:
            a = get_scoped(db, ArtifactRow, other.artifact_id, actor)
            other_path = storage_path(settings.storage_root, a.storage_key)
            if checksum(other_path) != a.sha256:
                raise DomainError(
                    "PARSED_CHECKSUM_MISMATCH", "Nguồn liên quan không khớp checksum."
                )
            right = pl.read_parquet(other_path)
            result.related_keys.extend(
                compare_key_candidates(frame, table.profile, right, other.profile, other.id, name)
            )
    return result


def preflight_approval(
    db: Session, actor: Actor, table_id: str, body: ApprovalInput
) -> NormalizationPreflight:
    """Compiler và transform thật trong bộ nhớ, không lưu mapping/canonical hoặc audit approval."""
    from studio.config import settings
    from studio.database import ArtifactRow, TableRow
    from studio.repository import get_scoped
    from studio.storage import checksum, storage_path

    table = get_scoped(db, TableRow, table_id, actor)
    artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256:
        raise DomainError("PARSED_CHECKSUM_MISMATCH", "Dữ liệu nguồn không khớp checksum.")
    schema = body.schema_definition.model_copy(update={"workspace_id": actor.workspace_id})
    mapping = MappingRevision(
        id="preflight",
        workspace_id=actor.workspace_id,
        source_table_id=table_id,
        source_signature="preflight",
        schema_id=schema.id,
        schema_revision=schema.revision,
        business_scope="preflight",
        revision=1,
        status="APPROVED",
        approved_by=actor.id,
        decisions=[
            d.model_copy(update={"decision": "APPROVED", "grain_assumption": schema.grain})
            for d in body.decisions
        ],
        rules=[r.model_copy(update={"approved_by": actor.id}) for r in body.rules],
    )
    plan = compile_transform_plan(mapping, schema, DatasetProfile.model_validate(table.profile))
    frame = pl.read_parquet(path)
    invalid, counts, failed_fields = preflight_rows(frame, plan)
    for d in mapping.decisions:
        if d.transformation_candidate.op not in {
            "parse_date",
            "parse_calendar_date",
            "parse_offset_timestamp",
            "parse_decimal",
        }:
            continue
        nonempty = frame.filter(
            pl.col(d.source_field).is_not_null() & (pl.col(d.source_field) != "")
        ).height
        failed = failed_fields[str(d.candidate_target)]
        if nonempty and failed == nonempty:
            raise DomainError(
                "MAPPING_TRANSFORM_ALL_FAILED",
                "Toàn bộ giá trị của một trường không chuyển được. "
                "Kiểm tra quy tắc trước khi duyệt.",
            )
    return NormalizationPreflight(
        source_rows=frame.height,
        predicted_invalid_rows=invalid,
        error_counts=dict(counts),
        source_sha256=artifact.sha256,
    )


def preflight_rows(
    frame: pl.DataFrame, plan: TransformPlan
) -> tuple[int, Counter[str], Counter[str]]:
    """Kiểm đủ mọi dòng bằng engine thật, chỉ giữ counters giữa các lô nhỏ.

    Không chia lô aggregate vì phải giữ đủ nhóm/lineage để kiểm chứng phép nhóm.
    Không công bố kết quả và không cắt mất dòng khi vượt kích thước lô.
    """
    aggregate = any(d.transformation_candidate.op == "aggregate_by" for d in plan.mapping.decisions)
    batches = [frame] if aggregate else frame.iter_slices(2000)
    invalid, counts, failed_fields = 0, Counter[str](), Counter[str]()
    for batch in batches:
        output = apply_transform_plan(
            batch, plan, "preflight", plan.mapping.source_table_id, "preflight", "preflight"
        )
        invalid += output.invalid_count
        counts.update(output.errors["code"].to_list())
        failed_fields.update(
            output.errors.filter(pl.col("value_state") == "INVALID")["field"].to_list()
        )
    return invalid, counts, failed_fields


def compare_key_candidates(
    left: pl.DataFrame,
    left_profile: dict[str, Any],
    right: pl.DataFrame,
    right_profile: dict[str, Any],
    table_id: str,
    name: str,
) -> list[RelatedKeyCheck]:
    """[D] Đo overlap/duplicate cho mã tham chiếu và lô; không phê duyệt khóa hoặc cardinality.

    Chỉ header cùng vai trò, giữ nguyên lexical values/scope. O(dòng) bộ nhớ và thời gian.
    Không coi mã khách hàng hay duy nhất đơn cột là bằng chứng khóa giao dịch.
    """

    def labels(profile: dict[str, Any]) -> dict[str, str]:
        return {
            normalized_name(c["name"]).replace("_", " "): c["column_id"] for c in profile["columns"]
        }

    a, b = labels(left_profile), labels(right_profile)
    output = []
    for role in (
        "reference",
        "reference id",
        "order id",
        "ma don",
        "ma tham chieu",
        "batch id",
        "ma lo",
    ):
        if role not in a or role not in b:
            continue
        keys = (["scope"] if "scope" in a and "scope" in b else []) + [role]

        def observed(
            frame: pl.DataFrame, columns: list[str]
        ) -> tuple[set[tuple[str, ...]], int, int]:
            rows = [tuple(r) for r in frame.select(columns).iter_rows()]
            valid = [r for r in rows if all(v is not None and v != "" for v in r)]
            return set(valid), len(valid) - len(set(valid)), len(rows) - len(valid)

        left_keys, ld, lm = observed(left, [a[k] for k in keys])
        right_keys, rd, rm = observed(right, [b[k] for k in keys])
        output.append(
            RelatedKeyCheck(
                table_id=table_id,
                source_name=name,
                fields=keys,
                shared_keys=len(left_keys & right_keys),
                left_duplicate_rows=ld,
                right_duplicate_rows=rd,
                missing_key_rows=lm + rm,
            )
        )
    return output
