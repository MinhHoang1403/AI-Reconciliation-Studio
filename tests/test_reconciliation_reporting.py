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
from studio.contracts.reconciliation import PlanningRequest
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
    # Classification includes verified missing counterparts; successful reconciliation does not.
    assert snapshot.automation_coverage.numerator == 4
    assert snapshot.automation_coverage.denominator == 5
    assert snapshot.full_match_rate.numerator == 2


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
        wire = json.loads(request.content)["generationConfig"]["responseJsonSchema"]
        assert (
            "Only canonical/schema/artifact"
            in wire["$defs"]["PlanningSuggestions"]["properties"]["evidence_ids"]["description"]
        )
        allowed = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])[
            "allowed_rule_evidence_ids"
        ]
        assert set(allowed) == {
            ident
            for cat in cats
            for ident in (cat.canonical.id, cat.canonical.artifact.id, cat.canonical.schema_id)
        }
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
        expected = 0 if kind == "off" else 1
        assert len(requests) == len(reserved) == expected
    provider.close()


def test_scoped_candidate_ignores_outside_duplicates_but_abstains_on_inside_conflicts():
    from datetime import UTC, datetime

    from studio.contracts.reconciliation import PlanningRequest
    from studio.reconciliation_planner import scoped_key_candidate

    left_rows = records("shipments.csv")
    right_rows = records("delivery-confirmations.csv")
    cats = [
        catalogue(
            source, rows, grain="shipment", metric="delivery_charge", amount="delivery_charge"
        )
        for source, rows in (("left", left_rows), ("right", right_rows))
    ]
    draft = PlanningRequest.from_plan(
        plan(
            left="left",
            right="right",
            entity="delivery",
            platform="",
            amount="delivery_charge",
            metric="delivery_charge",
            keys=["tracking_id"],
        )
    )
    prior = left_rows[0].model_copy(deep=True)
    prior.payload["event_date"] = datetime(2026, 9, 30, tzinfo=UTC)
    candidate = scoped_key_candidate(draft, cats, [*left_rows, prior], right_rows)
    assert candidate is not None and candidate.status == "PROPOSED"
    assert candidate.plan.cardinality == "ONE_TO_ONE"
    assert [(key.left, key.right) for key in candidate.plan.join_keys] == [
        ("tracking_id", "tracking_id")
    ]
    assert scoped_key_candidate(draft, cats, [*left_rows, left_rows[0]], right_rows) is None
    draft.period_start = None
    assert scoped_key_candidate(draft, cats, left_rows, right_rows) is None


def test_planner_retains_equal_keys_without_picking_a_plan():
    from studio.contracts import SchemaField
    from studio.contracts.reconciliation import PlanningRequest
    from studio.reconciliation_planner import scoped_key_candidates

    left_rows = records("shipments.csv")
    right_rows = records("delivery-confirmations.csv")
    cats = [
        catalogue(side, rows, grain="shipment", metric="delivery_charge", amount="delivery_charge")
        for side, rows in (("left", left_rows), ("right", right_rows))
    ]
    for cat, rows in zip(cats, (left_rows, right_rows), strict=True):
        cat.schema_definition.fields.append(
            SchemaField(id="manifest_reference", name="Manifest reference", data_type="string")
        )
        cat.identifier_fields.append("manifest_reference")
        for record in rows:
            record.payload["manifest_reference"] = "M-" + record.payload["tracking_id"]
    request = PlanningRequest.from_plan(
        plan(
            left="left",
            right="right",
            entity="delivery",
            platform="",
            amount="delivery_charge",
            metric="delivery_charge",
            keys=["tracking_id"],
        )
    )
    result = scoped_key_candidates(request, cats, left_rows, right_rows)
    assert result and result.status == "NEEDS_REVIEW" and result.plan is None
    assert len(result.candidates) == 2 and len({c.id for c in result.candidates}) == 2
    assert {
        (c.plan.join_keys[0].left, c.plan.join_keys[0].right, c.overlap) for c in result.candidates
    } == {("tracking_id", "tracking_id", 2), ("manifest_reference", "manifest_reference", 2)}
    assert scoped_key_candidates(request, cats, list(reversed(left_rows)), right_rows) == result


@pytest.mark.parametrize("reverse", [False, True])
def test_scoped_planner_matches_composite_anchor_to_detail_with_different_key(reverse):
    from studio.contracts.reconciliation import PlanningRequest
    from studio.reconciliation_planner import scoped_key_candidate

    orders = records("internal-sales.csv")
    lines = records("tiktok-order-lines.csv")
    anchor = catalogue("anchor", orders)
    detail = catalogue("detail", lines, grain="order_line")
    anchor.schema_definition.business_key_fields = ["shop_id", "order_id"]
    detail.schema_definition.business_key_fields = []
    detail.identifier_fields = ["order_id"]
    ids = [anchor, detail]
    rows = [orders, lines]
    if reverse:
        ids.reverse()
        rows.reverse()
    draft = PlanningRequest.from_plan(
        plan(
            left=ids[0].canonical.id,
            right=ids[1].canonical.id,
            platform="",
        )
    )
    draft.left.filters = {"shop_id": "SHOP-B"}
    draft.right.filters = {"shop_id": "SHOP-B"}
    proposal = scoped_key_candidate(draft, ids, *rows)
    assert proposal is not None and proposal.plan is not None
    assert proposal.plan.cardinality == ("MANY_TO_ONE" if reverse else "ONE_TO_MANY")
    assert proposal.plan.comparison_grain == "order"
    assert proposal.plan.aggregation == "SUM_SIGNED"
    assert [(key.left, key.right) for key in proposal.plan.join_keys] == [
        ("order_id", "order_id"),
        ("shop_id", "shop_id"),
    ]


