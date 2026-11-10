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


@pytest.mark.parametrize(
    "goal,expected",
    [
        ("Khóa ghép platform,order_id; chỉ đề xuất để tôi duyệt.", ["platform", "order_id"]),
        ("Không dùng khóa ghép platform,order_id", None),
        ("Khóa ghép platform hoặc order_id", None),
        ("Khóa ghép platform,foreign_field", None),
        ("Khóa ghép platform,platform", None),
        ("Khóa ghép platform. Khóa ghép order_id", None),
        ("Đối soát hai nguồn", None),
    ],
)
def test_literal_key_binding_preserves_order_without_inferring_missing_or_negated_keys(
    goal, expected
):
    from studio.reconciliation_planner import explicit_join_keys

    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    actual = explicit_join_keys(goal, cats)
    assert ([key.left for key in actual] if actual else None) == expected
    assert actual is None or all(key.left == key.right for key in actual)


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


@pytest.mark.parametrize(
    "kind", ["valid", "missing-scope", "invented-field", "changed-relation", "changed-keys"]
)
@pytest.mark.parametrize("relation", ["ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE"])
def test_local_planner_uses_approved_semantics_without_resending_raw_profiles(
    config, profile, kind, relation
):
    """MOCK transport; source reduction must retain every fact and validator gate."""
    from studio.ai_gateway import OllamaProvider

    config.local_demo_access = True
    config.ollama_url = "http://127.0.0.1:11434"
    p = plan()
    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    if relation != "ONE_TO_ONE":
        detail = cats[1 if relation == "ONE_TO_MANY" else 0]
        detail.canonical.grain = detail.schema_definition.grain = "order_line"
        p.cardinality, p.aggregation = relation, "SUM_SIGNED"
    cats[0].profile = profile.model_copy(
        deep=True,
        update={"source_table_id": cats[0].canonical.source_table_id, "workspace_id": "demo"},
    )
    cats[0].profile.columns[0].samples = ["RAW_PROFILE_MUST_NOT_BE_SENT"]
    request = PlanningRequest.from_plan(p)
    if kind == "changed-relation":
        request.intent = "Quan hệ: " + relation
    elif kind == "changed-keys":
        request.intent = "Khóa ghép " + ",".join(pair.left for pair in p.join_keys)
    if kind == "missing-scope":
        request.period_start = None
    suggestions = dict(
        left_role=p.left.role,
        right_role=p.right.role,
        **{
            key: value
            for key, value in p.model_dump(mode="json").items()
            if key
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
    if kind == "invented-field":
        suggestions["join_keys"][0]["left"] = "unavailable_key"
    elif kind == "changed-relation":
        suggestions["cardinality"] = "MANY_TO_ONE" if relation == "ONE_TO_MANY" else "ONE_TO_MANY"
    elif kind == "changed-keys":
        suggestions["join_keys"] = list(reversed(suggestions["join_keys"]))
    requests, reservations = [], []

    def handle(http_request):
        if http_request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3.8:27b", "size": 10, "digest": "a" * 64}]}
            )
        requests.append(http_request)
        body = json.loads(http_request.content)
        context = json.loads(body["messages"][1]["content"])
        assert context["user_confirmed"] == request.model_dump(mode="json", exclude_unset=True)
        assert "RAW_PROFILE_MUST_NOT_BE_SENT" not in json.dumps(body)
        assert "$defs" not in body["messages"][0]["content"]
        for compact, cat in zip(context["untrusted_catalogue"], cats, strict=True):
            assert compact["canonical_id"] == cat.canonical.id
            assert compact["business_key_fields"] == cat.schema_definition.business_key_fields
            assert compact["fields"] == [
                f.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
                for f in cat.schema_definition.fields
            ]
            assert (
                not {"profile", "approved_mapping", "canonical", "schema_definition"}
                & compact.keys()
            )
        assert body["format"]["properties"]["reasoning"]["maxLength"] == 240
        if kind == "changed-keys":
            for branch in body["format"]["$defs"]["PlanningSuggestions"]["anyOf"]:
                assert branch["properties"]["join_keys"]["const"] == [
                    pair.model_dump(mode="json") for pair in p.join_keys
                ]
        structures = body["format"]["$defs"]["PlanningSuggestions"]["anyOf"]
        tuples = {
            tuple(
                branch["properties"][key]["enum"][0]
                for key in ("cardinality", "aggregation", "comparison_grain")
            )
            for branch in structures
        }
        assert (relation, p.aggregation, p.comparison_grain) in tuples
        assert all(grain in {c.canonical.grain for c in cats} for _, _, grain in tuples)
        assert (len(tuples) == 1) == (relation == "ONE_TO_ONE" or kind == "changed-relation")
        import re

        from studio.reconciliation_planner import compatible_planning_metrics

        metric_variants = body["format"]["$defs"]["ComparisonMetric"]["anyOf"]
        for variant, metric in zip(metric_variants, compatible_planning_metrics(cats), strict=True):
            for key in (
                "metric_id",
                "left",
                "right",
                "currency",
                "unit",
                "amount_basis",
                "sign_convention",
            ):
                assert variant["properties"][key]["enum"] == [getattr(metric, key)]
            tolerance_wire = variant["properties"]["absolute_tolerance"]
            assert not re.fullmatch(tolerance_wire["pattern"], "")
            assert not re.fullmatch(tolerance_wire["pattern"], "-1")
            assert all(
                re.fullmatch(tolerance_wire["pattern"], value) for value in ("0", "0.01", "1E-18")
            )
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {
                    "content": json.dumps({"status": "PROPOSED", "suggestions": suggestions})
                },
            },
        )

    provider = OllamaProvider(
        config, "QWEN_27B", httpx.Client(transport=httpx.MockTransport(handle))
    )
    try:
        if kind in {"invented-field", "changed-relation", "changed-keys"}:
            with pytest.raises(DomainError):
                propose_plan(
                    provider,
                    cats,
                    request,
                    WorkspacePolicy(),
                    lambda: reservations.append(True) or True,
                    "demo",
                    "project",
                )
        else:
            result = propose_plan(
                provider,
                cats,
                request,
                WorkspacePolicy(),
                lambda: reservations.append(True) or True,
                "demo",
                "project",
            )
            if kind == "missing-scope":
                assert result.status == "NEEDS_REVIEW" and result.plan is None
                assert "period_start" in result.missing_requirements
            else:
                assert result.status == "PROPOSED"
                assert result.plan.left == p.left and result.plan.right == p.right
                assert (
                    result.plan.join_keys == p.join_keys
                    and result.plan.comparison_metrics == p.comparison_metrics
                )
        assert len(requests) == len(reservations) == provider.usage["ai_calls"] == 1
        assert provider.usage["cloud_requests"] == 0
    finally:
        provider.close()


