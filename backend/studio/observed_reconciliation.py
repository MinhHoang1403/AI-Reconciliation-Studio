"""Conservative order-reference comparisons over observed, current source rows."""

import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from studio.access import Actor
from studio.assistant import plain_question
from studio.contracts.reconciliation import (
    ComparisonMetric,
    FieldPair,
    ObservedComparison,
    ReconciliationPlan,
    SourceSelection,
)
from studio.database import DatasetRow, VersionRow
from studio.errors import DomainError
from studio.profiling import field_name_tokens
from studio.reconciliation_repository import load_canonical_records, selected_catalogue

EQUIVALENCE_CONFIRMATION = "Xác nhận các cột tiền chưa VAT đều là doanh thu thuần chưa VAT"
ROLE_ORDER = ("Bán hàng", "Thu ngân", "Kế toán")


def observed_request(goal: str) -> bool | None:
    """Recognize a request, with an optional direct business declaration from the editor."""
    sentences = [part.strip() for part in re.split(r"[.!?]+", plain_question(goal)) if part.strip()]
    if not sentences or not re.fullmatch(
        r"(?:hay )?(?:doi soat|doi chieu) (?:doanh thu )?"
        r"(?:ba nguon|3 nguon|(?:bao cao )?ban hang voi (?:so )?thu ngan "
        r"(?:va|roi (?:so )?thu ngan voi) (?:so )?ke toan)"
        r"(?: tren phan du lieu du dieu kien)?(?: giup (?:minh|toi))?",
        sentences[0],
    ):
        return None
    if len(sentences) == 1:
        return False
    if len(sentences) == 2 and sentences[1] == plain_question(EQUIVALENCE_CONFIRMATION):
        return True
    return None


def observed_order_plan(
    db: Session,
    actor: Actor,
    project_id: str,
    canonical_ids: list[str],
    confirmed: bool,
) -> tuple[ReconciliationPlan, ObservedComparison]:
    """Bind one exact key, calendar day and single monetary field per source.

    Range and source capture are observations. Coverage stays UNKNOWN; matching
    and independent verification use the same durable path as approved runs.
    """
    cats = selected_catalogue(db, actor, project_id, canonical_ids)
    keys, days, amounts = [], [], []
    for cat in cats:
        mapping = cat.mapping
        if cat.canonical.stale or not mapping or not mapping.policy_application:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID", "Cần bản chuẩn bị hiện hành đã kiểm chứng."
            )
        fields = cat.schema_definition.fields
        references = [
            field
            for field in fields
            if field.data_type == "string"
            and "order" in field_name_tokens(field.name)
            and set(field_name_tokens(field.name)) & {"id", "reference"}
        ]
        calendar = [
            d.candidate_target
            for d in mapping.decisions
            if d.transformation_candidate.op == "parse_calendar_date"
        ]
        monetary = [
            field
            for field in fields
            if field.data_type == "decimal"
            and field.currency == field.unit == "VND"
            and field.amount_basis in {"net_excluding_tax", "excluding_tax"}
        ]
        if len(references) != 1 or len(calendar) != 1 or len(monetary) != 1 or not calendar[0]:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID",
                f"{cat.name} cần có một mã đơn hàng, một ngày lịch và một cột tiền chưa VAT.",
            )
        keys.append(references[0].id)
        days.append(calendar[0])
        amounts.append(monetary[0])
    same_definition = amounts[0].semantic_metric == amounts[1].semantic_metric and all(
        field.amount_basis == "net_excluding_tax" for field in amounts
    )
    if not same_definition and not confirmed:
        field_labels = " và ".join(
            f"{cat.name} ({field.name})" for cat, field in zip(cats, amounts, strict=True)
        )
        raise DomainError(
            "OBSERVATION_METRIC_REQUIRED",
            f"Cần xác nhận {field_labels} cùng là doanh thu thuần chưa VAT.",
        )
    observations = [
        [
            item.payload
            for item in load_canonical_records(db, actor, cat.canonical)
            if not item.invalid
        ]
        for cat in cats
    ]
    if not {row[keys[0]] for row in observations[0] if row[keys[0]]}.intersection(
        row[keys[1]] for row in observations[1] if row[keys[1]]
    ):
        raise DomainError(
            "OBSERVATION_KEY_REQUIRED", "Chưa thấy mã đơn hàng chung trong các dòng dùng được."
        )
    dates = [
        row[day]
        for rows, day in zip(observations, days, strict=True)
        for row in rows
        if type(row[day]) is date
    ]
    if not dates or max(dates) == date.max:
        raise DomainError("OBSERVATION_SCOPE_INVALID", "Chưa xác định được khoảng ngày quan sát.")
    start, end = min(dates), max(dates) + timedelta(days=1)
    slots = []
    for cat, day in zip(cats, days, strict=True):
        version = db.get(VersionRow, cat.canonical.dataset_version_id)
        assert version is not None
        dataset = db.get(DatasetRow, version.dataset_id)
        assert dataset is not None
        slots.append(
            SourceSelection(
                canonical_id=cat.canonical.id,
                role=cat.canonical.entity_kind,
                date_field=day,
                time_basis="observed_source_calendar_day",
                currency_field="currency"
                if any(f.id == "currency" for f in cat.schema_definition.fields)
                else None,
                coverage_start=start,
                coverage_end=end,
                completeness="UNKNOWN",
                snapshot_at=dataset.created_at,
            )
        )
    metric_id = "net_revenue_excluding_tax" if not same_definition else amounts[0].semantic_metric
    assert metric_id is not None
    return ReconciliationPlan(
        name="Đối chiếu doanh thu theo mã đơn hàng",
        entity_kind="order",
        left=slots[0],
        right=slots[1],
        join_keys=[FieldPair(left=keys[0], right=keys[1])],
        comparison_metrics=[
            ComparisonMetric(
                left=amounts[0].id,
                right=amounts[1].id,
                metric_id=metric_id,
                currency="VND",
                unit="VND",
                amount_basis="net_excluding_tax",
                sign_convention="SOURCE_SIGNED",
            )
        ],
        comparison_grain="observed_order_reference",
        cardinality="ONE_TO_ONE",
        aggregation="NONE",
        period_start=start,
        period_end=end,
        timezone="UTC",
        effective_from=start,
        allow_partial=True,
        evidence_ids=canonical_ids,
    ), ObservedComparison(
        confirmed_by=actor.id if confirmed else None,
        confirmation=EQUIVALENCE_CONFIRMATION if confirmed else None,
    )
