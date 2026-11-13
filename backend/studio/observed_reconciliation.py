"""Conservative order-reference comparisons over observed, current source rows."""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

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
ROLE_LABELS = {plain_question(role): role for role in ROLE_ORDER}
DEFAULT_PAIRS = tuple(zip(ROLE_ORDER, ROLE_ORDER[1:], strict=False))
ROLE_SELECTOR = r"(?:(?:bao cao|so) )?(ban hang|thu ngan|ke toan)"
ACTION = r"(?:doi soat|doi chieu|so sanh)"
PAIR = rf"{ROLE_SELECTOR} voi {ROLE_SELECTOR}"
REQUEST_PREFIX = rf"^(?:(?:hay|vui long|toi muon|minh muon) )?{ACTION}\s+"
OBSERVED_SCOPE = (
    r"(?:chi (?:ket luan|doi soat) tren du lieu quan sat duoc|"
    r"tren phan du lieu du dieu kien|khong can xac nhan day du ca thang|"
    r"chi tren du lieu hien co|chi tren du lieu quan sat duoc)"
)
KEY = r"ma don hang"
METRIC = r"doanh thu thuan chua vat"
CALENDAR_DATE = r"\d{1,2}/\d{1,2}/\d{4}"
PERIOD_TOKEN = (
    r"(?:thang\s+\d{1,2}\s*/\s*\d{4}|quy\s+(?:iv|iii|ii|i|[1-4])\s*/\s*\d{4}|"
    rf"tu\s+(?:ngay\s+)?{CALENDAR_DATE}\s+den\s+(?:ngay\s+)?{CALENDAR_DATE})"
)


@dataclass(frozen=True)
class ObservedRequest:
    pairs: tuple[tuple[str, str], ...]
    key: str = KEY
    metric: str = METRIC
    currency: str = "vnd"
    period: tuple[date, date] | None = None
    confirmed: bool = False
    complete_period: bool = False
    invalid_period: bool = False


