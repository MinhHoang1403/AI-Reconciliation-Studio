import hashlib
import io
import zipfile

import openpyxl
import polars as pl
import pytest
from studio.contracts import WorkspacePolicy
from studio.errors import DomainError
from studio.parsing import (
    ParseConfig,
    choose_parser,
    inspect_upload,
    parse_to_artifacts,
    verify_parse,
)


@pytest.mark.parametrize(
    "name,data,mime",
    [
        ("fake.xlsx", b"not a zip", "application/octet-stream"),
        ("empty.csv", b"", "text/csv"),
        ("../a.csv", b"id\n0001", "text/csv"),
        ("a.csv", b"PK\x03\x04", "text/csv"),
        ("a.exe", b"MZ", "application/octet-stream"),
        ("a.csv", b"id\x00value", "text/csv"),
    ],
)
def test_T01_invalid_files(name, data, mime, config):
    with pytest.raises(DomainError):
        inspect_upload(io.BytesIO(data), name, mime, config)


def test_T01_size_and_zip_xml_limits(config):
    config.max_upload_bytes = 2
    with pytest.raises(DomainError, match="FILE_TOO_LARGE"):
        inspect_upload(io.BytesIO(b"123"), "a.csv", "text/csv", config)
    config.max_upload_bytes = 20000
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("xl/workbook.xml", '<!DOCTYPE x [<!ENTITY evil "x">]><x>&evil;</x>')
    stream.seek(0)
    with pytest.raises(DomainError, match="INVALID_OFFICE_ARCHIVE"):
        inspect_upload(stream, "a.xlsx", "application/octet-stream", config)


def test_T02_hash_scoped_bytes_not_mutated(config):
    raw = b"id,amount\n000123,0\n"
    stream = io.BytesIO(raw)
    first = inspect_upload(stream, "a.csv", "text/csv", config)
    second = inspect_upload(stream, "a.csv", "text/csv", config)
    assert first.sha256 == second.sha256 == hashlib.sha256(raw).hexdigest()
    assert stream.read() == raw


def test_legitimate_PK_csv_header_is_not_zip_magic(config):
    raw = b"PK,amount\n000123,10\n"
    assert inspect_upload(io.BytesIO(raw), "a.csv", "text/csv", config).size == len(raw)


def test_T03_document_route_cloud_off(config):
    inspection = inspect_upload(
        io.BytesIO(b"%PDF-1.7 synthetic"), "a.pdf", "application/pdf", config
    )
    with pytest.raises(DomainError, match="CLOUD_PARSING_DISABLED"):
        choose_parser(inspection, WorkspacePolicy())


def test_T04_T05_T06_excel_cells_formulas_and_header(tmp_path, config):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Orders"
    sheet.append(["Synthetic report"])
    sheet.append(["Order ID", "Gross amount", "Formula"])
    sheet.append(["000123", 1234.5, "=B3*2"])
    sheet.append([123, None, None])
    sheet["A4"].number_format = "000000"
    sheet.append([None, None, None])
    sheet.append(["000125", -12, None])
    hidden = book.create_sheet("Hidden")
    hidden.append(["ID", "Note"])
    hidden.append(["000001", "synthetic"])
    hidden.sheet_state = "hidden"
    path = tmp_path / "report.xlsx"
    book.save(path)
    with path.open("rb") as stream:
        inspection = inspect_upload(stream, path.name, "application/octet-stream", config)
    tables = parse_to_artifacts(path, inspection, ParseConfig(), config)
    assert len(tables) == 2
    first = tables[0]
    assert first.header_row == 2
    assert first.frame["c1"].to_list() == ["000123", "000123", None, "000125"]
    assert first.frame["c2"].to_list() == ["1234.5", None, None, "-12"]
    assert first.frame["_source_row"].to_list() == [3, 4, 5, 6]
    assert "FORMULA_UNVERIFIED" in first.warnings
    assert first.cell_metadata[0] == {"cell": "C3", "formula": "B3*2", "cached": None}
    assert verify_parse(first, config) == "UNVERIFIED_EXTRACTION"
    assert "HIDDEN_SHEET_REVIEW" in tables[1].warnings


def test_xlsx_parser_accepts_inspected_opaque_raw_storage_key(tmp_path, config):
    book = openpyxl.Workbook()
    book.active.append(["ID", "Amount"])
    book.active.append(["000123", 12.5])
    path = tmp_path / "opaque-raw-id"
    book.save(path)
    with path.open("rb") as stream:
        inspection = inspect_upload(stream, "synthetic.xlsx", "application/octet-stream", config)
    parsed = parse_to_artifacts(path, inspection, ParseConfig(), config)[0]
    assert parsed.frame["c1"].to_list() == ["000123"]


