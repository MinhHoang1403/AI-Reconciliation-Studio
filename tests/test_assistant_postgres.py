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


def conversation(client, context, key="conversation"):
    response = client.post(
        "/api/conversations", json=dict(context=context), headers={"Idempotency-Key": key}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def ask(client, conversation_id, context, question="Vì sao lệch?", key="question"):
    return client.post(
        "/api/assistant/messages",
        json=dict(conversation_id=conversation_id, context=context, text=question),
        headers={"Idempotency-Key": key},
    )


def test_conversation_queue_idempotency_cursor_cache_and_scope(pg):  # noqa: F811
    from sqlalchemy import func, select
    from studio.database import MessageRow

    client, factory, worker = pg
    pid, _, _, queued = create_approved_run(pg)
    drain(factory, worker)
    run_id = queued["run_id"]
    groups = client.get(f"/api/runs/{run_id}/matches?limit=100").json()["items"]
    group = next(g for g in groups if g["key"][-1] == "000702")
    context = dict(project_id=pid, run_id=run_id, group_id=group["id"])
    cid = conversation(client, context)
    assert conversation(client, context) == cid
    one = ask(client, cid, context)
    assert one.status_code == 202, one.text
    assert ask(client, cid, context).json() == one.json()
    assert ask(client, cid, context, question="Đổi nội dung", key="question").status_code == 409
    assert ask(client, cid, context, key="concurrent").status_code == 409
    drain(factory, worker)
    messages = client.get(f"/api/conversations/{cid}").json()["items"]
    assert len(messages) == 2 and messages[-1]["answer"]["status"] == "ANSWERED"
    answer = messages[-1]["answer"]
    assert answer["request_count"] == 0
    assert answer["fact_set"]["context"]["run_id"] == run_id
    assert any("12.75 / 10.00 / 2.75 / 0 VND" in line["text"] for line in answer["lines"])
    last = client.get(f"/api/conversations/{cid}?limit=1").json()
    assert last["has_more"] is True and last["items"][0]["role"] == "assistant"
    previous = client.get(
        f"/api/conversations/{cid}", params=dict(limit=1, before_id=last["items"][0]["id"])
    ).json()
    assert previous["items"][0]["role"] == "user"
    assert ask(client, cid, context, key="repeat").status_code == 202
    drain(factory, worker)
    assert client.get(f"/api/conversations/{cid}").json()["items"][-1]["answer"]["mode"] == "CACHE"
    other = project(client)
    assert conversation(client, dict(project_id=other), key="other") != cid
    assert (
        client.get("/api/conversations", params=dict(project_id=other, before_id=cid)).status_code
        == 404
    )
    assert ask(client, cid, dict(project_id=other), key="wrong-scope").status_code == 409
    assert (
        client.post(
            "/api/assistant/tools",
            json=dict(name="get_run_summary", context=dict(project_id=other, run_id=run_id)),
        ).status_code
        == 404
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MessageRow)) == 4


def test_conversation_owner_privacy_csrf_and_delete_pending_no_resurrection(pg, monkeypatch):  # noqa: F811
    from studio.database import MessageRow

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    one = ask(client, cid, context)
    assert one.status_code == 202
    from studio.api import app, current_actor

    app.dependency_overrides[current_actor] = lambda: Actor("other-member", "demo", "owner")
    try:
        assert client.get(f"/api/conversations/{cid}").status_code == 404
        assert client.delete(f"/api/conversations/{cid}").status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert (
        client.post(
            "/api/conversations",
            json=dict(context=context),
            headers={"Origin": "https://foreign.invalid", "Idempotency-Key": "csrf"},
        ).status_code
        == 403
    )
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    drain(factory, worker)
    assert client.get(f"/api/conversations/{cid}").status_code == 404
    assert client.get("/api/conversations", params=dict(project_id=pid)).json()["items"] == []
    with factory() as db:
        assert list(db.query(MessageRow)) == []
    assert client.get(f"/api/jobs/{one.json()['job_id']}").json()["status"] == "FAILED"