@pytest.mark.parametrize(
    "goal,expected",
    [
        ("Quan hệ MANY_TO_ONE; chỉ đề xuất để tôi duyệt.", "MANY_TO_ONE"),
        ("Cardinality = ONE_TO_MANY", "ONE_TO_MANY"),
        ("Không dùng quan hệ MANY_TO_ONE", None),
        ("Chưa xác nhận quan hệ ONE_TO_ONE", None),
        ("Quan hệ ONE_TO_MANY hoặc MANY_TO_ONE", None),
        ("Đối soát hai nguồn", None),
    ],
)
def test_cardinality_literal_cannot_infer_negated_or_ambiguous_relation(goal, expected):
    from studio.reconciliation_planner import explicit_cardinality

    assert explicit_cardinality(goal) == expected


@pytest.mark.parametrize("mismatch", ["amount_basis", "semantic_metric", "currency", "unit"])
def test_planner_incompatible_approved_money_requests_review_without_inference(mismatch):
    cats = [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]
    money = next(f for f in cats[1].schema_definition.fields if f.data_type == "decimal")
    setattr(
        money,
        mismatch,
        {"amount_basis": "net", "semantic_metric": "net_receipt", "currency": "USD", "unit": "USD"}[
            mismatch
        ],
    )

    class ForbiddenProvider:
        local = True
        usage = {}

        def request_typed(self, *args, **kwargs):
            pytest.fail("Incompatible approved money does not need model inference")

    def forbidden_reserve():
        pytest.fail("No inference request or budget reservation expected")

    result = propose_plan(
        ForbiddenProvider(),
        cats,
        PlanningRequest.from_plan(plan()),
        WorkspacePolicy(),
        forbidden_reserve,
        "demo",
        "project",
    )
    assert result.status == "NEEDS_REVIEW" and result.plan is None and result.missing_requirements


def test_candidate_cannot_expand_requested_gross_scope_to_all_compatible_money_fields():
    from studio.contracts import SchemaField
    from studio.reconciliation_planner import scoped_key_candidates

    left, right = records("internal-sales.csv")[:3], records("shopee-orders.csv")[:3]
    cats = [catalogue("internal", left), catalogue("shopee", right)]
    request = PlanningRequest.from_plan(plan())
    assert scoped_key_candidates(request, cats, left, right).status == "PROPOSED"
    for cat, rows in zip(cats, (left, right), strict=True):
        cat.schema_definition.fields.append(
            SchemaField(
                id="net_receipt",
                name="Net receipt",
                data_type="decimal",
                semantic_metric="net_receipt",
                amount_basis="net",
                currency="VND",
                unit="VND",
            )
        )
        for row in rows:
            row.payload["net_receipt"] = row.payload["gross_amount"]
    request.intent = "Chỉ đối soát item_gross trước phí; không thêm net_receipt."
    # The bounded row probe proves linkage, not a choice of monetary scope.
    # Leave metric selection with the typed planner/review rather than proposing
    # every compatible amount just because the schema exposes it.
    assert scoped_key_candidates(request, cats, left, right) is None


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
