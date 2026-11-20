"""Đọc tệp CSV/XLSX thành các bảng dữ liệu dạng chữ.

Nguyên tắc:
- Mọi ô được đọc ở dạng chữ để không làm mất số 0 đầu mã (`00123`) hay số điện thoại.
  Việc hiểu một ô là tiền hay ngày thuộc bước chuẩn hóa sau này.
- Mỗi dòng dữ liệu mang `row_ref`: số dòng trong tệp gốc (tính từ 1), để mọi kết quả
  về sau truy ngược được về đúng dòng gốc.
"""

import csv
import io
from dataclasses import dataclass

import fastexcel
import polars as pl

# Tên cột kỹ thuật chứa số dòng gốc trong tệp Parquet.
ROW_REF = "__row_ref"
# Số dòng đầu tiên dùng để tìm dòng tiêu đề.
HEADER_SCAN_ROWS = 50


class ReadError(Exception):
    """Lỗi đọc tệp, kèm thông điệp tiếng Việt để hiện cho người dùng."""


@dataclass
class RawSheet:
    """Toàn bộ ô của một sheet (hoặc của tệp CSV) trước khi tách dòng tiêu đề.

    Cột `frame` đặt tên tạm; dòng thứ i của frame là dòng `first_row + i` trong tệp gốc.
    """

    name: str | None
    frame: pl.DataFrame
    first_row: int = 1


@dataclass
class ReadTable:
    """Bảng đã tách tiêu đề: tên cột thật và các dòng dữ liệu kèm số dòng gốc."""

    header_row: int | None
    column_names: list[str]
    frame: pl.DataFrame  # cột ROW_REF + các cột dữ liệu (đều là chữ)


# ---------------------------------------------------------------- đọc tệp