def test_T05_csv_prefix_quoted_empty_bom_and_injection(tmp_path, config):
    raw = '\ufeffid,value\r\n000123,""\r\n000124,\r\n000125,=1+1\r\n'.encode("utf-8")
    path = tmp_path / "a.csv"
    path.write_bytes(raw)
    with path.open("rb") as stream:
        inspection = inspect_upload(stream, path.name, "text/csv", config)
    parsed = parse_to_artifacts(path, inspection, ParseConfig(), config)[0]
    assert parsed.frame["c1"].to_list() == ["000123", "000124", "000125"]
    assert parsed.frame["c2"].to_list() == ["", None, "=1+1"]
    assert path.read_bytes() == raw


def test_csv_blank_line_never_silently_lost(tmp_path, config):
    raw = b"id,value\n001,10\n\n002,20\n"
    path = tmp_path / "a.csv"
    path.write_bytes(raw)
    with path.open("rb") as stream:
        inspection = inspect_upload(stream, path.name, "text/csv", config)
    try:
        result = parse_to_artifacts(path, inspection, ParseConfig(), config)[0]
        assert result.frame.height == 3
    except DomainError as exc:
        assert exc.code == "CSV_ROW_COUNT_MISMATCH"


def test_csv_multiline_quoted_cell_keeps_physical_start_row(tmp_path, config):
    raw = b'id,note\n000123,"line one\nline two"\n000124,done\n'
    path = tmp_path / "multiline.csv"
    path.write_bytes(raw)
    inspection = inspect_upload(io.BytesIO(raw), path.name, "text/csv", config)
    parsed = parse_to_artifacts(path, inspection, ParseConfig(), config)[0]
    assert parsed.frame["_source_row"].to_list() == [2, 4]
    assert parsed.frame["c2"][0] == "line one\nline two"


def test_csv_rejects_post_header_limit_before_loading_frame(tmp_path, config, monkeypatch):
    path = tmp_path / "over-limit.csv"
    raw = b"id,value\n001,10\n002,20\n003,30\n"
    path.write_bytes(raw)
    limits = config.model_copy(update={"max_rows": 2})
    inspection = inspect_upload(io.BytesIO(raw), path.name, "text/csv", limits)

    def unexpected_read(*args, **kwargs):
        pytest.fail("CSV frame allocation must follow the row limit check")

    monkeypatch.setattr(pl, "read_csv", unexpected_read)
    with pytest.raises(DomainError, match="TABLE_LIMIT_EXCEEDED") as error:
        parse_to_artifacts(path, inspection, ParseConfig(), limits)
    assert error.value.code == "TABLE_LIMIT_EXCEEDED"


def test_xlsx_ignores_empty_formatted_sheet_before_valid_data(tmp_path, config):
    path = tmp_path / "formatted-empty.xlsx"
    book = openpyxl.Workbook()
    empty = book.active
    empty.title = "Mẫu trống"
    empty["B4"].number_format = "0.00"
    transactions = book.create_sheet("Giao dịch")
    transactions.append(["ID", "Số tiền"])
    transactions.append(["000123", "10.50"])
    book.save(path)

    with path.open("rb") as stream:
        inspection = inspect_upload(stream, path.name, "application/octet-stream", config)
    (parsed,) = parse_to_artifacts(path, inspection, ParseConfig(), config)

    assert parsed.sheet == "Giao dịch"
    assert parsed.frame.to_dicts() == [{"_source_row": 2, "c1": "000123", "c2": "10.50"}]


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_duplicate_header_preserves_columns_and_first_source_record(tmp_path, config, extension):
    """FND-PARSER: duplicate labels must never consume a data row as the header."""
    path = tmp_path / f"duplicate.{extension}"
    rows = [["ID", "amount", "amount"], ["000001", "10", "20"], ["000002", "30", "40"]]
    if extension == "xlsx":
        book = openpyxl.Workbook()
        for row in rows:
            book.active.append(row)
        book.save(path)
    else:
        path.write_text("\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")
    original = path.read_bytes()
    inspection = inspect_upload(io.BytesIO(original), path.name, "application/octet-stream", config)
    parsed = parse_to_artifacts(path, inspection, ParseConfig(), config)[0]
    assert parsed.header_row == 1
    assert [column.name for column in parsed.columns] == rows[0]
    assert parsed.frame["c1"].to_list() == ["000001", "000002"]
    assert parsed.frame["c2"].to_list() == ["10", "30"]
    assert parsed.frame["c3"].to_list() == ["20", "40"]
    assert parsed.frame["_source_row"].to_list() == [2, 3]
    assert "EMPTY_OR_DUPLICATE_HEADER" in parsed.warnings
    assert verify_parse(parsed, config) == "UNVERIFIED_EXTRACTION"
    assert path.read_bytes() == original