def _period(value: str) -> tuple[date, date]:
    if value.startswith("tu "):
        first, last = re.findall(CALENDAR_DATE, value)

        def calendar_date(text: str) -> date:
            day, month, year = map(int, text.split("/"))
            return date(year, month, day)

        start, end = calendar_date(first), calendar_date(last) + timedelta(days=1)
        if start >= end:
            raise ValueError("Reversed period")
        return start, end
    term, year_text = value.split("/")
    unit, number = term.split()
    year = int(year_text)
    span = 1 if unit == "thang" else 3
    index = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}.get(number, number)
    month = 1 + (int(index) - 1) * span
    start = date(year, month, 1)
    end_month = month - 1 + span
    return start, date(year + end_month // 12, end_month % 12 + 1, 1)


def observed_request(goal: str) -> ObservedRequest | None:
    """Parse supported comparison clauses. Unknown restrictions never become native writes."""
    text = " ".join(plain_question(goal).split())
    clauses = [part.strip() for part in re.split(r"[.!?;]+", text) if part.strip()]
    if not clauses:
        return None
    first, *modifiers = clauses
    if modifiers and re.match(rf"^(?:sau do|tiep theo|roi) (?:{ACTION} )?{PAIR}\b", modifiers[0]):
        first += ", " + modifiers.pop(0)
    first = re.sub(r" giup (?:minh|toi)$", "", first)
    first = re.sub(rf"(?:,\s*| )({OBSERVED_SCOPE})$", "", first)
    period = None
    invalid_period = False
    period_match = re.search(rf"(?:\s+(?:trong|cho))?\s+({PERIOD_TOKEN})$", first)
    if period_match:
        first = first[: period_match.start()]
        modifiers.insert(0, period_match[1])
    selection, separator, modifier = first.partition(", chi lay ")
    if separator:
        first = selection
        modifiers.insert(0, f"chi lay {modifier}")
    body = re.sub(REQUEST_PREFIX, "", first + " ", count=1).strip()
    pair_match = re.fullmatch(
        rf"{PAIR}(?:,? (?:sau do|tiep theo|roi|va) (?:{ACTION} )?{PAIR})?", body
    )
    pairs = DEFAULT_PAIRS
    key = metric = currency = None
    if body != first and pair_match:
        left, right, second_left, second_right = pair_match.groups()
        pairs = ((ROLE_LABELS[left], ROLE_LABELS[right]),)
        if second_left and second_right:
            pairs += ((ROLE_LABELS[second_left], ROLE_LABELS[second_right]),)
    elif body != first and re.fullmatch(
        r"(?:bao cao )?ban hang voi (?:so )?thu ngan va (?:so )?ke toan", body
    ):
        pass  # Giữ cách diễn đạt ba nguồn đã hỗ trợ.
    elif body != first and (key_match := re.fullmatch(rf"theo ({KEY})", body)):
        key = key_match[1]
    elif not (
        body != first
        and (
            (not body and period_match)
            or re.fullmatch(
                r"(?:doanh thu )?(?:ba|3) nguon|toan bo du lieu da tai len(?: cua (?:ba|3) nguon)?|"
                r"cac giao dich trong du lieu hien co",
                body,
            )
        )
        or re.fullmatch(
            r"kiem tra(?: xem)? so tien ban hang, thu ngan va ke toan co khop nhau khong",
            first,
        )
    ):
        return None
    if len(set(pairs)) != len(pairs) or any(left == right for left, right in pairs):
        return None
    confirmed = complete = False
    for clause in modifiers:
        if clause == plain_question(EQUIVALENCE_CONFIRMATION):
            confirmed = True
        elif re.fullmatch(OBSERVED_SCOPE, clause):
            continue
        elif explicit := re.fullmatch(rf"(?:(?:trong|cho|ky) )?({PERIOD_TOKEN})", clause):
            if period is not None or invalid_period:
                invalid_period = True
            else:
                try:
                    period = _period(explicit[1])
                except (ValueError, OverflowError):
                    invalid_period = True
        elif clause in {"can day du ca thang", "chi ket luan khi du du lieu ca ky"}:
            complete = True
        elif match := re.fullmatch(
            rf"(?:su dung|dung|theo) ({KEY})(?: va ({METRIC}))?(?: bang (vnd))?", clause
        ):
            key, metric, currency = match[1], match[2] or metric, match[3] or currency
        elif match := re.fullmatch(rf"(?:su dung|dung|theo) ({METRIC})(?: bang (vnd))?", clause):
            metric, currency = match[1], match[2] or currency
        elif clause in {"chi lay vnd", "chi dung vnd", "bang vnd"}:
            currency = "vnd"
        else:
            return None
    return ObservedRequest(
        pairs,
        key or KEY,
        metric or METRIC,
        currency or "vnd",
        period,
        confirmed,
        complete,
        invalid_period,
    )


def reconciliation_declined(goal: str) -> bool:
    """A direct instruction to stop or skip comparison cannot authorize a run."""
    text = plain_question(goal)
    return bool(
        re.search(
            rf"(?:^|[.!?;,]\s*|\b(?:va|nhung)\s+)(?:(?:hay|toi|minh|xin) )*"
            rf"(?:khong|dung|dung lai|chua) (?:duoc |can |muon |hay )?{ACTION}\b",
            text,
        )
    )


def observed_order_plan(
    db: Session,
    actor: Actor,
    project_id: str,
    canonical_ids: list[str],
    confirmed: bool,
    period: tuple[date, date] | None = None,
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
        if len(references) != 1 or references[0].id not in cat.identifier_fields:
            raise DomainError(
                "OBSERVATION_KEY_REQUIRED", f"Cần xác định cột mã đơn hàng của {cat.name}."
            )
        if len(calendar) != 1 or not calendar[0]:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID",
                f"Ngày giao dịch nào đã được xác nhận ở {cat.name}? "
                "Studio cần một ngày lịch hợp lệ cho mỗi dòng.",
            )
        if len(monetary) != 1:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID",
                f"Cột nào ở {cat.name} chứa doanh thu thuần chưa VAT bằng VND? "
                "Cần xác định một cột duy nhất.",
            )
        keys.append(references[0].id)
        days.append(calendar[0])
        amounts.append(monetary[0])
    same_definition = amounts[0].semantic_metric == amounts[1].semantic_metric and all(
        field.semantic_metric
        and {"net", "revenue"} <= set(field_name_tokens(field.semantic_metric))
        and field.amount_basis == "net_excluding_tax"
        for field in amounts
    )
    if not same_definition and not confirmed:
        field_labels = " và ".join(
            f"{cat.name} ({field.name})" for cat, field in zip(cats, amounts, strict=True)
        )
        raise DomainError(
            "OBSERVATION_METRIC_REQUIRED",
            f"Cần xác nhận {field_labels} cùng là doanh thu thuần chưa VAT.",
        )
    ranges: list[tuple[date, date]] = []
    eligible_keys: list[set[str]] = []
    for cat, day, key, amount in zip(cats, days, keys, amounts, strict=True):
        dated: list[tuple[date, str]] = []
        for record in load_canonical_records(db, actor, cat.canonical):
            if record.invalid:
                continue
            stamp, reference, money = (record.payload.get(field) for field in (day, key, amount.id))
            if (
                type(stamp) is date
                and isinstance(reference, str)
                and reference
                and isinstance(money, Decimal)
                and money.is_finite()
                and record.payload.get("currency", "VND") == "VND"
            ):
                dated.append((stamp, reference))
        if not dated:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID",
                f"{cat.name} chưa có dòng dùng được với ngày giao dịch, mã đơn và số tiền VND.",
            )
        first, last = min(value for value, _ in dated), max(value for value, _ in dated)
        if last == date.max:
            raise DomainError(
                "OBSERVATION_SCOPE_INVALID", f"Ngày cuối của {cat.name} vượt phạm vi hỗ trợ."
            )
        ranges.append((first, last + timedelta(days=1)))
        eligible_keys.append(
            {
                value
                for day_value, value in dated
                if value and (not period or period[0] <= day_value < period[1])
            }
        )
    if period and any(not keys for keys in eligible_keys):
        raise DomainError(
            "OBSERVATION_SCOPE_INVALID",
            "Có nguồn thiếu giao dịch dùng được trong khoảng ngày đã yêu cầu.",
        )
    if not eligible_keys[0].intersection(eligible_keys[1]):
        raise DomainError(
            "OBSERVATION_KEY_REQUIRED",
            "Chưa thấy mã đơn hàng chung trong các dòng dùng được thuộc phạm vi này.",
        )
    start, end = period or (min(first for first, _ in ranges), max(last for _, last in ranges))
    slots = []
    for cat, day, (first, end_exclusive) in zip(cats, days, ranges, strict=True):
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
                coverage_start=first,
                coverage_end=end_exclusive,
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
