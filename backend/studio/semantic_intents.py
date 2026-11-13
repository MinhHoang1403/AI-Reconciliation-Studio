"""Resolve bounded source analytics against the current canonical catalogue."""

import re
from datetime import date, timedelta

from studio.assistant import plain_question
from studio.contracts import SchemaDefinition
from studio.contracts.agent import AgentIntent, DatasetContext, IntentCatalogue
from studio.contracts.data_query import DataQuery, QueryAggregation, QueryFilter, QuerySort
from studio.data_query import source_measures
from studio.errors import DomainError
from studio.profiling import field_name_tokens

ROLE = r"(?:(?:bao cao|so) )?(ban hang|thu ngan|ke toan)"
DATE = r"\d{1,2}/\d{1,2}/\d{4}"
DAY_RANGE = rf"(?:tu )?({DATE}) den (?:het |ngay )?({DATE})"
MONTH = r"thang (\d{1,2})(?:/(\d{4}))?"
MONEY = r"(?:so tien|tien|doanh thu(?: thuan)?(?: chua vat)?|gia tri)"


def validate_source_money_language(
    goal: str, query: DataQuery, schema: SchemaDefinition | None
) -> None:
    """A provider can propose an existing measure only when the user's words authorize it."""
    text = plain_question(goal)
    if not schema or not re.search(r"\b(?:tong|sum|total)\b", text):
        raise DomainError(
            "QUERY_SEMANTICS_REQUIRED", "Cần nêu phép tính tổng và chỉ tiêu của nguồn."
        )
    measures = source_measures(schema)
    if "doanh thu" in text:
        measures = [m for m in measures if "revenue" in field_name_tokens(m.semantic_metric)]
    if "thuan" in text:
        measures = [m for m in measures if "net" in field_name_tokens(m.semantic_metric)]
    if "chua vat" in text:
        measures = [m for m in measures if m.amount_basis == "net_excluding_tax"]
    if match := re.search(r"\b(vnd|usd|eur)\b", text):
        measures = [m for m in measures if m.currency == match[1].upper()]
    explicit = [m for m in measures if plain_question(m.name).replace("_", " ") in text]
    candidates = explicit or measures
    if len(candidates) != 1 or {
        a.field_id for a in query.aggregations if a.op == "sum_decimal"
    } != {candidates[0].field_id}:
        raise DomainError(
            "QUERY_SEMANTICS_REQUIRED", "Bạn muốn tính loại tiền nào trong nguồn đã chọn?"
        )


def source_scope_explicit(goal: str) -> bool:
    text = plain_question(goal)
    return bool(
        re.search(rf"\b{ROLE}\b|\b(?:ca ba|ba|3|hai|tung|moi|tat ca(?: cac)?) nguon\b", text)
    )


def _clarify(question: str) -> AgentIntent:
    return AgentIntent(intent="CLARIFY", questions=[question])


def _by_name(text: str, datasets: list[DatasetContext]) -> list[DatasetContext]:
    filenames = [
        d
        for d in datasets
        if re.search(rf"(?<![\w.-]){re.escape(plain_question(d.name))}(?![\w.-])", text)
    ]
    if filenames:
        return filenames
    role = re.search(rf"\b{ROLE}\b", text)
    if not role:
        return []
    result = []
    for dataset in datasets:
        words = " ".join(re.findall(r"[a-z0-9]+", plain_question(dataset.name)))
        if f" {role[1]} " in f" {words} " or any(
            table.schema_definition
            and plain_question(table.schema_definition.entity_kind) == role[1]
            for table in dataset.tables
        ):
            result.append(dataset)
    return result


def _period(text: str, previous: DataQuery | None) -> tuple[str, str] | None:
    if match := re.search(DAY_RANGE, text):
        days = []
        for value in match.groups():
            day, month, year = map(int, value.split("/"))
            days.append(date(year, month, day))
        if days[0] > days[1]:
            raise ValueError("range")
        return days[0].isoformat(), (days[1] + timedelta(days=1)).isoformat()
    if match := re.search(MONTH, text):
        month = int(match[1])
        year = (
            int(match[2])
            if match[2]
            else next(
                (
                    int(f.value[0][:4])
                    for f in previous.filters
                    if f.op == "between"
                    and isinstance(f.value, list)
                    and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.value[0])
                ),
                0,
            )
            if previous
            else 0
        )
        start = date(year, month, 1)
        return start.isoformat(), date(year + (month == 12), month % 12 + 1, 1).isoformat()
    return None


