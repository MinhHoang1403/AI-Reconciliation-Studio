import runpy
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from reconciliation_cases import catalogue, plan, records
from studio.contracts.reconciliation import ComparisonMetric, PlanProposal
from studio.errors import DomainError
from studio.reconciliation_contracts import validate_reconciliation_contract


def sources():
    return [
        catalogue("internal", records("internal-sales.csv")),
        catalogue("shopee", records("shopee-orders.csv")),
    ]


def test_acceptance_cli_planner_payload_matches_current_api_and_preserves_confirmed_scope():
    from studio.reconciliation_api import AIPlanInput
    from studio.reconciliation_planner import validate_planning_request

    candidate = Path(__file__).resolve().parents[1] / "tools/check-reconciliation.py"
    if not candidate.is_file():
        candidate = Path(__file__).with_name("check-reconciliation.py")
    helper = runpy.run_path(str(candidate))
    confirmed = plan()
    body = helper["planner_input"]("project", confirmed.model_dump(mode="json"))
    parsed = AIPlanInput.model_validate(body)
    validate_planning_request(parsed.request, sources(), "demo", "project")
    assert parsed.project_id == "project"
    assert parsed.request.left.canonical_id == confirmed.left.canonical_id
    assert parsed.request.right.canonical_id == confirmed.right.canonical_id
    assert parsed.request.left.coverage_start == confirmed.left.coverage_start
    assert parsed.request.right.coverage_end == confirmed.right.coverage_end
    assert parsed.request.period_start == confirmed.period_start
    assert parsed.request.period_end == confirmed.period_end
    assert parsed.request.timezone == confirmed.timezone
    assert "join_keys" not in body["request"]
    assert "comparison_metrics" not in body["request"]


def test_T17_nonexistent_key_or_evidence_rejected():
    p = plan()
    p.join_keys[0].left = "invented"
    with pytest.raises(DomainError, match="FIELD_NOT_FOUND"):
        validate_reconciliation_contract(p, sources(), "demo", "project")
    p = plan().model_copy(update={"evidence_ids": ["invented"]})
    with pytest.raises(DomainError):
        validate_reconciliation_contract(p, sources(), "demo", "project")


def test_T18_gross_net_and_stale_scope_blocked():
    for mutation in ("basis", "stale", "scope"):
        cats = sources()
        if mutation == "basis":
            next(
                f for f in cats[1].schema_definition.fields if f.id == "gross_amount"
            ).amount_basis = "net"
        elif mutation == "stale":
            cats[1].canonical.stale = True
        else:
            cats[1].project_id = "other-project"
        with pytest.raises(DomainError):
            validate_reconciliation_contract(plan(), cats, "demo", "project")


def test_T19_incomplete_coverage_needs_explicit_partial():
    p = plan()
    p.right.completeness = "INCOMPLETE"
    with pytest.raises(DomainError):
        validate_reconciliation_contract(p, sources(), "demo", "project")
    p.allow_partial = True
    assert validate_reconciliation_contract(p, sources(), "demo", "project") == p


def test_rule_precision_period_currency_and_rigid_fuzzy_constraints():
    p = plan()
    raw = p.comparison_metrics[0].model_dump()
    raw["absolute_tolerance"] = 0.1
    with pytest.raises(ValidationError):
        ComparisonMetric.model_validate(raw)
    p.comparison_metrics[0].absolute_tolerance = Decimal("0.01")
    assert validate_reconciliation_contract(p, sources(), "demo", "project")
    for update in (
        {"timezone": "invented"},
        {"effective_from": "2026-10-02"},
        {"aggregation": "SUM_SIGNED"},
        {"cardinality": "ONE_TO_MANY", "aggregation": "SUM_SIGNED"},
        {"fuzzy_fields": [dict(left="order_id", right="order_id")]},
    ):
        bad = type(p).model_validate(p.model_dump() | update)
        with pytest.raises(DomainError):
            validate_reconciliation_contract(bad, sources(), "demo", "project")


def test_AI_cannot_approve_reconciliation_rule():
    with pytest.raises(ValidationError):
        PlanProposal.model_validate(dict(status="APPROVED", plan=plan().model_dump()))


def test_domain_templates_never_invent_settlement_or_currency():
    from studio.domain_templates import domain_templates

    templates = domain_templates("demo", {"order", "order_line"})
    assert {t.entity_kind for t in templates} == {"order", "order_line", "financial_event"}
    assert all(
        next(f for f in t.fields if f.id == "amount").currency == "UNKNOWN" for t in templates
    )
    assert "settlement" in {t.entity_kind for t in domain_templates("demo", {"settlement"})}