@pytest.mark.parametrize(
    "case,left_keys,right_keys,grains,expected",
    [
        (
            "shipment",
            ["0001", "0002"],
            ["0002", "0003"],
            ("dispatch", "dispatch"),
            ("ONE_TO_ONE", 1),
        ),
        (
            "invoice-lines",
            ["0001", "0002"],
            ["0001", "0001", "0002"],
            ("invoice", "line"),
            ("ONE_TO_MANY", 2),
        ),
        (
            "settlement",
            ["0001", "0002", "0002"],
            ["0001", "0002"],
            ("entry", "batch"),
            ("MANY_TO_ONE", 2),
        ),
        ("disjoint", ["0001"], ["1"], ("dispatch", "dispatch"), None),
        ("duplicate", ["0001", "0001"], ["0001"], ("dispatch", "dispatch"), None),
        ("many-both", ["0001", "0001"], ["0001", "0001"], ("invoice", "line"), None),
        ("mixed-amount-basis", ["0001"], ["0001"], ("dispatch", "dispatch"), None),
        ("mixed-currency", ["0001"], ["0001"], ("dispatch", "dispatch"), None),
        ("unknown-grain", ["0001"], ["0001"], ("unknown", "dispatch"), None),
        ("missing-coverage", ["0001"], ["0001"], ("dispatch", "dispatch"), None),
    ],
)
def test_planner_independent_business_cases(case, left_keys, right_keys, grains, expected):
    from datetime import UTC, datetime

    from studio.contracts.reconciliation import CanonicalRecord
    from studio.reconciliation_planner import scoped_key_candidates

    def rows(side, key_field, keys):
        return [
            CanonicalRecord(
                id=f"{side}-{index}",
                payload={
                    key_field: value,
                    "event_date": datetime(2026, 10, 15, tzinfo=UTC),
                    "currency": "VND",
                    "gross_amount": Decimal("7.75"),
                },
                invalid=False,
                quality_flags=[],
                provenance=[
                    dict(
                        file_id=side,
                        source_table_id=side,
                        source_row_id=f"{side}-{index}",
                        sheet="CSV",
                        row=index + 2,
                    )
                ],
            )
            for index, value in enumerate(keys)
        ]

    left_rows, right_rows = (
        rows("left", "dispatch_ref", left_keys),
        rows("right", "control_code", right_keys),
    )
    left = catalogue("left", left_rows, grain=grains[0], metric="billed_value")
    right = catalogue("right", right_rows, grain=grains[1], metric="billed_value")
    left.identifier_fields = ["dispatch_ref"]
    right.identifier_fields = ["control_code"]
    request = PlanningRequest.from_plan(
        plan(left="left", right="right", platform="", entity="delivery", metric="billed_value")
    )
    if case == "mixed-amount-basis":
        next(
            f for f in right.schema_definition.fields if f.id == "gross_amount"
        ).amount_basis = "net"
    elif case == "mixed-currency":
        next(f for f in right.schema_definition.fields if f.id == "gross_amount").currency = "USD"
    elif case == "missing-coverage":
        request.right.coverage_end = None
    result = scoped_key_candidates(request, [left, right], left_rows, right_rows)
    if expected is None:
        assert result is None
    else:
        assert result and result.plan and len(result.candidates) == 1
        assert (result.plan.cardinality, result.candidates[0].overlap) == expected
        assert [(pair.left, pair.right) for pair in result.plan.join_keys] == [
            ("dispatch_ref", "control_code")
        ]
        assert result.plan.comparison_metrics[0].metric_id == "billed_value"


