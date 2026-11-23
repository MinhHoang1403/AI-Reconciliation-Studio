"""Dựng bộ dữ liệu sạch cho một bảng và tìm các vấn đề cần xử lý (docs/ARCHITECTURE.md 4.3–4.4).

Đầu vào: bảng đã đọc (mọi ô dạng chữ), ánh xạ cột, các ô người dùng đã sửa, các quyết định
giữ/loại dòng và lựa chọn thứ tự ngày. Đầu ra: một phiên bản sạch mới (Parquet, cột chuẩn
đúng kiểu) kèm nhật ký sửa tự động và danh sách vấn đề theo ba mức:
- AUTO: tự sửa và ghi nhật ký (định dạng số/ngày, khoảng trắng, đầu số 84, dòng trống…).
- SUGGEST: gợi ý, người dùng đồng ý một lần (dòng trùng y hệt).
- ASK: dừng ở đúng ô, chờ người dùng sửa hoặc loại dòng (thiếu mã, ô không đọc được,
  cùng mã khác số tiền).
Dựng lại từ đầu mỗi lần nên kết quả luôn xác định; tệp gốc không bao giờ bị sửa (R15).
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import polars as pl
from sqlalchemy import func, select

from studio import database, storage
from studio.models import CellCorrection, CleanVersion, DatasetTable, RowDecision
from studio.reading import ROW_REF
from studio.sales_fields import FIELDS_BY_KEY
from studio.table_locks import table_lock
from studio.value_parsers import (
    DateOrder,
    NumberStyle,
    Parsed,
    detect_date_order,
    detect_number_style,
    is_blank,
    is_cancelled_status,
    name_match_key,
    parse_date,
    parse_identifier,
    parse_money,
    parse_phone,
    parse_text,
)

logger = logging.getLogger(__name__)

# Trường bắt buộc theo loại bảng; mỗi phần tử là nhóm "ít nhất một trong các cột này".
REQUIRED_FIELDS: dict[str, list[tuple[str, ...]]] = {
    "ORDERS_PLATFORM": [("order_id",), ("amount",)],
    "ORDERS_POS": [("order_id",), ("amount",)],
    "PAYMENT_GATEWAY": [("amount",), ("payment_id", "order_id")],
    "BANK_STATEMENT": [("transaction_date",), ("debit", "credit")],
}
# Cột mã mà mỗi dòng phải khác nhau; cùng mã nhưng khác số tiền là mâu thuẫn.
KEY_FIELD = {
    "ORDERS_PLATFORM": "order_id",
    "ORDERS_POS": "order_id",
    "PAYMENT_GATEWAY": "payment_id",
}
EXAMPLES_PER_FIX = 3
CENT = Decimal("0.01")

FIX_LABELS = {
    "NUMBER_FORMAT": "Đổi định dạng số tiền về số",
    "SHORTHAND_AMOUNT": "Đọc số tiền viết tắt (tr, k)",
    "DATE_FORMAT": "Đổi ngày về dạng năm-tháng-ngày",
    "EXCEL_SERIAL_DATE": "Đổi số ngày kiểu Excel thành ngày",
    "WHITESPACE": "Bỏ khoảng trắng thừa",
    "PHONE_PREFIX": "Đổi đầu số 84 thành 0",
    "PHONE_FORMAT": "Bỏ dấu cách, dấu chấm trong số điện thoại",
    "PHONE_LEADING_ZERO": "Thêm số 0 bị mất ở đầu số điện thoại",
    "EXCEL_NUMBER_CODE": "Bỏ đuôi .0 của mã bị Excel đọc thành số",
    "USER_CORRECTION": "Giá trị bạn đã sửa",
}


@dataclass
class ColumnPlan:
    """Cách đọc một cột: tên cột gốc, cột chuẩn, kiểu số/thứ tự ngày suy từ cả cột."""

    column: str
    field_key: str
    number_style: NumberStyle = "VN"
    date_order: DateOrder = "DMY"
    date_order_defaulted: bool = False


@dataclass
class Correction:
    """Giá trị người dùng sửa cho một ô, kèm ô gốc lúc sửa (cột trong tệp, giá trị gốc)."""

    value: str
    source_column: str | None = None
    original_value: str | None = None

    def applies_to(self, column: str, original: str | None) -> bool:
        """Chỉ áp dụng khi ô hiện tại vẫn là ô đã sửa: cùng cột gốc, cùng giá trị gốc.

        Bản sửa cũ chưa ghi ô gốc (source_column trống) thì áp dụng như trước.
        """
        if self.source_column is None:
            return True
        return self.source_column == column and self.original_value == original


@dataclass
class BuildInput:
    table_id: uuid.UUID
    table_kind: str | None
    raw: pl.DataFrame
    plans: list[ColumnPlan]
    corrections: dict[tuple[int, str], Correction]
    decisions: dict[int, str]
    date_order_choices: dict[str, str]


@dataclass
class BuildOutput:
    frame: pl.DataFrame
    excluded_count: int
    summary: dict[str, Any]
    issues: list[dict[str, Any]] = field(default_factory=list)


def parse_cell(raw: str | None, plan: ColumnPlan) -> Parsed:
    field_type = FIELDS_BY_KEY[plan.field_key].type
    if field_type == "MONEY":
        return parse_money(raw, plan.number_style)
    if field_type == "DATE":
        return parse_date(raw, plan.date_order)
    if field_type == "IDENTIFIER":
        return parse_identifier(raw)
    if field_type == "PHONE":
        return parse_phone(raw)
    return parse_text(raw)


def parse_user_value(value: str, field_key: str) -> Parsed:
    """Đọc giá trị người dùng (hoặc AI) nhập cho một ô.

    Tiền: thử kiểu Việt trước (1.250.000), không được thì kiểu Anh (1,250,000), vì một ô lẻ
    không có cả cột để suy kiểu. Ngày: ngày/tháng hoặc năm-tháng-ngày.
    """
    plan = ColumnPlan(column="", field_key=field_key)
    parsed = parse_cell(value, plan)
    if parsed.state == "INVALID" and FIELDS_BY_KEY[field_key].type == "MONEY":
        plan.number_style = "EN"
        parsed = parse_cell(value, plan)
    return parsed


def _plan_columns(
    raw: pl.DataFrame, mappings: list[tuple[str, str]], date_order_choices: dict[str, str]
) -> list[ColumnPlan]:
    plans = []
    for column, field_key in mappings:
        plan = ColumnPlan(column=column, field_key=field_key)
        values = [value for value in raw[column].to_list() if not is_blank(value)]
        field_type = FIELDS_BY_KEY[field_key].type
        if field_type == "MONEY":
            plan.number_style = detect_number_style(values)
        if field_type == "DATE":
            chosen = date_order_choices.get(field_key)
            if chosen in ("DMY", "MDY"):
                plan.date_order = chosen  # type: ignore[assignment]
            else:
                plan.date_order, plan.date_order_defaulted = detect_date_order(values)
        plans.append(plan)
    return plans


def _issue(
    kind: str,
    level: str,
    row_refs: list[int],
    message: str,
    field_key: str | None = None,
    values: list[str | None] | None = None,
    resolved: bool = False,
) -> dict[str, Any]:
    return {
        "id": f"{kind}:{field_key or ''}:{'-'.join(str(ref) for ref in row_refs)}",
        "kind": kind,
        "level": level,
        "field_key": field_key,
        "field_label": FIELDS_BY_KEY[field_key].label if field_key else None,
        "row_refs": row_refs,
        "values": values or [],
        "message": message,
        "status": "RESOLVED" if resolved else "OPEN",
    }


def build(data: BuildInput) -> BuildOutput:
    raw = data.raw
    row_refs: list[int] = raw[ROW_REF].to_list()
    raw_columns = [name for name in raw.columns if name != ROW_REF]
    raw_rows = list(raw.select(raw_columns).iter_rows())
    issues: list[dict[str, Any]] = []

    # 1. Dòng trống hoàn toàn: tự bỏ (mức AUTO).
    empty = {
        ref
        for ref, cells in zip(row_refs, raw_rows, strict=True)
        if all(is_blank(cell) for cell in cells)
    }

    # 2. Dòng trùng y hệt: gợi ý bỏ bản lặp (mức SUGGEST); quyết định của người dùng có hiệu lực.
    groups: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for ref, cells in zip(row_refs, raw_rows, strict=True):
        if ref not in empty:
            groups[tuple((cell or "").strip() for cell in cells)].append(ref)
    for refs in (refs for refs in groups.values() if len(refs) > 1):
        decided = all(ref in data.decisions for ref in refs[1:])
        issues.append(
            _issue(
                "DUPLICATE_ROW",
                "SUGGEST",
                refs,
                f"{len(refs)} dòng giống hệt nhau (dòng gốc {', '.join(map(str, refs))}). "
                "Đề xuất giữ dòng đầu, bỏ các bản lặp; "
                "nếu đây là giao dịch thật lặp lại thì giữ tất cả.",
                resolved=decided,
            )
        )

    excluded = empty | {ref for ref, decision in data.decisions.items() if decision == "EXCLUDE"}
    included = [index for index, ref in enumerate(row_refs) if ref not in excluded]

    # 3. Đọc từng ô theo cột chuẩn; ghi nhật ký sửa và ô không đọc được.
    output: dict[str, list[Any]] = {ROW_REF: [row_refs[index] for index in included]}
    fixes: dict[tuple[str, str], dict[str, Any]] = {}
    parsed_values: dict[str, list[Any]] = {}
    for plan in data.plans:
        position = raw_columns.index(plan.column)
        values: list[Any] = []
        for index in included:
            ref = row_refs[index]
            original = raw_rows[index][position]
            correction = data.corrections.get((ref, plan.field_key))
            if correction is not None and correction.applies_to(plan.column, original):
                parsed = parse_user_value(correction.value, plan.field_key)
                fix: str | None = "USER_CORRECTION"
            else:
                parsed = parse_cell(original, plan)
                fix = parsed.fix
            if parsed.state == "INVALID":
                issues.append(
                    _issue(
                        "INVALID_VALUE",
                        "ASK",
                        [ref],
                        f"Không đọc được “{original}” thành "
                        f"{FIELDS_BY_KEY[plan.field_key].label.lower()}.",
                        plan.field_key,
                        [original],
                    )
                )
            elif fix:
                entry = fixes.setdefault(
                    (plan.field_key, fix),
                    {
                        "field_key": plan.field_key,
                        "field_label": FIELDS_BY_KEY[plan.field_key].label,
                        "fix": fix,
                        "fix_label": FIX_LABELS.get(fix, fix),
                        "count": 0,
                        "examples": [],
                    },
                )
                entry["count"] += 1
                if len(entry["examples"]) < EXAMPLES_PER_FIX:
                    entry["examples"].append(
                        {"row_ref": ref, "before": original, "after": _display(parsed.value)}
                    )
            values.append(parsed.value)
        parsed_values[plan.field_key] = values

    # 4. Thiếu trường bắt buộc theo loại bảng (ô đã báo "không đọc được" thì không báo thêm).
    invalid_cells = {
        (issue["row_refs"][0], issue["field_key"])
        for issue in issues
        if issue["kind"] == "INVALID_VALUE"
    }
    for group in REQUIRED_FIELDS.get(data.table_kind or "", []):
        present = [key for key in group if key in parsed_values]
        if not present:
            continue
        for offset, index in enumerate(included):
            if all(parsed_values[key][offset] is None for key in present):
                ref = row_refs[index]
                if not any((ref, key) in invalid_cells for key in present):
                    labels = " hoặc ".join(FIELDS_BY_KEY[key].label.lower() for key in present)
                    issues.append(
                        _issue(
                            "MISSING_VALUE",
                            "ASK",
                            [ref],
                            f"Dòng này thiếu {labels}. Hãy nhập giá trị hoặc loại dòng.",
                            present[0],
                            [None],
                        )
                    )

    # 5. Cùng mã nhưng khác số tiền: mâu thuẫn, cần người dùng xem.
    key_field = KEY_FIELD.get(data.table_kind or "")
    if key_field in parsed_values and "amount" in parsed_values:
        by_key: dict[str, list[int]] = defaultdict(list)
        for offset, key in enumerate(parsed_values[key_field]):
            if key is not None:
                by_key[key].append(offset)
        for key, offsets in by_key.items():
            amounts = {parsed_values["amount"][offset] for offset in offsets}
            # Số tiền trống (ô không đọc được) xếp cuối, không so sánh None với số.
            ordered = sorted(amounts, key=lambda amount: (amount is None, amount or 0))
            if len(offsets) > 1 and len(amounts) > 1:
                refs = [row_refs[included[offset]] for offset in offsets]
                kept = all(data.decisions.get(ref) == "KEEP" for ref in refs)
                issues.append(
                    _issue(
                        "CONFLICTING_VALUES",
                        "ASK",
                        refs,
                        f"Mã {key} xuất hiện ở {len(refs)} dòng với số tiền khác nhau "
                        f"({', '.join(_money_vi(amount) for amount in ordered)}). "
                        "Sửa số tiền "
                        "đúng, loại dòng sai, hoặc giữ cả nếu đúng là nhiều giao dịch.",
                        "amount",
                        [_display(parsed_values["amount"][offset]) for offset in offsets],
                        resolved=kept,
                    )
                )

    # 6. Dựng bảng sạch đúng kiểu; thêm cột phụ cho đối soát.
    for plan in data.plans:
        values = parsed_values[plan.field_key]
        field_type = FIELDS_BY_KEY[plan.field_key].type
        if field_type == "MONEY":
            output[plan.field_key] = [
                None if value is None else value.quantize(CENT) for value in values
            ]
        else:
            output[plan.field_key] = values
    schema: dict[str, Any] = {ROW_REF: pl.Int64}
    for plan in data.plans:
        field_type = FIELDS_BY_KEY[plan.field_key].type
        schema[plan.field_key] = (
            pl.Decimal(20, 2)
            if field_type == "MONEY"
            else pl.Date
            if field_type == "DATE"
            else pl.String
        )
    if "customer_name" in parsed_values:
        output["customer_name_key"] = [
            None if value is None else name_match_key(value)
            for value in parsed_values["customer_name"]
        ]
        schema["customer_name_key"] = pl.String
    cancelled_count = 0
    if "status" in parsed_values:
        flags = [
            value is not None and is_cancelled_status(value) for value in parsed_values["status"]
        ]
        output["is_cancelled"] = flags
        schema["is_cancelled"] = pl.Boolean
        cancelled_count = sum(flags)
    frame = pl.DataFrame(output, schema=schema)

    summary = {
        "fixes": sorted(fixes.values(), key=lambda item: -item["count"]),
        "empty_rows": sorted(empty),
        "cancelled_count": cancelled_count,
        "date_orders": [
            {
                "field_key": plan.field_key,
                "field_label": FIELDS_BY_KEY[plan.field_key].label,
                "order": plan.date_order,
                "defaulted": plan.date_order_defaulted,
                "chosen_by_user": plan.field_key in data.date_order_choices,
            }
            for plan in data.plans
            if FIELDS_BY_KEY[plan.field_key].type == "DATE"
        ],
    }
    return BuildOutput(frame=frame, excluded_count=len(excluded), summary=summary, issues=issues)


def _money_vi(value: Decimal | None) -> str:
    """Số tiền kiểu Việt để hiển thị trong thông điệp: 2195000 → 2.195.000."""
    if value is None:
        return "trống"
    whole = f"{int(value):,}".replace(",", ".")
    fraction = abs(value) % 1
    return whole if fraction == 0 else f"{whole},{str(fraction.quantize(CENT))[2:]}"


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return (
            format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")
        )
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def build_clean_version(table_id: uuid.UUID) -> None:
    """Dựng phiên bản sạch mới cho bảng (chạy nền); lỗi được ghi lại, không làm hỏng dữ liệu.

    Các lần dựng cùng bảng chạy lần lượt (khóa theo bảng): lần sau luôn đọc đủ mọi sửa đổi
    và luôn là phiên bản mới nhất, không có hai phiên bản trùng số.
    """
    with table_lock(table_id):
        _build_clean_version(table_id)


def _build_clean_version(table_id: uuid.UUID) -> None:
    with database.SessionFactory() as session:
        table = session.get(DatasetTable, table_id)
        if table is None or table.status != "READY" or table.parquet_path is None:
            return
        mappings = [
            (mapping.column_name, mapping.field_key)
            for mapping in table.mappings
            if mapping.field_key
        ]
        if not mappings:
            table.clean_status = "NONE"
            session.commit()
            return
        table.clean_status = "BUILDING"
        session.commit()
        raw = pl.read_parquet(table.parquet_path)
        corrections = {
            (item.row_ref, item.field_key): Correction(
                item.value, item.source_column, item.original_value
            )
            for item in session.scalars(
                select(CellCorrection).where(CellCorrection.table_id == table_id)
            )
        }
        decisions = {
            item.row_ref: item.decision
            for item in session.scalars(select(RowDecision).where(RowDecision.table_id == table_id))
        }
        choices = dict(table.clean_options.get("date_orders", {}))
        data = BuildInput(
            table_id,
            table.table_kind,
            raw,
            _plan_columns(raw, mappings, choices),
            corrections,
            decisions,
            choices,
        )
    try:
        result = build(data)
    except Exception:
        logger.exception("Lỗi khi dựng bộ dữ liệu sạch cho bảng %s", table_id)
        with database.SessionFactory() as session:
            failed = session.get(DatasetTable, table_id)
            if failed is not None:
                failed.clean_status = "FAILED"
                session.commit()
        return

    with database.SessionFactory() as session:
        table = session.get(DatasetTable, table_id)
        if table is None:
            return
        version = (
            session.scalar(
                select(func.max(CleanVersion.version)).where(CleanVersion.table_id == table_id)
            )
            or 0
        ) + 1
        path = storage.tables_dir() / f"{table_id}-sach-phien-ban-{version}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        result.frame.write_parquet(path)
        session.add(
            CleanVersion(
                id=uuid.uuid4(),
                table_id=table_id,
                version=version,
                parquet_path=str(path),
                row_count=result.frame.height,
                excluded_count=result.excluded_count,
                summary=result.summary,
                issues=result.issues,
            )
        )
        table.clean_status = "READY"
        session.commit()


def source_cell(table: DatasetTable, row_ref: int, field_key: str) -> tuple[str, str | None] | None:
    """Ô gốc đang được ánh xạ vào cột chuẩn ở một dòng: (tên cột trong tệp, giá trị gốc).

    Trả None khi cột chuẩn chưa được ánh xạ hoặc không có dòng gốc này.
    """
    column = next(
        (mapping.column_name for mapping in table.mappings if mapping.field_key == field_key),
        None,
    )
    if column is None or table.parquet_path is None:
        return None
    rows = (
        pl.scan_parquet(table.parquet_path)
        .filter(pl.col(ROW_REF) == row_ref)
        .select(column)
        .collect()
    )
    if rows.height == 0:
        return None
    return column, rows[column][0]


def latest_version(table: DatasetTable) -> CleanVersion | None:
    return table.clean_versions[-1] if table.clean_versions else None