def test_assistant_worker_crash_fencing_and_unknown_delivery_hold(pg, monkeypatch):  # noqa: F811
    from datetime import timedelta

    from sqlalchemy import func, select
    from studio.database import AuditRow, JobRow, MessageRow, now

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    one = ask(client, cid, context).json()
    with factory() as db:
        first = worker.claim_job(db)
        assert first[0] == one["job_id"]
        job = db.get(JobRow, one["job_id"])
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    with factory() as db:
        second = worker.claim_job(db)
    worker.process_job(*first)
    worker.process_job(*second)
    with factory() as db:
        assert db.get(JobRow, one["job_id"]).attempts == 2
        assert (
            db.scalar(
                select(func.count()).select_from(MessageRow).where(MessageRow.role == "assistant")
            )
            == 1
        )
    # Sau reservation mà chưa rõ delivery: không resend, kể cả policy task đã bật trong test.
    two = ask(client, cid, context, key="uncertain").json()
    with factory() as db:
        db.add(
            AuditRow(
                workspace_id="demo",
                actor_id="test-owner",
                action="ASSISTANT_REQUEST_RESERVED",
                resource_id=two["job_id"],
            )
        )
        db.commit()
    drain(factory, worker)
    job = client.get(f"/api/jobs/{two['job_id']}").json()
    assert (job["status"], job["error_code"]) == ("BLOCKED", "AI_DELIVERY_UNKNOWN")
    assert len(client.get(f"/api/conversations/{cid}").json()["items"]) == 3


def test_language_request_checks_preparation_and_never_auto_runs(pg):  # noqa: F811
    from sqlalchemy import func, select
    from studio.database import RunRow

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    result = ask(client, cid, context, question="Đối soát ba file tháng 10")
    assert result.status_code == 202
    drain(factory, worker)
    answer = client.get(f"/api/conversations/{cid}").json()["items"][-1]["answer"]
    assert (
        answer["status"] == "REVIEW_REQUIRED"
        and answer["proposal"]["confirmation_required"] is True
    )
    assert answer["proposal"]["approved_rule_ids"] == []
    assert answer["proposal"]["required_sources"] == 3
    assert (
        answer["proposal"]["requested_month"] == 10 and answer["proposal"]["requested_year"] is None
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0


def test_reviewed_template_action_idempotent_and_unapproved_until_human_confirmation(pg):  # noqa: F811
    client, _, _ = pg
    _, plan, rule, _ = create_approved_run(pg)
    body = dict(
        left_canonical_id=plan.left.canonical_id,
        right_canonical_id=plan.right.canonical_id,
        period_start=str(plan.period_start),
        period_end=str(plan.period_end),
        left_coverage_start=str(plan.left.coverage_start),
        left_coverage_end=str(plan.left.coverage_end),
        right_coverage_start=str(plan.right.coverage_start),
        right_coverage_end=str(plan.right.coverage_end),
        completeness="CONFIRMED",
        snapshot_at=plan.left.snapshot_at.isoformat(),
    )
    path = f"/api/reconciliation-contracts/{rule['id']}/reuse"
    one = client.post(path, json=body, headers={"Idempotency-Key": "reviewed-action"})
    assert one.status_code == 201, one.text
    two = client.post(path, json=body, headers={"Idempotency-Key": "reviewed-action"})
    assert two.json() == one.json()
    assert one.json()["proposal"]["status"] == "PROPOSED" and one.json()["contract_id"] is None
    body["snapshot_at"] = "2026-11-01T00:00:00Z"
    assert (
        client.post(path, json=body, headers={"Idempotency-Key": "reviewed-action"}).status_code
        == 409
    )


def test_task_budget_reservation_failure_receipt_and_no_blind_resend(pg, monkeypatch):  # noqa: F811
    import studio.assistant_jobs as jobs
    from pydantic import SecretStr
    from sqlalchemy import func, select
    from studio.config import settings
    from studio.contracts.assistant import AssistantAnswer
    from studio.database import AuditRow, TraceRow, WorkspaceRow

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", 10)
    monkeypatch.setattr(settings, "assistant_cloud_enabled", True)
    monkeypatch.setattr(settings, "assistant_request_budget", 1)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic"))
    with factory() as db:
        db.get(WorkspaceRow, "demo").policy = dict(
            mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=10
        )
        db.commit()
    attempts = []

    def mocked(question, facts, policy, config, reserve):
        allowed = reserve()
        attempts.append(allowed)
        if allowed:
            raise DomainError("GEMINI_UNAVAILABLE", "MOCK delivery unknown", 503)
        return AssistantAnswer(
            status="PROVIDER_UNAVAILABLE",
            mode="DETERMINISTIC",
            fact_set=facts,
            lines=[],
            suggestions=[],
        )

    monkeypatch.setattr(jobs, "answer_question", mocked)
    one = ask(client, cid, context, key="reserved").json()
    drain(factory, worker)
    assert client.get(f"/api/jobs/{one['job_id']}").json()["status"] == "BLOCKED"
    assert ask(client, cid, context, key="exhausted").status_code == 202
    drain(factory, worker)
    assert attempts == [True, False]
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "GEMINI_REQUEST_RESERVED")
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "ASSISTANT_REQUEST_RESERVED")
            )
            == 1
        )
        trace = db.scalar(select(TraceRow).where(TraceRow.job_id == one["job_id"]))
        assert trace.usage == dict(reserved_attempts=1, tokens=None, cost_estimate=None)
