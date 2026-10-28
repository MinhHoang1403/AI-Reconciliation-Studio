"""F14: validate scoped metadata and explicit business declarations before approval.

Uniqueness and row coverage are additionally checked against canonical records at
execution; duplicate keys remain review cases, never permission to choose a match.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from studio.contracts.reconciliation import ReconciliationPlan, SourceCatalogue
from studio.errors import DomainError


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise DomainError(code, message, 422)


def known(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in {"unknown", "ambiguous", "unspecified"})


def validate_reconciliation_contract(
    plan: ReconciliationPlan, catalogue: list[SourceCatalogue], workspace_id: str, project_id: str
) -> ReconciliationPlan:
    """Return the unchanged valid plan or a coded failure; never infer missing semantics.

    Source refs must be active canonical revisions in this project. Evidence and
    all field pairs are allowlisted; SOURCE_SIGNED is an explicit user declaration,
    not an inferred marketplace sign or fee conversion. Approval remains separate.
    """
    indexed = {c.canonical.id: c for c in catalogue}
    _require(len(indexed) == len(catalogue), "SOURCE_CATALOGUE_INVALID", "Nguồn bị lặp.")
    selected = []
    for slot in (plan.left, plan.right):
        cat = indexed.get(slot.canonical_id)
        _require(cat is not None, "SOURCE_NOT_FOUND", "Nguồn canonical không tồn tại.")
        assert cat is not None
        canonical, schema = cat.canonical, cat.schema_definition
        _require(
            cat.project_id == project_id
            and canonical.workspace_id == workspace_id
            and schema.workspace_id == workspace_id,
            "SOURCE_SCOPE_INVALID",
            "Nguồn không thuộc project/workspace hiện tại.",
        )
        _require(
            not canonical.stale
            and canonical.quality_status != "FAILED"
            and canonical.schema_id == schema.id
            and canonical.schema_revision == schema.revision,
            "SOURCE_REVISION_INVALID",
            "Nguồn đã cũ, lỗi hoặc không đúng schema revision.",
        )
        _require(
            known(canonical.grain)
            and known(schema.grain)
            and canonical.grain == schema.grain
            and known(plan.entity_kind),
            "GRAIN_UNKNOWN",
            "Chưa xác nhận ý nghĩa mỗi dòng.",
        )
        compatible_entities = {plan.entity_kind}
        if plan.entity_kind == "order":
            compatible_entities.add("order_line")
        _require(
            canonical.entity_kind in compatible_entities,
            "ENTITY_INCOMPATIBLE",
            "Loại dữ liệu không tương thích với đối tượng đối soát.",
        )
        fields = {f.id: f for f in schema.fields}
        _require(
            slot.date_field in fields and fields[slot.date_field].data_type == "date",
            "DATE_FIELD_INVALID",
            "Cần trường ngày đã chuẩn hóa.",
        )
        _require(
            set(slot.filters) <= fields.keys(),
            "FILTER_FIELD_INVALID",
            "Bộ lọc tham chiếu trường không tồn tại.",
        )
        _require(
            all(fields[k].data_type in {"string", "enum"} for k in slot.filters),
            "FILTER_TYPE_INVALID",
            "Bộ lọc scope chỉ nhận chuỗi đã duyệt.",
        )
        if slot.currency_field:
            _require(
                slot.currency_field in fields
                and fields[slot.currency_field].data_type in {"string", "enum"},
                "CURRENCY_FIELD_INVALID",
                "Trường currency không hợp lệ.",
            )
        _require(
            slot.coverage_start < slot.coverage_end,
            "COVERAGE_INVALID",
            "Khoảng coverage phải có đầu và cuối hợp lệ.",
        )
        _require(
            slot.snapshot_at.utcoffset() is not None,
            "SNAPSHOT_TIMEZONE_REQUIRED",
            "Thời điểm chụp dữ liệu cần timezone.",
        )
        if slot.settlement_due_at is not None:
            _require(
                slot.settlement_due_at.utcoffset() is not None,
                "SETTLEMENT_TIMEZONE_REQUIRED",
                "Hạn quyết toán cần timezone.",
            )
        incomplete = (
            slot.completeness != "CONFIRMED"
            or slot.coverage_start > plan.period_start
            or slot.coverage_end < plan.period_end
            or (slot.settlement_due_at is not None and slot.snapshot_at < slot.settlement_due_at)
        )
        _require(
            not incomplete or plan.allow_partial,
            "INSUFFICIENT_COVERAGE",
            "Coverage chưa đủ; cần xác nhận chạy một phần, không kết luận thiếu chắc chắn.",
        )
        selected.append(cat)
    left, right = selected
    _require(
        known(plan.left.time_basis) and plan.left.time_basis == plan.right.time_basis,
        "TIME_BASIS_INCOMPATIBLE",
        "Hai nguồn cần cùng cơ sở thời gian đã xác nhận.",
    )
    try:
        ZoneInfo(plan.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise DomainError("TIMEZONE_INVALID", "Timezone không hợp lệ.", 422) from exc
    _require(
        plan.effective_from <= plan.period_start
        and (plan.effective_to is None or plan.period_end <= plan.effective_to),
        "RULE_EXPIRED",
        "Rule không có hiệu lực trên toàn kỳ được chọn.",
    )
    _require(known(plan.comparison_grain), "GRAIN_UNKNOWN", "Cần xác nhận comparison grain.")
    if plan.cardinality == "ONE_TO_ONE":
        _require(
            plan.aggregation == "NONE"
            and left.canonical.grain == right.canonical.grain == plan.comparison_grain,
            "CARDINALITY_GRAIN_INVALID",
            "1:1 cần cùng grain và không aggregation.",
        )
    else:
        anchor = left if plan.cardinality == "ONE_TO_MANY" else right
        _require(
            plan.aggregation == "SUM_SIGNED" and anchor.canonical.grain == plan.comparison_grain,
            "AGGREGATION_UNAPPROVED",
            "Nhóm cần SUM_SIGNED và grain tham chiếu đã xác nhận.",
        )
    maps = [{f.id: f for f in c.schema_definition.fields} for c in selected]
    pairs = [*plan.join_keys, *plan.attributes, *plan.fuzzy_fields, *plan.fuzzy_block_keys]
    for pair in pairs:
        _require(
            pair.left in maps[0] and pair.right in maps[1],
            "FIELD_NOT_FOUND",
            "Rule tham chiếu field/trường không tồn tại.",
        )
        _require(
            maps[0][pair.left].data_type == maps[1][pair.right].data_type,
            "FIELD_TYPES_INCOMPATIBLE",
            "Hai trường không cùng kiểu dữ liệu.",
        )
    for pair in plan.join_keys:
        _require(
            maps[0][pair.left].data_type in {"string", "enum"},
            "JOIN_KEY_TYPE_INVALID",
            "Khóa định danh cần chuỗi được bảo toàn, không dùng số tiền làm khóa.",
        )
    for metric in plan.comparison_metrics:
        _require(
            metric.left in maps[0] and metric.right in maps[1],
            "METRIC_FIELD_NOT_FOUND",
            "Trường chỉ tiêu không tồn tại.",
        )
        for fields, key in ((maps[0], metric.left), (maps[1], metric.right)):
            field = fields[key]
            _require(
                field.data_type == "decimal"
                and known(field.semantic_metric)
                and field.semantic_metric == metric.metric_id
                and field.currency == metric.currency
                and known(field.amount_basis)
                and field.amount_basis == metric.amount_basis
                and known(field.unit)
                and field.unit == metric.unit,
                "RULE_UNVERIFIED",
                "Metric, gross/net, đơn vị hoặc currency chưa đồng nhất.",
            )
    for side, cat, fields in zip(("left", "right"), selected, maps, strict=True):
        rigid = set(cat.identifier_fields) | set(cat.schema_definition.business_key_fields)
        rigid |= {getattr(pair, side) for pair in plan.join_keys}
        for pair in plan.fuzzy_fields:
            key = getattr(pair, side)
            _require(
                key not in rigid and fields[key].data_type in {"string", "enum"},
                "FUZZY_RIGID_ID_FORBIDDEN",
                "Không fuzzy mã định danh hoặc trường ngoài text.",
            )
    _require(
        not plan.fuzzy_fields or bool(plan.fuzzy_block_keys),
        "FUZZY_BLOCKING_REQUIRED",
        "Fuzzy cần blocking keys đã duyệt để giới hạn ứng viên.",
    )
    evidence = {
        v
        for c in selected
        for v in (c.canonical.id, c.canonical.artifact.id, c.canonical.schema_id)
    }
    _require(
        set(plan.evidence_ids) <= evidence,
        "INVALID_EVIDENCE",
        "Evidence không nằm trong nguồn được phép.",
    )
    return plan