def resolve_source_read(goal: str, catalogue: IntentCatalogue) -> AgentIntent | None:
    """Source amounts, order identifiers and follow-ups use approved fields only."""
    text = " ".join(plain_question(goal).split()).rstrip(" ?!.")
    if re.search(r"\b(?:khong|dung|chua) (?:duoc |can |hay )?(?:tinh tong|cong tong)\b", text):
        return AgentIntent(
            intent="UNSUPPORTED", questions=["Đã ghi nhận yêu cầu bỏ phép tính tổng."]
        )
    if re.search(r"[;!?]|\.\s|\b(?:roi|sau do|dong thoi|xoa|cap nhat|bo qua)\b", text):
        return None
    if re.search(r"\b(?:doi soat|luot chay|nhom khop|chenh lech)\b", text) and not re.fullmatch(
        r"hai nguon chenh nhau bao nhieu", text
    ):
        return None
    previous = catalogue.previous_query
    if (
        not previous
        or previous.source_kind != "CANONICAL"
        or previous.project_id != catalogue.context.project_id
    ):
        previous = None
    change_source = re.fullmatch(rf"con {ROLE}", text)
    refine = re.match(
        r"^(?:(?:tiep tuc|hay) )?(?:nhom ket qua nay|hien thi) theo (?:tung )?(?:ngay|thang)$", text
    )
    dates_only = re.match(rf"^(?:chi lay|loc) (?:giao dich )?(?:{DAY_RANGE}|{MONTH})$", text)
    all_sources = bool(re.search(r"\b(?:ca ba|ba|3|tung|moi|tat ca(?: cac)?) nguon\b", text))
    comparison = bool(
        re.fullmatch(
            r"(?:ba nguon|ba tong tien nay|hai nguon) "
            r"(?:co tong tien bang nhau khong|co bang nhau khong|chenh nhau bao nhieu)",
            text,
        )
    )
    total = bool(re.search(rf"\b(?:tong|tong cong) {MONEY}\b", text))
    grouped = bool(re.search(rf"\b{MONEY} (?:theo )?tung (?:ngay|thang)\b", text))
    distinct = bool(
        re.search(r"\b(?:bao nhieu|dem) ma don(?: hang)? (?:duy nhat|khac nhau)\b", text)
    )
    count = bool(re.fullmatch(r"(?:co )?bao nhieu giao dich(?: (?:trong|cua) .+)?", text))
    top = re.fullmatch(
        rf"(?:hien thi|xem|cho toi xem) (\d{{1,2}}) (?:don hang|giao dich)"
        rf"(?: co)? {MONEY} (?:cao|lon) nhat(?: (?:cua|trong) .+)?",
        text,
    )
    negative = bool(
        re.fullmatch(
            rf"(?:co |xem |liet ke )?(?:nhung |cac )?giao dich"
            rf"(?: co)? {MONEY} am(?: nao)?(?: (?:cua|trong) .+)?",
            text,
        )
    )
    lookup = re.fullmatch(
        r"(?:hay )?tim (?:don |ma(?: don hang)? )([a-z0-9_-]{1,64})(?: va cho xem dong nguon)?",
        text,
    )
    extrema = re.search(rf"\b{MONEY} (nho|thap|lon|cao) nhat\b", text) if not top else None
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
            refine,
            dates_only,
        )
    ):
        return None
    if "thang" in text and re.search(r"\bthang\s+\d", text) and not re.search(MONTH, text):
        return _clarify("Hãy ghi rõ tháng và năm cần tính.")
    if re.search(
        r"\b(?:theo khach|theo cua hang|va xuat|va doi chieu|tien mat|chuyen khoan)\b", text
    ):
        return _clarify(
            "Hãy chọn đúng chỉ tiêu, tiền tệ và điều kiện đã xác nhận của nguồn cần tính."
        )
    candidates = catalogue.datasets
    selected = _by_name(text, candidates)
    has_name = bool(re.search(rf"\b{ROLE}\b|\.(?:csv|xlsx)\b", text))
    if has_name and len(selected) != 1:
        return _clarify("Hãy chọn tên tệp chính xác trong dự án để xác định nguồn cần dùng.")
    if change_source or refine or dates_only:
        if not previous:
            return _clarify("Bạn muốn dùng nguồn và bảng nào cho yêu cầu tiếp theo?")
    prior = [
        d
        for d in candidates
        if previous and any(t.canonical_id == previous.source_id for t in d.tables)
    ]
    multi = all_sources or comparison
    if not selected:
        if multi:
            previous_ids = {q.source_id for q in catalogue.previous_source_queries}
            selected = (
                [d for d in candidates if any(t.canonical_id in previous_ids for t in d.tables)]
                if text.startswith("hai nguon")
                else candidates
            )
            if text.startswith("hai nguon") and len(selected) != 2:
                return _clarify("Bạn muốn so sánh hai nguồn nào?")
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
        period = _period(text, previous)
    except (ValueError, OverflowError):
        return _clarify("Khoảng ngày nào cần dùng? Hãy ghi rõ ngày hoặc tháng và năm.")
    queries = []
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
        keys = [
            f.id
            for f in schema.fields
            if f.data_type == "string"
            and "order" in field_name_tokens(f.name)
            and {"id", "reference"}.intersection(field_name_tokens(f.name))
        ]
        days = [f.id for f in schema.fields if f.data_type == "date"]
        money = source_measures(schema)
        if "doanh thu" in text:
            money = [m for m in money if "revenue" in field_name_tokens(m.semantic_metric)]
        if "thuan" in text:
            money = [m for m in money if "net" in field_name_tokens(m.semantic_metric)]
        if "chua vat" in text:
            money = [m for m in money if m.amount_basis == "net_excluding_tax"]
        if "sau vat" in text or "gom vat" in text:
            money = [m for m in money if m.amount_basis in {"including_tax", "gross_including_tax"}]
        if "gross" in text:
            money = [m for m in money if m.amount_basis == "gross"]
        if currency := re.search(r"\b(vnd|usd|eur)\b", text):
            money = [m for m in money if m.currency == currency[1].upper()]
        uses_previous = bool(change_source or refine or dates_only)
        if uses_previous and previous and previous.source_measure_id:
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
        if (period or grouped or refine) and len(days) != 1:
            return _clarify(f"Cần xác định cột ngày giao dịch của {dataset.name}.")
        if period:
            query.filters = [f for f in query.filters if f.field_id != days[0]]
            query.filters.append(QueryFilter(field_id=days[0], op="between", value=list(period)))
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
            query.calendar_bucket = (
                "month" if re.search(r"theo (?:tung )?thang|tung thang", text) else "day"
            )
            query.limit = 50
            query.sort = []
        if top and measure:
            if not 1 <= int(top[1]) <= 50:
                return _clarify(
                    "Bạn muốn xem bao nhiêu giao dịch? Mỗi bảng hiển thị tối đa 50 dòng."
                )
            query.sort = [QuerySort(field_id=measure.field_id, descending=True)]
            query.limit = int(top[1])
        if negative and measure:
            query.filters.append(QueryFilter(field_id=measure.field_id, op="lt", value="0"))
        if dates_only and measure:
            query.filters = [f for f in query.filters if f.field_id != measure.field_id]
            query.sort = []
            query.limit = 25
            query.aggregations = []
            query.group_by = []
            query.calendar_bucket = None
        queries.append(query)
    return AgentIntent(
        intent="QUERY_DATA",
        query=queries[0] if len(queries) == 1 else None,
        source_queries=queries if len(queries) > 1 else [],
        compare_source_totals=comparison,
    )