def decode_utf8(content: bytes) -> str:
    """Giải mã UTF-8 (có hoặc không có BOM); bảng mã khác thì báo lỗi rõ ràng."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ReadError(
            "Tệp CSV không dùng bảng mã UTF-8. Hãy lưu lại tệp ở dạng 'CSV UTF-8' rồi tải lên lại."
        ) from error


def detect_delimiter(text: str) -> str:
    """Đoán dấu phân cách cột từ phần đầu tệp; không chắc chắn thì dùng dấu phẩy."""
    sample = text[: 64 * 1024]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_csv(content: bytes) -> RawSheet:
    text = decode_utf8(content)
    if not text.strip():
        raise ReadError("Tệp CSV trống.")
    frame = pl.read_csv(
        io.BytesIO(text.encode("utf-8")),
        has_header=False,
        separator=detect_delimiter(text),
        infer_schema=False,  # mọi cột giữ dạng chữ
        truncate_ragged_lines=True,
        raise_if_empty=False,
    )
    return RawSheet(name=None, frame=frame)


def read_xlsx(content: bytes) -> list[RawSheet]:
    """Đọc mọi sheet đang hiển thị; sheet ẩn thường là bảng tra cứu nội bộ nên bỏ qua."""
    if not content.startswith(b"PK"):
        raise ReadError("Tệp không phải Excel .xlsx hợp lệ.")
    try:
        reader = fastexcel.read_excel(content)
        sheets: list[RawSheet] = []
        for name in reader.sheet_names:
            # header_row=None, skip_rows=0: lấy đủ mọi dòng từ dòng 1, kể cả dòng trống ở đầu,
            # để số dòng trong frame trùng với số dòng Excel.
            sheet = reader.load_sheet(name, header_row=None, skip_rows=0, dtypes="string")
            if sheet.visible != "visible":
                continue
            sheets.append(RawSheet(name=name, frame=sheet.to_polars()))
    except ReadError:
        raise
    except Exception as error:
        raise ReadError("Không đọc được tệp Excel. Tệp có thể bị hỏng hoặc có mật khẩu.") from error
    return sheets


# ---------------------------------------------------------------- tìm dòng tiêu đề


def _cell_texts(row: tuple[object, ...]) -> list[str]:
    return [str(value).strip() for value in row if value is not None and str(value).strip()]


def _looks_like_label(value: str) -> bool:
    """Ô tiêu đề thường là chữ; ô toàn số, ngày hay tiền thì không phải tên cột."""
    stripped = value.replace(".", "").replace(",", "").replace("/", "").replace("-", "")
    stripped = stripped.replace(":", "").replace(" ", "")
    return not stripped.isdigit()


def detect_header_row(frame: pl.DataFrame) -> int | None:
    """Đoán vị trí (tính từ 0) của dòng tiêu đề trong phần đầu sheet.

    Quy tắc kinh nghiệm: dòng tiêu đề là dòng đầu tiên có ít nhất một nửa số cột
    của bảng có giá trị, gần như toàn bộ là chữ (không phải số), và ngay sau nó có dữ liệu.
    Dòng tiêu đề báo cáo phía trên (chỉ một ô) bị bỏ qua. Người dùng có thể chỉnh lại.
    """
    rows = list(frame.head(HEADER_SCAN_ROWS).iter_rows())
    filled = [_cell_texts(row) for row in rows]
    widest = max((len(cells) for cells in filled), default=0)
    if widest < 2:
        return None
    needed = max(2, -(-widest // 2))  # làm tròn lên một nửa
    for index, cells in enumerate(filled[:-1]):
        if len(cells) < needed:
            continue
        label_share = sum(_looks_like_label(cell) for cell in cells) / len(cells)
        if label_share >= 0.8 and len(filled[index + 1]) >= 1:
            return index
    return None


# ---------------------------------------------------------------- tách bảng


def _unique_names(raw_names: list[str | None]) -> list[str]:
    """Tên cột rỗng thành 'Cột N'; tên trùng thêm hậu tố ' (2)', ' (3)'…"""
    names: list[str] = []
    seen: dict[str, int] = {}
    for position, raw in enumerate(raw_names, start=1):
        base = (raw or "").strip() or f"Cột {position}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        names.append(base if count == 1 else f"{base} ({count})")
    return names


def build_table(raw: RawSheet, header_index: int | None) -> ReadTable:
    """Tách dòng tiêu đề và trả về các dòng dữ liệu kèm số dòng gốc.

    `header_index` tính từ 0 trong frame; None nghĩa là sheet không có dòng tiêu đề.
    """
    frame = raw.frame
    if frame.height == 0 or frame.width == 0:
        return ReadTable(header_row=None, column_names=[], frame=pl.DataFrame({ROW_REF: []}))

    data_start = 0 if header_index is None else header_index + 1
    header_values: list[str | None] = (
        [None] * frame.width
        if header_index is None
        else [None if value is None else str(value) for value in frame.row(header_index)]
    )
    data = frame.slice(data_start)

    # Bỏ cột không có tên và hoàn toàn trống (thường là cột thừa ở mép bảng).
    keep = [
        position
        for position, column in enumerate(data.columns)
        if header_values[position] not in (None, "") or data[column].drop_nulls().len() > 0
    ]
    names = _unique_names([header_values[position] for position in keep])
    data = data.select(
        [pl.col(data.columns[p]).alias(name) for p, name in zip(keep, names, strict=True)]
    )

    # Gắn số dòng gốc, rồi bỏ các dòng trống ở cuối bảng (không bỏ dòng trống ở giữa).
    data = data.with_row_index(ROW_REF, offset=raw.first_row + data_start)
    data = data.with_columns(pl.col(ROW_REF).cast(pl.Int64))
    non_empty = data.select(
        pl.any_horizontal([pl.col(name).str.strip_chars().str.len_chars() > 0 for name in names])
        if names
        else pl.lit(False)
    ).to_series()
    last = max((index for index, flag in enumerate(non_empty) if flag), default=-1)
    data = data.head(last + 1)

    header_row = None if header_index is None else raw.first_row + header_index
    return ReadTable(header_row=header_row, column_names=names, frame=data)


def header_index_from_row(raw: RawSheet, header_row: int) -> int:
    """Đổi số dòng tiêu đề người dùng chọn (tính từ 1) thành vị trí trong frame."""
    index = header_row - raw.first_row
    if not 0 <= index < raw.frame.height:
        raise ReadError(f"Dòng tiêu đề {header_row} nằm ngoài phạm vi của bảng.")
    return index
