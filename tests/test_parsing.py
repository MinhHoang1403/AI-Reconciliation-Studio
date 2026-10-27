import hashlib
import io
import zipfile

import openpyxl
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
