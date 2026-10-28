from decimal import Decimal

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
