"""Resolve bounded source analytics against the current canonical catalogue."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from studio.assistant import plain_question
from studio.contracts.agent import AgentIntent, DatasetContext, IntentCatalogue, TableContext
from studio.contracts.data_query import DataQuery, QueryAggregation, QueryFilter, QuerySort
from studio.data_query import source_measures
from studio.errors import DomainError
from studio.profiling import field_name_tokens

ROLE = r"(?:(?:bao cao|so) )?(ban hang|thu ngan|ke toan)"
DATE = r"\d{1,2}/\d{1,2}/\d{4}"
DAY_RANGE = rf"(?:tu (?:ngay )?)?({DATE}) den (?:(?:het )?(?:ngay )?)({DATE})"
SINGLE_DAY = rf"ngay ({DATE})"
MONTH = r"(?:(nua dau|nua sau) )?thang (\d{1,2})(?:\s*/\s*(\d{4}))?"
QUARTER = r"quy (iv|iii|ii|i|[1-4])(?:\s*/\s*| nam )(\d{4})"
YEAR = r"nam (\d{4})"
DAY_EDGE = rf"(truoc|sau) (?:ngay )?({DATE})"
PERIOD = rf"(?:{DAY_RANGE}|{DAY_EDGE}|{SINGLE_DAY}|{MONTH}|{QUARTER}|{YEAR})"
MONEY = r"(?:so tien|tien|doanh thu(?: thuan)?(?: chua vat| truoc vat| sau vat| gom vat)?|gia tri)"
STATUS = r'(?:co )?trang thai\s+(?:"([a-z0-9 _-]+)"|([a-z0-9_-]+))'
GROUPING = r"theo (?:tung )?(ngay|thang)"
ALL_SOURCES = r"(?:ca ba|ba|3|tung|moi|tat ca(?: cac)?) nguon"
DISTINCT_ORDERS = (
    r"(?:co )?(?:bao nhieu|dem) ma don(?: hang)? (?:duy nhat|khac nhau)|(?:co )?bao nhieu don hang"
)
COUNT_ROWS = r"(?:co )?bao nhieu giao dich"
TOP_ACTION = r"(?:hien thi|xem|cho toi xem|top) (\d{1,2}) (?:don hang|giao dich)(?: co)?"
NEGATIVE_ROWS = rf"(?:co |xem |liet ke )?(?:nhung |cac )?giao dich(?: co)? {MONEY} am(?: nao)?"
TOTAL_ACTION = r"(?:tinh )?(?:tong cong|tong|sum|total)"
EXTREMA = rf"{MONEY} (nho|thap|lon|cao) nhat"
CURRENCY = r"(?:chi (?:lay|tinh) (?:cac )?giao dich |bang )?(vnd|usd|eur)"
TOP_FOLLOWUP = (
    r"(?:(?:cho toi|xem|lay) )?top (\d{1,2}) (?:nhung |va )?giu "
    r"(?:nguyen )?(?:cac )?bo loc (?:ngay )?(?:truoc do|dang dung)"
)
TIE_COUNT = r"(?:co )?bao nhieu giao dich dong hang (?:tai |o )?vi tri thu (\d{1,2})"


@dataclass(frozen=True)
class CalendarScope:
    op: Literal["between", "lt", "gte"]
    values: tuple[str, ...]

    def bind(self, field_id: str) -> QueryFilter:
        if self.op == "between":
            return QueryFilter(field_id=field_id, op="between", value=list(self.values))
        return QueryFilter(field_id=field_id, op=self.op, value=self.values[0])


def validate_source_query_coverage(query: DataQuery, bound: AgentIntent | None) -> None:
    """Reject an unbound source query or one that alters any result-defining operation."""
    if not bound or bound.intent != "QUERY_DATA" or not bound.query:
        raise DomainError(
            "INPUT_AMBIGUOUS",
            bound.questions[0]
            if bound and bound.questions
            else "Hãy xác nhận nguồn, chỉ tiêu và điều kiện trước khi tính tiền.",
        )
    expected = bound.query.model_dump(exclude={"filters", "currency_field"})
    proposed = query.model_dump(exclude={"filters", "currency_field"})
    if (
        proposed != expected
        or sorted(f.model_dump_json() for f in bound.query.filters)
        != sorted(f.model_dump_json() for f in query.filters)
        or query.currency_field not in (None, bound.query.currency_field)
    ):
        raise DomainError(
            "INPUT_AMBIGUOUS", "Kế hoạch chưa khớp yêu cầu. Hãy xác nhận phạm vi cần tính."
        )


def source_scope_explicit(goal: str) -> bool:
    text = plain_question(goal)
    return bool(
        re.search(rf"\b{ROLE}\b|\b(?:ca ba|ba|3|hai|tung|moi|tat ca(?: cac)?) nguon\b", text)
    )


def _clarify(question: str) -> AgentIntent:
    return AgentIntent(intent="CLARIFY", questions=[question])


def _status_filter(match: re.Match[str], table: TableContext) -> QueryFilter:
    label = match[1] or match[2]
    matches = [
        (field, value)
        for field, values in table.approved_status_values.items()
        for value in values
        if plain_question(value) == label
    ]
    if len(matches) != 1:
        raise DomainError("INPUT_AMBIGUOUS", "Bạn muốn lọc theo trạng thái chuẩn hóa nào?")
    field, value = matches[0]
    return QueryFilter(field_id=field, op="eq", value=value)


def _by_name(text: str, datasets: list[DatasetContext]) -> list[DatasetContext]:
    filenames = [
        d
        for d in datasets
        if re.search(rf"(?<![\w.-]){re.escape(plain_question(d.name))}(?![\w.-])", text)
    ]
    if filenames:
        return filenames
    roles = {match[1] for match in re.finditer(rf"\b{ROLE}\b", text)}
    if not roles:
        return []
    result = []
    for dataset in datasets:
        words = " ".join(re.findall(r"[a-z0-9]+", plain_question(dataset.name)))
        if any(f" {role} " in f" {words} " for role in roles) or any(
            table.schema_definition and plain_question(table.schema_definition.entity_kind) in roles
            for table in dataset.tables
        ):
            result.append(dataset)
    return result


def _period(clause: str, previous_year: int | None = None) -> CalendarScope:
    def day(value: str) -> date:
        d, m, y = map(int, value.split("/"))
        return date(y, m, d)

    if match := re.fullmatch(DAY_EDGE, clause):
        boundary = day(match[2])
        if match[1] == "truoc":
            return CalendarScope("lt", (boundary.isoformat(),))
        return CalendarScope("gte", ((boundary + timedelta(days=1)).isoformat(),))
    if match := re.fullmatch(DAY_RANGE, clause):
        start, last = map(day, match.groups())
        if start > last:
            raise ValueError("Reversed period")
        end = last + timedelta(days=1)
    elif match := re.fullmatch(SINGLE_DAY, clause):
        start = day(match[1])
        end = start + timedelta(days=1)
    elif match := re.fullmatch(MONTH, clause):
        half, month_text, year_text = match.groups()
        month = int(month_text)
        year = int(year_text) if year_text else previous_year or 0
        start = date(year, month, 16 if half == "nua sau" else 1)
        end = (
            date(year, month, 16)
            if half == "nua dau"
            else date(year + (month == 12), month % 12 + 1, 1)
        )
    elif match := re.fullmatch(QUARTER, clause):
        number = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}.get(match[1], match[1])
        year, month = int(match[2]), 1 + (int(number) - 1) * 3
        start = date(year, month, 1)
        end = date(year + (month == 10), (month + 2) % 12 + 1, 1)
    else:
        match = re.fullmatch(YEAR, clause)
        assert match
        year = int(match[1])
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    return CalendarScope("between", (start.isoformat(), end.isoformat()))


def _consume(pattern: str, text: str) -> tuple[list[re.Match[str]], str]:
    """Match full clauses and preserve offsets for verbatim filter literals."""
    matches = list(re.finditer(rf"(?<![\w/])(?:{pattern})(?![\w/])", text))
    for match in reversed(matches):
        text = text[: match.start()] + " " * len(match[0]) + text[match.end() :]
    return matches, text


LOCATION = r"(?:(?:chi (?:tinh|lay) |tai |o ))(chi nhanh|cua hang|khu vuc) "
LITERAL = r'"([^"]+)"|“([^”]+)”'
FILTER_FIELD = rf"(?:co )?truong ([a-z0-9_ ]+?) (?:dung bang|bang) (?:{LITERAL})"
LOCATION_VALUE = (
    r"[a-z0-9_-]+(?: (?!(?:va|hoac|trong|theo|ngoai|tru|khong|chi|tai|khi|"
    r"tu|truoc|sau|ngay|thang|quy|nam|nua|co|thi|vnd|usd|eur)\b)[a-z0-9_-]+){0,5}"
)
LOCATION_FILTER = rf"{LOCATION}(?:{LITERAL}|({LOCATION_VALUE}))"
LOCATION_FOLLOWUP = rf"con (chi nhanh|cua hang|khu vuc) (?:{LITERAL}|({LOCATION_VALUE}))"
EXPLICIT_SOURCE = (
    r"(?:(?:cua|trong|tu) )?(?:(?:bo )?du lieu(?: cua)? |nguon(?: du lieu)? |tep |file )?"
)


def _field_names(field_id: str, label: str) -> set[str]:
    return {plain_question(value.replace("_", " ")) for value in (field_id, label)}


def _field_filter(match: re.Match[str], original: str, table: TableContext) -> QueryFilter:
    label = match[1]
    schema = table.schema_definition
    assert schema
    approved_aliases = {
        "chi nhanh": {"branch", "branch code", "branch name"},
        "cua hang": {"store", "store code", "store name"},
        "khu vuc": {"region", "region code", "region name"},
    }
    names = {label.replace("_", " "), *approved_aliases.get(label, ())}
    fields = [
        f
        for f in schema.fields
        if _field_names(f.id, f.name) & names
        and f.data_type in {"string", "enum", "decimal"}
    ]
    if len(fields) != 1:
        raise DomainError(
            "INPUT_AMBIGUOUS",
            "Chưa xác định được cột phù hợp để lọc theo "
            + {"chi nhanh": "chi nhánh", "cua hang": "cửa hàng", "khu vuc": "khu vực"}.get(
                label, "trường đã nêu"
            )
            + ". Bạn muốn dùng cột nào trong bản chuẩn hóa?",
        )
    field = fields[0]
    literal_index = next(i for i in range(2, len(match.groups()) + 1) if match[i])
    value = original[match.start(literal_index) : match.end(literal_index)]
    if field.data_type == "enum":
        values = [
            v
            for v in table.approved_status_values.get(field.id, [])
            if plain_question(v) == plain_question(value)
        ]
        if len(values) != 1:
            raise DomainError("INPUT_AMBIGUOUS", "Bạn muốn dùng giá trị chuẩn hóa nào để lọc?")
        value = values[0]
    elif field.data_type == "decimal" and not re.fullmatch(r"-?\d{1,38}(?:\.\d{1,18})?", value):
        raise DomainError(
            "INPUT_AMBIGUOUS", "Hãy ghi giá trị số chính xác, dùng dấu chấm cho phần lẻ."
        )
    elif literal_index == 4 and " " in value:
        raise DomainError(
            "INPUT_AMBIGUOUS",
            "Hãy đặt nguyên văn giá trị cần lọc trong dấu ngoặc kép.",
        )
    return QueryFilter(field_id=field.id, op="eq", value=value)


def resolve_source_read(goal: str, catalogue: IntentCatalogue) -> AgentIntent | None:
    """Source amounts, order identifiers and follow-ups use approved fields only."""
    original = (
        re.sub(
            rf"{LITERAL}|\s+",
            lambda match: match[0] if match[0][0] in '"“' else " ",
            unicodedata.normalize("NFC", goal),
        )
        .strip()
        .rstrip(" ?!.")
    )
    # Keep normalized clauses and verbatim literals in the same coordinate system.
    text = "".join(plain_question(char)[:1] or "\ufffd" for char in original)
    unquoted = re.sub(LITERAL, '""', text)
    if re.search(
        r"\b(?:khong|dung|chua) (?:duoc |can |hay )?(?:tinh(?: tong)?|cong tong)\b",
        unquoted,
    ):
        return AgentIntent(
            intent="UNSUPPORTED", questions=["Đã ghi nhận yêu cầu bỏ phép tính tổng."]
        )
    if re.search(
        r"\b(?:doi soat|luot chay|nhom khop|chenh lech|lech tien|sai tien|sai lech)\b", unquoted
    ) and not re.fullmatch(r"hai nguon chenh nhau bao nhieu", text):
        return None
    previous = catalogue.previous_query
    if (
        not previous
        or previous.source_kind != "CANONICAL"
        or previous.project_id != catalogue.context.project_id
    ):
        previous = None
    change_source = re.fullmatch(rf"con {ROLE}", text)
    compare_with = re.fullmatch(rf"so sanh voi {ROLE}", text)
    top_followup = re.fullmatch(TOP_FOLLOWUP, text)
    tie_count = re.fullmatch(TIE_COUNT, text)
    refine = re.match(
        r"^(?:(?:tiep tuc|hay) )?(?:nhom ket qua nay|hien thi) theo (?:tung )?(?:ngay|thang)$", text
    )
    fields, remaining = _consume(FILTER_FIELD, text)
    locations, remaining = _consume(LOCATION_FILTER, remaining)
    location_followup, remaining = _consume(LOCATION_FOLLOWUP, remaining)
    locations.extend(location_followup)
    filters = sorted([*fields, *locations], key=lambda match: match.start())
    statuses, remaining = _consume(STATUS, remaining)

    def alternatives(labels: set[str]) -> str:
        return "|".join(map(re.escape, sorted(labels, key=lambda label: (-len(label), label))))

    filenames = alternatives({plain_question(d.name) for d in catalogue.datasets if "." in d.name})
    stems = alternatives({plain_question(d.name.rsplit(".", 1)[0]) for d in catalogue.datasets})
    scope_text = " ".join(remaining.split())
    selectors = [rf'"(?:{stems})"|(?:tep|file|nguon) (?:{stems})'] if stems else []
    if filenames:
        selectors.append(rf'"(?:{filenames})"|(?:{filenames})(?![\w.-])')
    if role_stems := alternatives(
        {
            plain_question(d.name.rsplit(".", 1)[0])
            for d in catalogue.datasets
            if re.fullmatch(ROLE, plain_question(d.name.rsplit(".", 1)[0]))
        }
    ):
        selectors.append(rf"(?:(?:bao cao|so) )?(?:{role_stems})(?![\w.-])")
    source_matches, remaining = (
        _consume(rf"{EXPLICIT_SOURCE}(?:{'|'.join(selectors)})", remaining)
        if selectors
        else ([], remaining)
    )
    roles, remaining = _consume(rf"{EXPLICIT_SOURCE}{ROLE}", remaining)
    all_matches, remaining = _consume(
        rf"{EXPLICIT_SOURCE}{ALL_SOURCES}(?: trong du an hien tai)?", remaining
    )
    calendars, remaining = _consume(PERIOD, remaining)
    buckets, remaining = _consume(GROUPING, remaining)
    currencies, remaining = _consume(CURRENCY, remaining)
    dates_only = re.fullmatch(rf"(?:chi lay|loc) (?:giao dich )?{PERIOD}", text)
    filter_only = bool(
        previous
        and (statuses or filters or currencies)
        and re.fullmatch(
            r"(?:(?:chi (?:lay|tinh)|loc|xem)(?: giao dich)?|con(?: thi sao)?)?",
            " ".join(remaining.split()),
        )
    )
    all_sources = bool(all_matches)
    comparison = bool(
        re.fullmatch(
            r"(?:ba nguon|ba tong tien nay|hai nguon) "
            r"(?:co tong tien bang nhau khong|co bang nhau khong|chenh nhau bao nhieu)",
            text,
        )
    )
    candidates = catalogue.datasets
    selected = _by_name(scope_text, candidates)
    if source_matches:
        selected = []
        for occurrence in source_matches:
            names_for_occurrence = [
                d
                for d in candidates
                if re.search(
                    rf'(?<![\w.-]){re.escape(plain_question(d.name))}"?$',
                    occurrence[0],
                )
            ] or [
                d
                for d in candidates
                if re.search(
                    rf'(?<![\w.-]){re.escape(plain_question(d.name.rsplit(".", 1)[0]))}"?$',
                    occurrence[0],
                )
            ]
            selected.extend(d for d in names_for_occurrence if d not in selected)
    action = " ".join(remaining.split()).strip(" ,")
    action = re.sub(r"^(?:cho toi biet |xin |hay |vui long )", "", action)
    if calendars or filters or statuses:
        action = re.sub(r"^trong(?: *, *| )", "", action)
    action = re.sub(r" , ", " ", action)
    action = re.sub(r"(?<=chua vat),? khong phai tong tien co vat$", "", action)
    if (
        len(locations) == 1
        and len(filters) == 1
        and not statuses
        and not calendars
        and not currencies
    ):
        # "Chỉ [địa điểm], không tính các [địa điểm] khác" repeats the same equality.
        location_kind = locations[0][1]
        if previous and location_followup and action == "thi sao":
            filter_only = True
        if previous and re.fullmatch(rf"khong tinh cac {location_kind} khac", action):
            if locations[0][0].startswith(("chi tinh ", "chi lay ")):
                filter_only = True
    measure_names = {
        name
        for dataset in candidates
        for table in dataset.tables
        if table.schema_definition
        for measure in source_measures(table.schema_definition)
        for name in _field_names(measure.field_id, measure.name)
    }
    measure_pattern = "|".join(
        map(re.escape, sorted(measure_names, key=lambda name: (-len(name), name)))
    )
    measure_term = rf"(?:{measure_pattern}|{MONEY})" if measure_pattern else MONEY
    top_rows = rf"{TOP_ACTION} ({measure_term}) (?:cao|lon) nhat"
    total = bool(re.search(rf"\b{TOTAL_ACTION} {measure_term}\b", action))
    explicit_measure = re.fullmatch(
        rf"(?:{TOTAL_ACTION} )?({measure_term})(?: la bao nhieu| bao nhieu| giup toi)?"
        r"(?: (?:trong|cua|va))*",
        action,
    )
    grouped = bool(buckets and explicit_measure and not refine)
    distinct = bool(re.search(rf"\b(?:{DISTINCT_ORDERS})\b", action))
    count = bool(re.search(rf"\b{COUNT_ROWS}\b", action)) and not tie_count
    ranked = re.search(rf"\b{top_rows}\b", action)
    top = top_followup or ranked
    negative = bool(re.search(rf"\b{NEGATIVE_ROWS}\b", action))
    lookup = re.fullmatch(
        r"(?:hay )?tim (?:don |ma(?: don hang)? )([a-z0-9_-]{1,64})(?: va cho xem dong nguon)?",
        text,
    )
    extrema = re.search(rf"\b{EXTREMA}\b", action) if not top else None
    if not any(
        (
            total,
            grouped,
            distinct,
            count,
            top,
            negative,
            lookup,
            extrema,
            comparison,
            change_source,
            compare_with,
            refine,
            dates_only,
            filter_only,
            top_followup,
            tie_count,
        )
    ):
        return None
    if len(calendars) > 1 or len(buckets) > 1 or len(currencies) > 1 or len(all_matches) > 1:
        return _clarify("Bạn muốn dùng khoảng ngày, cách nhóm và đơn vị tiền nào?")
    if not (
        comparison
        or change_source
        or compare_with
        or refine
        or dates_only
        or filter_only
        or lookup
        or top_followup
        or tie_count
    ):
        actions = (
            rf"(?:{TOTAL_ACTION} {measure_term}|{DISTINCT_ORDERS}|{COUNT_ROWS}|"
            rf"{top_rows}|{NEGATIVE_ROWS}|{EXTREMA})"
        )
        connectors = r"(?: (?:trong|cua|va))*" if filters or statuses or calendars else ""
        residual = re.fullmatch(
            rf"(?:{actions}{'|' + measure_term if grouped else ''})"
            rf"(?: la bao nhieu| bao nhieu| giup toi)?{connectors}",
            action,
        )
        if residual is None or (buckets and not grouped):
            return _clarify(
                "Chưa xác định được đầy đủ điều kiện. Bạn có thể ghi rõ trường, "
                "giá trị lọc hoặc khoảng ngày cần dùng không?"
            )
    if (filters or statuses) and (comparison or change_source or compare_with or lookup):
        return _clarify("Hãy xác nhận bộ lọc cho nguồn đang chọn.")
    if tie_count:
        if not previous or previous.ranking_size != int(tie_count[1]):
            return _clarify("Hãy mở bảng Top N có đúng vị trí bạn muốn kiểm tra.")
        if not any(t.canonical_id == previous.source_id for d in candidates for t in d.tables):
            return _clarify("Hãy chọn lại nguồn hiện hành của bảng Top N.")
        return AgentIntent(intent="QUERY_DATA", query=previous.model_copy(deep=True))
    explicit_roles = {role[1] for role in roles}
    if len(explicit_roles) > 1 or (
        source_matches
        and explicit_roles
        and any(
            dataset not in _by_name(" ".join(explicit_roles), candidates) for dataset in selected
        )
    ):
        return _clarify("Bạn muốn dùng một nguồn hay xem riêng từng nguồn?")
    if sum(map(bool, (total or grouped, distinct, count, top, negative, lookup, extrema))) > 1:
        return _clarify("Bạn muốn xem phép tính hay danh sách giao dịch nào trước?")
    recent_totals = catalogue.previous_source_queries.copy()
    if catalogue.earlier_source_total:
        recent_totals.append(catalogue.earlier_source_total)
    if (
        text.startswith("hai nguon")
        and comparison
        and len(recent_totals) == 2
        and all(
            q.project_id == catalogue.context.project_id
            and q.source_id in {t.canonical_id for d in candidates for t in d.tables}
            and len(q.aggregations) == 1
            and q.aggregations[0].op == "sum_decimal"
            and not q.group_by
            for q in recent_totals
        )
    ):
        if len({q.source_id for q in recent_totals}) != 2:
            return _clarify("Bạn muốn so sánh hai nguồn nào?")
        return AgentIntent(
            intent="QUERY_DATA", source_queries=recent_totals, compare_source_totals=True
        )
    if text.startswith("hai nguon") and comparison:
        return _clarify("Hãy chọn hai tổng tiền cần so sánh.")
    if re.search(r"\b(?:bao gom|lay ca|tinh ca) (?:cac )?(?:giao dich )?dong hang\b", text):
        return _clarify(
            "Top N trả tối đa N dòng. Bạn muốn chọn hạng nào để xem số giao dịch đồng hạng?"
        )
    has_name = bool(selected or re.search(rf"\b{ROLE}\b|\.(?:csv|xlsx)\b", scope_text))
    if (has_name and len(selected) != 1) or (all_sources and selected):
        return _clarify("Hãy chọn tên tệp chính xác trong dự án để xác định nguồn cần dùng.")
    if change_source or compare_with or refine or dates_only or top_followup:
        if not previous:
            return _clarify("Bạn muốn dùng nguồn và bảng nào cho yêu cầu tiếp theo?")
    if (
        compare_with
        and previous
        and (
            len(previous.aggregations) != 1
            or previous.aggregations[0].op != "sum_decimal"
            or previous.group_by
            or len(catalogue.previous_source_queries) != 1
        )
    ):
        return _clarify("Bạn muốn so sánh tổng tiền nào với nguồn vừa nêu?")
    prior = [
        d
        for d in candidates
        if previous and any(t.canonical_id == previous.source_id for t in d.tables)
    ]
    multi = all_sources or comparison
    if not selected:
        if multi:
            selected = candidates
        elif prior:
            selected = prior
        elif catalogue.context.dataset_id:
            selected = [d for d in candidates if d.id == catalogue.context.dataset_id]
        elif len(candidates) == 1:
            selected = candidates
        elif lookup:
            return None  # Exact code lookup already has a scoped cross-source reader.
    if not selected:
        return _clarify(
            "Bạn muốn dùng nguồn nào? Có thể nêu tên tệp hoặc yêu cầu xem riêng từng nguồn."
        )
    if comparison and len(selected) < 2:
        return _clarify("Cần ít nhất hai nguồn để so sánh các tổng.")
    if re.search(r"\b(?:ba|3) nguon\b", text) and len(selected) != 3:
        return _clarify("Hãy chọn đúng ba nguồn cần tính trong dự án.")
    try:
        period = (
            _period(calendars[0][0], catalogue.previous_source_year if previous else None)
            if calendars
            else None
        )
    except (ValueError, OverflowError):
        return _clarify("Khoảng ngày nào cần dùng? Hãy ghi rõ ngày hoặc tháng và năm.")
    prior_totals = (
        {q.source_id: q for q in catalogue.previous_source_queries}
        if (refine or dates_only) and len(catalogue.previous_source_queries) > 1
        else {}
    )
    if prior_totals:
        if any(q.project_id != catalogue.context.project_id for q in prior_totals.values()):
            return _clarify("Hãy chọn lại bảng trong dự án hiện tại.")
        selected = [d for d in candidates if any(t.canonical_id in prior_totals for t in d.tables)]
        if len(selected) != len(prior_totals):
            return _clarify("Một nguồn đã đổi. Hãy chọn lại các bảng cần dùng.")
    queries = []
    base_query = previous
    for dataset in selected:
        tables = [
            t
            for t in dataset.tables
            if t.canonical_id and t.schema_definition and t.canonical_status != "FAILED"
        ]
        if len(tables) != 1:
            return _clarify(
                f"Nguồn {dataset.name} cần một bảng chuẩn hóa hiện hành để thực hiện yêu cầu."
            )
        table = tables[0]
        schema = table.schema_definition
        assert schema and table.canonical_id
        previous = prior_totals.get(table.canonical_id, base_query)
        keys = [
            f.id
            for f in schema.fields
            if f.data_type == "string"
            and "order" in field_name_tokens(f.id)
            and {"id", "reference"}.intersection(field_name_tokens(f.id))
        ]
        days = [f.id for f in schema.fields if f.data_type == "date"]
        money = source_measures(schema)
        if explicit_measure and explicit_measure[1] in measure_names:
            money = [m for m in money if explicit_measure[1] in _field_names(m.field_id, m.name)]
        if ranked and ranked[2] in measure_names:
            money = [m for m in money if ranked[2] in _field_names(m.field_id, m.name)]
        if "doanh thu" in action:
            money = [m for m in money if "revenue" in field_name_tokens(m.semantic_metric)]
        if "thuan" in action:
            money = [m for m in money if "net" in field_name_tokens(m.semantic_metric)]
        if "chua vat" in action or "truoc vat" in action:
            money = [m for m in money if m.amount_basis == "net_excluding_tax"]
        if "sau vat" in action or "gom vat" in action:
            money = [m for m in money if m.amount_basis in {"including_tax", "gross_including_tax"}]
        if currencies:
            money = [m for m in money if m.currency == currencies[0][1].upper()]
        uses_previous = bool(
            change_source or compare_with or refine or dates_only or filter_only or top_followup
        )
        if uses_previous and previous:
            if previous.source_id != table.canonical_id and (
                previous.filters or previous.group_by or previous.sort or previous.select_fields
            ):
                return _clarify("Hãy xác nhận lại các bộ lọc và trường khi chuyển sang nguồn khác.")
            if previous.source_measure_id:
                money = [m for m in money if m.field_id == previous.source_measure_id]
        needs_money = bool(
            total
            or grouped
            or top
            or negative
            or extrema
            or comparison
            or refine
            or (uses_previous and previous and previous.source_measure_id)
        )
        if needs_money and len(money) != 1:
            names = ", ".join(m.name for m in money)
            return _clarify(
                f"Trong {dataset.name}, bạn muốn tính loại tiền nào? "
                f"Các chỉ tiêu hiện có gồm {names}."
                if names
                else f"{dataset.name} chưa có chỉ tiêu tiền phù hợp đã xác nhận. "
                "Bạn muốn kiểm tra định nghĩa cột nào?"
            )
        measure = money[0] if needs_money else None
        query = DataQuery(
            project_id=catalogue.context.project_id,
            source_kind="CANONICAL",
            source_id=table.canonical_id,
        )
        if uses_previous and previous:
            query = previous.model_copy(
                deep=True, update={"source_id": table.canonical_id, "offset": 0}
            )
        if measure:
            query.source_measure_id = measure.field_id
            query.currency_field = (
                "currency" if any(f.id == "currency" for f in schema.fields) else None
            )
        if (period or grouped or refine) and len(days) != 1:
            return _clarify(f"Cần xác định cột ngày giao dịch của {dataset.name}.")
        if period:
            query.filters = [f for f in query.filters if f.field_id != days[0]]
            query.filters.append(period.bind(days[0]))
        try:
            bound = [_status_filter(status, table) for status in statuses]
            bound.extend(_field_filter(predicate, original, table) for predicate in filters)
        except DomainError as exc:
            return _clarify(exc.message_vi)
        if len({rule.field_id for rule in bound}) != len(bound):
            return _clarify("Bạn muốn kết hợp những giá trị lọc này như thế nào?")
        for rule in bound:
            if filter_only:
                query.filters = [f for f in query.filters if f.field_id != rule.field_id]
            query.filters.append(rule)
        if currencies and not measure:
            if not any(
                f.id == "currency" and f.data_type in {"string", "enum"} for f in schema.fields
            ):
                return _clarify("Nguồn chưa có trường tiền tệ đã xác nhận.")
            query.filters.append(
                QueryFilter(field_id="currency", op="eq", value=currencies[0][1].upper())
            )
        if len(query.filters) > 8:
            return _clarify("Hãy chọn tối đa tám điều kiện lọc cho một bảng.")
        if distinct or lookup:
            if len(keys) != 1:
                return _clarify(f"Cột nào là mã đơn hàng trong {dataset.name}?")
            if distinct:
                query.aggregations = [QueryAggregation(op="count_distinct", field_id=keys[0])]
            if lookup:
                exact = re.search(
                    r"([A-Za-z0-9_-]+)(?:\s+và cho xem dòng nguồn)?[.?!\s]*$", goal, re.IGNORECASE
                )
                assert exact
                query.filters = [QueryFilter(field_id=keys[0], op="eq", value=exact[1])]
        if count:
            query.aggregations = [QueryAggregation(op="count")]
        if measure and (total or comparison or grouped or refine or extrema):
            op = (
                "sum_decimal"
                if not extrema
                else ("min" if extrema[1] in {"nho", "thap"} else "max")
            )
            query.aggregations = [QueryAggregation(op=op, field_id=measure.field_id)]
        if grouped or refine:
            query.group_by = [days[0]]
            query.calendar_bucket = "month" if buckets[0][1] == "thang" else "day"
            query.limit = 50
            query.sort = []
            query.ranking_size = None
        if top and measure:
            if not 1 <= int(top[1]) <= 50:
                return _clarify(
                    "Bạn muốn xem bao nhiêu giao dịch? Mỗi bảng hiển thị tối đa 50 dòng."
                )
            query.sort = [QuerySort(field_id=measure.field_id, descending=True)]
            query.limit = int(top[1])
            query.ranking_size = int(top[1])
            query.aggregations = []
            query.group_by = []
            query.calendar_bucket = None
        if negative and measure:
            query.filters.append(QueryFilter(field_id=measure.field_id, op="lt", value="0"))
        if dates_only and measure and "giao dich" in text:
            query.filters = [f for f in query.filters if f.field_id != measure.field_id]
            query.sort = []
            query.limit = 25
            query.aggregations = []
            query.group_by = []
            query.calendar_bucket = None
            query.ranking_size = None
        queries.append(query)
    if compare_with and previous:
        if previous.source_id == queries[0].source_id:
            return _clarify("Bạn muốn so sánh với nguồn nào khác?")
        return AgentIntent(
            intent="QUERY_DATA", source_queries=[previous, *queries], compare_source_totals=True
        )
    return AgentIntent(
        intent="QUERY_DATA",
        query=queries[0] if len(queries) == 1 else None,
        source_queries=queries if len(queries) > 1 else [],
        compare_source_totals=comparison,
    )
