import csv
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from zipfile import ZipFile

import httpx
import pytest
from openpyxl import load_workbook
from pydantic import SecretStr
from reconciliation_cases import catalogue, plan, records
from studio.ai_gateway import GeminiProvider
from studio.contracts import WorkspacePolicy
from studio.errors import DomainError
from studio.reconciliation_engine import match_records
from studio.reconciliation_exports import NS, write_csv, write_xlsx
from studio.reconciliation_planner import propose_plan
from studio.verification import calculate_metric_snapshot


def test_T34_zero_denominator_and_snapshot_oracle():
    p = plan()
    empty = match_records(p, [], [])
    snapshot = calculate_metric_snapshot("run", "rule", 1, p, [], [], empty)
    assert snapshot.full_match_rate.percent is None
    left, right = records("internal-sales.csv"), records("shopee-orders.csv")
    snapshot = calculate_metric_snapshot(
        "run", "rule", 1, p, left, right, match_records(p, left, right)
    )
    assert snapshot.eligible_units == 5
    assert snapshot.full_match_rate.numerator == 2 and snapshot.full_match_rate.percent == "40.00"
    assert snapshot.monetary[0].absolute_variance == Decimal("10.00")
    assert snapshot.review_rate.numerator == 1


def test_export_injection_numeric_negatives_precision_and_prefix(tmp_path):
    sections = {
        "Summary": [
            ["Field", "Value"],
            ["ID", "000123"],
            ["Negative", Decimal("-12.75")],
            ["Precise", Decimal("123456789012345678.123456789012345678")],
            *[["Untrusted", value] for value in ("=SUM(1+1)", "+CMD", "-CMD", "@CMD", " \t=1")],
        ]
    }
    xlsx, csv_path = tmp_path / "report.xlsx", tmp_path / "report.csv"
    write_xlsx(xlsx, sections)
    write_csv(csv_path, sections)
    book = load_workbook(xlsx, data_only=False)
    assert book["Summary"]["B2"].value == "000123"
    assert book["Summary"]["B3"].data_type == "n" and book["Summary"]["B3"].value == -12.75
    assert all(c.data_type != "f" for sheet in book for row in sheet for c in row)
    with ZipFile(xlsx) as archive:
        tree = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        cell = next(c for c in tree.findall(f".//{{{NS}}}c") if c.attrib["r"] == "B4")
        assert Decimal(cell.find(f"{{{NS}}}v").text) == sections["Summary"][3][1]
    rows = list(csv.reader(csv_path.open(encoding="utf-8-sig", newline="")))
    assert next(r[2] for r in rows if r[1] == "Negative") == "-12.75"
    assert all(r[2].startswith("'") for r in rows if r[1] == "Untrusted")


def test_xlsx_rejects_unrepresentable_text_without_silent_truncation(tmp_path):
    for value in ("x" * 32768, "untrusted\x00value"):
        with pytest.raises(DomainError, match="EXPORT_CELL_LIMIT"):
            write_xlsx(
                tmp_path / "unpublished.xlsx", {"Summary": [["Field", "Value"], ["Text", value]]}
            )


@pytest.mark.parametrize("kind", ["valid", "invented", "approved", "invalid-json", "off"])
def test_planner_typed_contract_bounded_attempts_and_policy(config, kind):
    p = plan()
    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    config.allow_external_ai = True
    config.external_ai_request_budget = 10
    config.gemini_api_key = SecretStr("synthetic-not-a-real-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=kind != "off", external_request_budget=10
    )
    requests = []
    reserved = []

    def handle(request):
        requests.append(request)
        body = dict(status="PROPOSED", plan=p.model_dump(mode="json"))
        if kind == "invented":
            body["plan"]["join_keys"][0]["left"] = "invented"
        if kind == "approved":
            body["status"] = "APPROVED"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "invalid" if kind == "invalid-json" else json.dumps(body)}
                            ]
                        }
                    }
                ]
            },
        )

    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(handle)))

    def reserve():
        reserved.append(1)
        return True

    if kind == "valid":
        result = propose_plan(provider, cats, p, policy, reserve, "demo", "project")
        assert result.status == "PROPOSED" and len(requests) == len(reserved) == 1
    else:
        with pytest.raises(DomainError):
            propose_plan(provider, cats, p, policy, reserve, "demo", "project")
        expected = 0 if kind == "off" else 1 if kind == "invented" else 2
        assert len(requests) == len(reserved) == expected
    provider.close()