@pytest.mark.parametrize("header_row,valid", [(3, True), (2, False)])
def test_csv_explicit_header_uses_physical_record_start(tmp_path, config, header_row, valid):
    path = tmp_path / "multiline-preamble.csv"
    raw = b'"Report\ncaption"\nid,amount\n000001,10\n000002,20\n'
    path.write_bytes(raw)
    inspection = inspect_upload(io.BytesIO(raw), path.name, "text/csv", config)
    if not valid:
        with pytest.raises(DomainError, match="INVALID_HEADER_ROW"):
            parse_to_artifacts(path, inspection, ParseConfig(header_row=header_row), config)
        return
    parsed = parse_to_artifacts(path, inspection, ParseConfig(header_row=header_row), config)[0]
    assert parsed.header_row == 3
    assert [c.name for c in parsed.columns] == ["id", "amount"]
    assert parsed.frame["c1"].to_list() == ["000001", "000002"]
    assert parsed.frame["_source_row"].to_list() == [4, 5]
    assert path.read_bytes() == raw


def test_csv_rejects_row_overflow_during_read_instead_of_collecting_whole_file(
    tmp_path, config, monkeypatch
):
    import studio.parsing as parsing

    original_reader = parsing.csv.reader
    read = []

    class ObservedReader:
        def __init__(self, *args, **kwargs):
            self.reader = original_reader(*args, **kwargs)

        def __iter__(self):
            return self

        def __next__(self):
            record = next(self.reader)
            read.append(1)
            return record

        @property
        def line_num(self):
            return self.reader.line_num

    monkeypatch.setattr(parsing.csv, "reader", ObservedReader)
    config.max_rows = 2
    path = tmp_path / "overflow.csv"
    raw = b"id,value\n" + b"000001,10\n" * 100
    path.write_bytes(raw)
    inspection = inspect_upload(io.BytesIO(raw), path.name, "text/csv", config)
    with pytest.raises(DomainError, match="TABLE_LIMIT_EXCEEDED"):
        parse_to_artifacts(path, inspection, ParseConfig(delimiter=","), config)
    assert len(read) <= config.max_rows + 31


def test_T07_profile_exact_null_empty_duplicate(profile):
    amount = profile.columns[1]
    assert (profile.row_count, amount.null_count, amount.empty_count, amount.distinct_count) == (
        4,
        1,
        0,
        3,
    )
    assert profile.columns[0].identifier_candidate
    assert profile.key_candidates == [["c1"]]


def test_T08_alias_candidates(profile, schema):
    from studio.profiling import find_mapping_candidates

    candidates = find_mapping_candidates(profile, schema)
    assert candidates["c1"] == ["reference_id"]
    assert candidates["c2"] == []


@pytest.mark.parametrize(
    "header,target,kind,values",
    [
        ("MA_DON_HANG", "order_id", "string", ["0001", "0002"]),
        ("Mã khách hàng", "customer_id", "string", ["0001", "0002"]),
        ("Nhà cung cấp code", "supplier_id", "string", ["0001", "0002"]),
        ("Tiền trước phí", "gross_amount", "decimal", ["1.20", "-2.50"]),
        ("Giá trị sau khấu trừ", "net_amount", "decimal", ["1.20", "-2.50"]),
        ("Khoản đã thanh toán", "paid_amount", "decimal", ["1.20", "-2.50"]),
        ("Công nợ phải trả", "payable_amount", "decimal", ["1.20", "-2.50"]),
        ("Ngày chi trả", "payment_date", "date", ["2026-11-01", "2026-11-02"]),
        ("Mã loại tiền", "currency", "string", ["USD", "VND"]),
    ],
)
def test_multilingual_field_roles_preserve_unicode_forms_and_column_order(
    header, target, kind, values
):
    import unicodedata

    import polars as pl
    from studio.contracts import SchemaDefinition, SchemaField, SourceColumn
    from studio.profiling import find_mapping_candidates, profile_table

    destination = SchemaDefinition(
        id="semantic-target",
        workspace_id="workspace",
        name="Business specification",
        revision=1,
        entity_kind="unknown",
        grain="unknown",
        fields=[SchemaField(id=target, name=target, data_type=kind)],
    )
    for form in ("NFC", "NFD"):
        name = unicodedata.normalize(form, header)
        for columns in (["value", "note"], ["note", "value"]):
            frame = pl.DataFrame({"value": values, "note": ["a", "b"]}).select(columns)
            profile = profile_table(
                frame,
                [
                    SourceColumn(id=key, name=name if key == "value" else "Ghi chú", source_index=i)
                    for i, key in enumerate(columns)
                ],
                "table",
                "workspace",
                "parsed",
            )
            original = profile.model_dump_json()
            assert find_mapping_candidates(profile, destination)["value"] == [target]
            assert profile.model_dump_json() == original