@pytest.mark.parametrize(
    "kind",
    [
        "different-ids",
        "invented",
        "changed-scope",
        "missing",
        "budget",
        "suggestions",
        "suggested-fake-field",
        "fake-evidence",
        "unconfirmed-scope",
        "suggested-bad-money",
        "suggested-cardinality",
        "changed-period",
        "structured-complete",
        "structured-sparse-complete",
        "structured-null-complete",
        "structured-partial",
    ],
)
def test_planner_partial_request_proposes_keys_without_execution(config, kind):
    p = plan()
    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    # Same meaning, different canonical IDs; no join keys exist in the input contract.
    for field in cats[1].schema_definition.fields:
        if field.id == "order_id":
            field.id, field.name = "external_reference", "Marketplace reference"
    p.join_keys = [
        pair.model_copy(update={"right": "external_reference"})
        if pair.right == "order_id"
        else pair
        for pair in p.join_keys
    ]
    draft = PlanningRequest.from_plan(p)
    if kind == "structured-sparse-complete":
        sparse = draft.model_dump(mode="json", exclude_unset=True)
        sparse.pop("allow_partial", None)
        sparse["right"].pop("filters", None)
        draft = PlanningRequest.model_validate(sparse)
    if kind == "structured-null-complete":
        sparse = draft.model_dump(mode="json")
        sparse["left"]["filters"] = sparse["right"]["filters"] = None
        sparse["allow_partial"] = None
        draft = PlanningRequest.model_validate(sparse)
    if kind in {
        "missing",
        "suggestions",
        "suggested-fake-field",
        "fake-evidence",
        "unconfirmed-scope",
        "structured-partial",
    }:
        draft = PlanningRequest(left={"canonical_id": "internal"}, right={"canonical_id": "shopee"})
    config.allow_external_ai = True
    config.external_ai_request_budget = 10
    config.gemini_api_key = SecretStr("synthetic-not-a-real-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=10
    )
    requests = []

    def handle(request):
        requests.append(request)
        body = dict(status="PROPOSED", plan=p.model_dump(mode="json"))
        if kind == "invented":
            body["plan"]["join_keys"][0]["right"] = "imaginary"
        if kind == "changed-scope":
            body["plan"]["left"]["filters"] = {}
        if kind == "changed-period":
            body["plan"]["period_end"] = "2026-10-30"
        if kind == "missing":
            body = dict(
                status="NEEDS_REVIEW",
                plan=None,
                missing_requirements=["Confirm reporting period"],
                reasoning="Missing coverage",
            )
        if kind in {
            "suggestions",
            "structured-complete",
            "structured-sparse-complete",
            "structured-null-complete",
            "structured-partial",
            "suggested-fake-field",
            "fake-evidence",
            "suggested-bad-money",
            "suggested-cardinality",
        }:
            suggestion = dict(
                left_role="reference",
                right_role="counterpart",
                **{
                    k: v
                    for k, v in p.model_dump(mode="json").items()
                    if k
                    in {
                        "join_keys",
                        "comparison_metrics",
                        "comparison_grain",
                        "cardinality",
                        "aggregation",
                        "evidence_ids",
                    }
                },
            )
            if kind == "suggested-fake-field":
                suggestion["join_keys"][0]["left"] = "invented"
            if kind == "fake-evidence":
                suggestion["evidence_ids"] = ["invented-evidence"]
            if kind == "suggested-bad-money":
                suggestion["comparison_metrics"][0]["amount_basis"] = "net"
            if kind == "suggested-cardinality":
                suggestion["cardinality"] = "MANY_TO_MANY"
            body = dict(
                status="PROPOSED" if kind.startswith("structured-") else "NEEDS_REVIEW",
                plan=None,
                suggestions=suggestion,
                missing_requirements=["Confirm reporting period"],
            )
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}
        )

    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(handle)))
    if kind in {
        "invented",
        "changed-scope",
        "budget",
        "suggested-fake-field",
        "fake-evidence",
        "suggested-bad-money",
        "suggested-cardinality",
        "changed-period",
    }:
        with pytest.raises(DomainError):
            propose_plan(provider, cats, draft, policy, lambda: kind != "budget", "demo", "project")
    else:
        result = propose_plan(provider, cats, draft, policy, lambda: True, "demo", "project")
        if kind == "missing":
            assert result.status == "NEEDS_REVIEW" and result.plan is None
        elif kind in {"suggestions", "unconfirmed-scope", "structured-partial"}:
            assert result.status == "NEEDS_REVIEW" and result.plan is None
            assert result.suggestions.join_keys == p.join_keys
            assert result.missing_requirements
        else:
            assert result.status == "PROPOSED" and result.plan.join_keys == p.join_keys
    assert len(requests) == (0 if kind == "budget" else 1)
    provider.close()


@pytest.mark.parametrize("kind", ["stale", "workspace", "profile", "artifact"])
def test_planner_context_gate_rejects_bad_refs_before_cloud(config, kind):
    from studio.contracts import DatasetProfile

    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    if kind == "stale":
        cats[0].canonical.stale = True
    elif kind == "workspace":
        cats[0].schema_definition.workspace_id = "foreign"
    elif kind == "profile":
        cats[0].profile = DatasetProfile(
            source_table_id="foreign",
            workspace_id="demo",
            artifact_id="parsed",
            row_count=0,
            columns=[],
            key_candidates=[],
        )
    else:
        cats[0].canonical.artifact.workspace_id = "foreign"
    calls = []
    provider = GeminiProvider(
        config, httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request)))
    )
    with pytest.raises(DomainError):
        propose_plan(
            provider,
            cats,
            PlanningRequest(left={"canonical_id": "internal"}, right={"canonical_id": "shopee"}),
            WorkspacePolicy(),
            lambda: pytest.fail("Must validate context before reservation"),
            "demo",
            "project",
        )
    assert calls == []
    provider.close()
