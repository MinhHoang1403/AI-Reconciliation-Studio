"""Assistant dùng đúng UUID-schema harness; mọi dữ liệu ở đây là tổng hợp."""

import pytest
from studio.access import Actor
from studio.assistant_tools import build_fact_set, read_tool
from studio.contracts.assistant import AssistantContext, ToolRequest
from studio.errors import DomainError
from test_postgres import drain, pg, project  # noqa: F401
from test_reconciliation_postgres import create_approved_run

pytestmark = pytest.mark.integration


def test_T38_tools_reject_other_project_run_and_dataset(pg):  # noqa: F811
    client, factory, _ = pg
    pid = project(client)
    other = project(client)
    with factory() as db:
        actor = Actor("test-owner", "demo", "owner")
        result = read_tool(
            db, actor, ToolRequest(name="list_datasets", context=AssistantContext(project_id=pid))
        )
        assert result.datasets == []
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            read_tool(
                db,
                Actor("x", "foreign", "owner"),
                ToolRequest(name="list_datasets", context=AssistantContext(project_id=other)),
            )


def test_T39_T40_verified_facts_independent_delivery_oracle(pg):  # noqa: F811
    client, factory, worker = pg
    pid, _, rule, queued = create_approved_run(pg)
    drain(factory, worker)
    run_id = queued["run_id"]
    matches = client.get(f"/api/runs/{run_id}/matches?limit=100").json()["items"]
    mismatch = next(g for g in matches if g["key"][-1] == "000702")
    assert mismatch["comparison_state"] == "AMOUNT_MISMATCH"
    context = AssistantContext(project_id=pid, run_id=run_id, group_id=mismatch["id"])
    with factory() as db:
        actor = Actor("test-owner", "demo", "owner")
        facts = build_fact_set(db, actor, context)
        assert facts.rule_id == rule["id"]
        assert facts.snapshot.run_id == run_id
        money = next(f for f in facts.facts if f.id == "comparison_0")
        # Oracle đọc trực tiếp hai CSV fixture: trái 12.75, phải 10.00 => +2.75 VND.
        assert money.value == "12.75 / 10.00 / 2.75 / 0 VND"
        assert money.currency == "VND" and money.metric_id == "delivery_charge"
        assert all(r.run_id == run_id for r in facts.references)
        assert len({r.member_id for r in facts.references if r.member_id}) == 2
        assert facts.id == build_fact_set(db, actor, context).id
        with pytest.raises(DomainError, match="INSUFFICIENT_EVIDENCE"):
            read_tool(
                db,
                actor,
                ToolRequest(name="get_metric_breakdown", context=context, metric_id="EBITDA"),
            )
        other = project(client)
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            build_fact_set(db, actor, context.model_copy(update={"project_id": other}))
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            build_fact_set(db, actor, context.model_copy(update={"group_id": "nonexistent"}))


def test_workflow_tools_no_financial_readiness_invention(pg):  # noqa: F811
    client, factory, _ = pg
    pid = project(client)
    with factory() as db:
        context = AssistantContext(project_id=pid)
        actor = Actor("test-owner", "demo", "viewer")
        result = read_tool(db, actor, ToolRequest(name="get_workflow_status", context=context))
        assert result.workflow.ready_canonical_count == 0
        assert result.workflow.approved_rule_ids == []
        assert result.workflow.questions
        facts = build_fact_set(db, actor, context)
        assert facts.verification_status == "INSUFFICIENT_EVIDENCE" and not facts.facts