@pytest.mark.parametrize(
    "header",
    [
        "Không phải tiền phí",
        "Giá trị gross hoặc net",
        "Ngày dự kiến chưa xác nhận",
        "Mã giao dịch hay khách hàng",
        "Tiền đã trả hay dự kiến",
        "Not gross amount",
    ],
)
def test_multilingual_proposals_abstain_on_negation_and_alternatives(header):
    import polars as pl
    from studio.contracts import SchemaDefinition, SchemaField, SourceColumn
    from studio.profiling import find_mapping_candidates, profile_table

    frame = pl.DataFrame({"value": ["10.20", "20.50"]})
    profile = profile_table(
        frame,
        [SourceColumn(id="value", name=header, source_index=0)],
        "table",
        "workspace",
        "parsed",
    )
    destination = SchemaDefinition(
        id="semantic-target",
        workspace_id="workspace",
        name="Ambiguous",
        revision=1,
        entity_kind="unknown",
        grain="unknown",
        fields=[
            SchemaField(id=name, name=name, data_type="decimal")
            for name in (
                "gross_amount",
                "net_amount",
                "fee_amount",
                "paid_amount",
                "expected_amount",
            )
        ],
    )
    assert find_mapping_candidates(profile, destination)["value"] == []


def test_profile_only_draft_recognizes_vietnamese_types_without_business_approval():
    import polars as pl
    from studio.agent_preparation import profiled_fields
    from studio.contracts import SourceColumn
    from studio.profiling import profile_table

    frame = pl.DataFrame(
        {
            "key": ["0001", "0002"],
            "money": ["12.50", "-2.00"],
            "revenue": ["2500", "3700"],
            "date": ["2026-11-01", "2026-11-02"],
        }
    )
    profile = profile_table(
        frame,
        [
            SourceColumn(id=key, name=name, source_index=index)
            for index, (key, name) in enumerate(
                zip(
                    frame.columns,
                    [
                        "Mã thanh toán",
                        "Phí ngân hàng",
                        "Doanh thu ghi nhận chưa VAT",
                        "Ngày thanh toán",
                    ],
                    strict=True,
                )
            )
        ],
        "table",
        "workspace",
        "parsed",
    )
    fields = profiled_fields(profile)
    assert [field.data_type for field in fields] == ["string", "decimal", "decimal", "date"]
    assert all(not field.business_key for field in fields)
    assert all(
        field.amount_basis is None and field.semantic_metric is None and field.timezone is None
        for field in fields
    )
    assert frame["key"].to_list() == ["0001", "0002"]


def test_mapping_shortlist_abstains_for_generic_roles_and_competing_columns(profile, schema):
    from studio.ai_gateway import manual_proposal
    from studio.profiling import find_mapping_candidates

    key = profile.columns[0]
    money = profile.columns[1]
    currency = key.model_copy(update={"column_id": "c7", "name": "Billing currency"})
    generic_date = money.model_copy(update={"column_id": "c8", "name": "Date"})
    second_key = key.model_copy(
        update={
            "column_id": "c9",
            "name": "Tracking ID",
            "evidence_ids": ["table:c9"],
        }
    )
    generic_reference = key.model_copy(update={"column_id": "c10", "name": "Reference"})
    new = profile.model_copy(
        update={"columns": [key, money, currency, generic_date, second_key, generic_reference]}
    )
    matches = find_mapping_candidates(new, schema)
    assert matches["c8"] == matches["c10"] == []
    proposal = manual_proposal(new, schema)
    both_keys = [d for d in proposal.decisions if d.source_field in {key.column_id, "c9"}]
    assert len(both_keys) == 2
    assert all(d.candidate_target is None and d.decision == "AMBIGUOUS" for d in both_keys)


def test_decimal_zero_and_paid_header_are_not_identifier_candidates():
    import polars as pl
    from studio.contracts import SourceColumn
    from studio.profiling import profile_table

    frame = pl.DataFrame({"c1": ["0.00", "100.50"]})
    result = profile_table(
        frame,
        [SourceColumn(id="c1", name="Paid amount", source_index=1)],
        "table",
        "workspace",
        "parsed",
    )
    assert not result.columns[0].identifier_candidate
