"""Oracle tổng hợp: queue/approval/normalization thật, provider được ghi rõ MOCK."""

from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from studio.access import Actor
from studio.agent_api import decide
from studio.contracts.agent import AgentIntent, NormalizationDraft, ReviewDecision
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    CanonicalRow,
    JobRow,
    MappingRow,
    MembershipRow,
    now,
)
from studio.errors import DomainError
from test_assistant_postgres import conversation
from test_postgres import drain, pg, project  # noqa: F401
from test_reconciliation_postgres import create_approved_run

pytestmark = pytest.mark.integration


def test_settings_chat_limits_match_enforced_upload_contract(pg, monkeypatch):  # noqa: F811
    """Giới hạn công bố và upload cùng đổi theo cấu hình; GET không gọi provider."""
    from studio.config import settings

    client, factory, _ = pg
    monkeypatch.setattr(settings, "max_upload_files", 2)
    before = client.get("/api/settings").json()
    assert before["agent_max_upload_files"] == 2
    assert before["agent_upload_extensions"] == [".csv", ".xlsx"]
    assert before["cloud_live_status"] == "NOT VERIFIED"
    response = client.post(
        "/api/agent/attachments",
        files=[
            ("files", (f"synthetic-{i}.csv", b"id,amount\n000702,12.75\n", "text/csv"))
            for i in range(3)
        ],
        headers={"Idempotency-Key": "over-chat-file-limit"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TOO_MANY_FILES"
    monkeypatch.setattr(settings, "max_upload_files", 10)
    after = client.get("/api/settings").json()
    assert after["agent_max_upload_files"] == 5
    assert after["max_upload_files"] == 10
    assert after["gemini_requests_used"] == before["gemini_requests_used"]
    assert set(after["ai_task_allowances"]) == {"agent", "planner", "assistant"}
    assert all(t["remaining"] == 0 for t in after["ai_task_allowances"].values())
    with factory() as db:
        assert not db.scalar(select(func.count()).select_from(JobRow))


def ask_agent(client, context, cid, *, command=None, key="agent", text="Chuẩn hóa dữ liệu"):
    response = client.post(
        "/api/assistant/messages",
        json=dict(conversation_id=cid, context=context, mode="AGENT", command=command, text=text),
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_settings_task_allowance_exhaustion_is_independent_from_global_budget(pg, monkeypatch):  # noqa: F811
    """Planner hết lượt không được hiển thị như còn quyền chỉ vì global còn nhiều."""
    from studio.config import settings
    from studio.database import WorkspaceRow

    client, factory, _ = pg
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", 100)
    monkeypatch.setattr(settings, "agent_request_budget", 100)
    monkeypatch.setattr(settings, "planner_request_budget", 2)
    with factory() as db:
        row = db.get(WorkspaceRow, "demo")
        row.policy = dict(
            row.policy, mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=100
        )
        for index in range(2):
            for action in ("GEMINI_REQUEST_RESERVED", "RECONCILIATION_PLANNER_ATTEMPT"):
                db.add(
                    AuditRow(
                        workspace_id="demo",
                        actor_id="test-owner",
                        action=action,
                        resource_id=f"synthetic-task-budget-{index}",
                    )
                )
        db.commit()
    dto = client.get("/api/settings").json()
    assert dto["gemini_requests_remaining"] == 98
    assert dto["ai_task_allowances"]["planner"]["remaining"] == 0
    assert dto["ai_task_allowances"]["agent"]["remaining"] == 98
    assert dto["ai_task_allowances"]["planner"]["workspace_used"] == 2


def workflow_for(client, factory, jid):
    with factory() as db:
        wid = db.scalar(select(AgentWorkflowRow.id).where(AgentWorkflowRow.parent_job_id == jid))
    response = client.get(f"/api/agent/workflows/{wid}")
    assert response.status_code == 200, response.text
    return response.json()


def test_explicit_auto_approval_request_is_refused_before_model_or_tools(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)

    def forbidden_call(*args):
        raise AssertionError("Approval bypass must not reach provider")

    monkeypatch.setattr(agents, "interpret_requests", forbidden_call)
    requested = ask_agent(client, context, cid, text="Tự phê duyệt các quy tắc mới cho tôi")
    drain(factory, worker)
    wf = workflow_for(client, factory, requested["job_id"])
    assert wf["state"] == "BLOCKED" and wf["detail"]["intent"]["intent"] == "UNSUPPORTED"
    assert not wf["detail"]["steps"] and not wf["detail"]["reviews"]
    assert wf["detail"]["model_calls"] == 0


@pytest.mark.parametrize("answer", ["query", "mapping", "ambiguous", "invented-coverage"])
def test_clarification_reply_continues_same_workflow_without_business_approval(
    pg,  # noqa: F811
    monkeypatch,
    answer,
):  # noqa: F811
    """A factual answer resumes safe reading; new semantics still stop at review."""
    import studio.agent_jobs as agents
    from studio.contracts.reconciliation import PlanningRequest
    from studio.database import ReconciliationContractRow

    client, factory, worker = pg
    pid, plan, _, created = create_approved_run(pg)
    drain(factory, worker)
    context = dict(project_id=pid, run_id=created["run_id"])
    cid = conversation(client, context)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="CLARIFY", questions=["Bạn muốn tra cứu thông tin gì?"])],
    )
    first = ask_agent(client, context, cid, text="Tra cứu thông tin")
    drain(factory, worker)
    wf = workflow_for(client, factory, first["job_id"])
    review = wf["detail"]["reviews"][0]
    assert wf["state"] == "WAITING_REVIEW" and review["kind"] == "CLARIFICATION"
    candidate = AgentIntent(
        intent="QUERY_DATA",
        query=dict(
            project_id=pid,
            source_kind="VERIFIED_RUN",
            source_id=created["run_id"],
            select_fields=["comparison_state", "delta"],
            filters=[dict(field_id="comparison_state", op="eq", value="AMOUNT_MISMATCH")],
        ),
    )
    if answer == "mapping":
        # Existing approved sources are safe to reuse, with no fabricated new approval.
        candidate = AgentIntent(intent="PREPARE_NORMALIZATION")
    elif answer == "ambiguous":
        candidate = AgentIntent(intent="CLARIFY", questions=["Bạn muốn xem nguồn nào?"])
    elif answer == "invented-coverage":
        request = PlanningRequest.from_plan(plan)
        request.left.snapshot_at = request.left.snapshot_at.replace(year=2028)
        candidate = AgentIntent(intent="RECONCILE_DATASETS", planning_request=request)
    monkeypatch.setattr(agents, "interpret_requests", lambda *args: [candidate])
    body = dict(
        review_id=review["id"],
        nonce=review["nonce"],
        fingerprint=review["fingerprint"],
        text="Xem các giao dịch chênh lệch" if answer != "mapping" else "Chuẩn hóa dữ liệu",
    )
    path = f"/api/agent/workflows/{wf['id']}"
    accepted = client.post(
        path + "/replies", json=body, headers={"Idempotency-Key": "clarification-reply"}
    )
    assert accepted.status_code == 202, accepted.text
    drain(factory, worker)
    after = client.get(path).json()
    messages = client.get(f"/api/conversations/{cid}").json()["items"]
    if answer == "invented-coverage":
        assert after["state"] == "WAITING_REVIEW"
        assert after["detail"]["reviews"][0]["state"] == "OPEN"
        assert after["detail"]["error_code"] == "INPUT_AMBIGUOUS"
    elif answer == "ambiguous":
        assert after["state"] == "WAITING_REVIEW"
        assert after["detail"]["reviews"][0]["reply_questions"] == candidate.questions
    else:
        assert after["state"] == "COMPLETED", after
        assert after["detail"]["reviews"][0]["state"] == "DECIDED"
        assert messages[-1]["workflow_id"] == wf["id"]
        if answer == "query":
            table = next(b["result"] for b in after["detail"]["blocks"] if b["type"] == "table")
            assert table["total_count"] == 1 and table["rows"][0]["delta"] == "2.75"
    assert (
        client.post(
            path + "/replies", json=body, headers={"Idempotency-Key": "clarification-reply"}
        ).json()["job_id"]
        == accepted.json()["job_id"]
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 2
        )


def test_clarification_to_new_normalization_still_requires_mapping_approval(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    wf, _ = mapping_fixture(pg, monkeypatch)
    context = dict(project_id=wf["context"]["project_id"])
    cid = conversation(client, context)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="CLARIFY", questions=["Bạn muốn làm gì với dữ liệu?"])],
    )
    queued = ask_agent(client, context, cid, key="clarify-new", text="Giúp tôi xử lý")
    drain(factory, worker)
    waiting = workflow_for(client, factory, queued["job_id"])
    review = waiting["detail"]["reviews"][0]
    monkeypatch.setattr(
        agents, "interpret_requests", lambda *args: [AgentIntent(intent="PREPARE_NORMALIZATION")]
    )
    path = f"/api/agent/workflows/{waiting['id']}"
    response = client.post(
        path + "/replies",
        json=dict(
            review_id=review["id"],
            nonce=review["nonce"],
            fingerprint=review["fingerprint"],
            text="Chuẩn hóa hai nguồn",
        ),
        headers={"Idempotency-Key": "clarify-to-mapping"},
    )
    assert response.status_code == 202
    drain(factory, worker)
    done = client.get(path).json()
    assert done["state"] == "WAITING_REVIEW"
    assert any(r["kind"] == "MAPPING" and r["state"] == "OPEN" for r in done["detail"]["reviews"])
    with factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 0
        )
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0


def test_followup_position_uses_persisted_displayed_page_and_never_another_conversation(
    pg,  # noqa: F811
    monkeypatch,
):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.assistant_tools import agent_catalogue
    from studio.contracts.assistant import AssistantContext
    from studio.contracts.data_query import DataQuery

    client, factory, worker = pg
    pid, _, _, created = create_approved_run(pg)
    drain(factory, worker)
    context = dict(project_id=pid, run_id=created["run_id"])
    cid = conversation(client, context)
    query = DataQuery(
        project_id=pid,
        source_kind="VERIFIED_RUN",
        source_id=created["run_id"],
        select_fields=["comparison_state", "delta"],
        limit=1,
    )
    monkeypatch.setattr(
        agents, "interpret_requests", lambda *args: [AgentIntent(intent="QUERY_DATA", query=query)]
    )
    asked = ask_agent(client, context, cid, text="Xem các nhóm giao dịch")
    drain(factory, worker)
    first = workflow_for(client, factory, asked["job_id"])
    original = first["detail"]["blocks"]
    resolved = next(b["result"]["query"] for b in original if b["type"] == "table")
    path = f"/api/agent/workflows/{first['id']}/query-pages"
    page = client.post(
        path, json=resolved | dict(offset=1, sort=[dict(field_id="group_id", descending=True)])
    )
    assert page.status_code == 200, page.text
    selected = page.json()["rows"][0]["group_id"]
    reopened = client.get(f"/api/agent/workflows/{first['id']}").json()
    assert reopened["detail"]["blocks"] == original
    assert reopened["detail"]["query_selection"]["group_ids"] == [selected]
    assert client.post(path, json=resolved | dict(source_id="foreign-run")).status_code == 409
    assert (
        client.post(
            path,
            json=resolved
            | dict(filters=[dict(field_id="linkage_state", op="eq", value="UNMATCHED")]),
        ).status_code
        == 409
    )
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="EXPLAIN_RESULT", result_position=1)],
    )
    followup = ask_agent(
        client,
        context,
        cid,
        key="position",
        text="Giải thích giao dịch đầu tiên trong bảng đang xem",
    )
    drain(factory, worker)
    second = workflow_for(client, factory, followup["job_id"])
    assert second["state"] == "COMPLETED", second
    assert second["context"]["group_id"] == selected
    assert (
        next(b["result"]["group"]["id"] for b in second["detail"]["blocks"] if b["type"] == "facts")
        == selected
    )
    summarized = ask_agent(
        client,
        context,
        cid,
        command="SUMMARIZE_RESULTS",
        key="summary-after-explanation",
        text="Tóm tắt toàn bộ kết quả",
    )
    drain(factory, worker)
    summary = workflow_for(client, factory, summarized["job_id"])
    assert summary["context"]["group_id"] is None and summary["context"]["case_id"] is None
    assert (
        next(b["result"]["run"] for b in summary["detail"]["blocks"] if b["type"] == "facts")
        is not None
    )
    # Same project, different conversation must not inherit the page or its filters.
    other = conversation(client, context, key="other-conversation")
    another = ask_agent(
        client, context, other, key="other-position", text="Giải thích giao dịch đầu tiên"
    )
    drain(factory, worker)
    foreign = workflow_for(client, factory, another["job_id"])
    assert foreign["state"] != "COMPLETED"
    with factory() as db:
        cat = agent_catalogue(
            db,
            Actor("test-owner", "demo", "owner"),
            AssistantContext(**context),
            [],
            workflow_id=foreign["id"],
        )
        assert cat.previous_query is None and cat.previous_groups == []


def test_displayed_page_changed_during_inference_never_explains_a_different_group(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.contracts.data_query import DataQuery

    client, factory, worker = pg
    pid, _, _, created = create_approved_run(pg)
    drain(factory, worker)
    context = dict(project_id=pid, run_id=created["run_id"])
    cid = conversation(client, context)
    query = DataQuery(
        project_id=pid, source_kind="VERIFIED_RUN", source_id=created["run_id"], limit=1
    )
    monkeypatch.setattr(
        agents, "interpret_requests", lambda *args: [AgentIntent(intent="QUERY_DATA", query=query)]
    )
    asked = ask_agent(client, context, cid, text="Liệt kê giao dịch")
    drain(factory, worker)
    first = workflow_for(client, factory, asked["job_id"])

    def change_page(*args):
        response = client.post(
            f"/api/agent/workflows/{first['id']}/query-pages",
            json=query.model_dump(mode="json") | dict(offset=1),
        )
        assert response.status_code == 200, response.text
        return [AgentIntent(intent="EXPLAIN_RESULT", result_position=1)]

    monkeypatch.setattr(agents, "interpret_requests", change_page)
    second = ask_agent(client, context, cid, key="page-race", text="Giải thích giao dịch đầu tiên")
    drain(factory, worker)
    result = workflow_for(client, factory, second["job_id"])
    assert result["state"] == "BLOCKED" and result["detail"]["error_code"] == "STALE_CONTEXT"
    assert not result["detail"]["blocks"] and result["context"]["group_id"] is None


def mapping_fixture(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid = project(client)
    result = client.post(
        "/api/datasets/uploads",
        data=dict(project_id=pid, request_ai_mapping="false"),
        files=[
            (
                "files",
                (
                    "synthetic.csv",
                    b"id,amount,date\n000701,25.00,2026-10-01\n000702,12.75,2026-10-02\n",
                    "text/csv",
                ),
            )
        ],
    )
    assert result.status_code == 202, result.text
    drain(factory, worker)

    def mock_draft(provider, table_id, profile, policy, reserve):
        return NormalizationDraft.model_validate(
            dict(
                table_id=table_id,
                entity_kind="delivery",
                grain="one delivery per row",
                fields=[
                    dict(
                        source_field="c1",
                        target_id="delivery_id",
                        name="ID",
                        data_type="string",
                        business_key=True,
                    ),
                    dict(
                        source_field="c2",
                        target_id="amount",
                        name="Amount",
                        data_type="decimal",
                        locale="en-US",
                        currency="VND",
                        unit="VND",
                        semantic_metric="delivery_charge",
                        amount_basis="gross",
                        question="Xác nhận gross/VND và locale?",
                    ),
                    dict(
                        source_field="c3",
                        target_id="date",
                        name="Date",
                        data_type="date",
                        date_format="%Y-%m-%d",
                        timezone="UTC",
                    ),
                ],
            )
        )

    monkeypatch.setattr(agents, "propose_normalization", mock_draft)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    queued = ask_agent(client, context, cid, command="PREPARE_NORMALIZATION")
    drain(factory, worker)
    wf = workflow_for(client, factory, queued["job_id"])
    assert wf["state"] == "WAITING_REVIEW", wf
    review = wf["detail"]["reviews"][0]
    assert review["resource_label"].startswith("synthetic.csv")
    body = dict(
        review_id=review["id"],
        nonce=review["nonce"],
        fingerprint=review["fingerprint"],
        decision=dict(type="MAPPING", draft=review["normalization_draft"].copy()),
    )
    # Quy ước được người vận hành TEST xác nhận; không coi timezone/basis từ model là bằng chứng.
    from copy import deepcopy
    body["decision"]["draft"] = deepcopy(body["decision"]["draft"])
    for field in body["decision"]["draft"]["fields"]:
        if field["data_type"] == "date":
            field["timezone"] = "UTC"
        if field["data_type"] == "decimal":
            field["amount_basis"] = "gross"
    return wf, body


def test_agent_mock_mapping_review_atomic_resume_reopen_idempotency(pg, monkeypatch):  # noqa: F811
    client, factory, worker = pg
    wf, body = mapping_fixture(pg, monkeypatch)
    wid = wf["id"]
    with factory() as db:
        baseline = db.scalar(select(func.count()).select_from(MappingRow))
        pending = decide(
            db, Actor("test-owner", "demo", "owner"), wid, ReviewDecision.model_validate(body)
        )
        assert pending.state == "RUNNING"
        db.rollback()
        assert db.scalar(select(func.count()).select_from(MappingRow)) == baseline
        assert db.get(AgentWorkflowRow, wid).state == "WAITING_REVIEW"
    path = f"/api/agent/workflows/{wid}/decisions"
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda key: client.post(path, json=body, headers={"Idempotency-Key": key}),
                ["review", "concurrent-review"],
            )
        )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert client.post(path, json=body, headers={"Idempotency-Key": "retry"}).status_code == 200
    drain(factory, worker)
    done = client.get(f"/api/agent/workflows/{wid}").json()
    assert done["state"] == "COMPLETED", done
    block = next(b for b in done["detail"]["blocks"] if b["type"] == "dataset_summary")
    assert (block["rows"], block["invalid_rows"], block["status"]) == (2, 0, "READY")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "AGENT_REVIEW_DECIDED")
            )
            == 1
        )
        assert (
            db.scalar(select(func.count()).select_from(JobRow).where(JobRow.kind == "normalize"))
            == 1
        )
    changed = ReviewDecision.model_validate(body)
    changed.decision.draft.grain = "changed"
    assert (
        client.post(
            path, json=changed.model_dump(mode="json"), headers={"Idempotency-Key": "changed"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("reason", ["nonce", "expiry", "revision", "viewer", "cancel"])
def test_agent_review_denies_stale_permission_cancel_without_approval(pg, monkeypatch, reason):  # noqa: F811
    client, factory, worker = pg
    wf, body = mapping_fixture(pg, monkeypatch)
    if reason == "nonce":
        body["nonce"] = "a" * 32
    with factory() as db:
        row = db.get(AgentWorkflowRow, wf["id"])
        if reason == "expiry":
            detail = deepcopy(row.detail)
            detail["reviews"][0]["expires_at"] = (now() - timedelta(minutes=1)).isoformat()
            row.detail = detail
        elif reason == "revision":
            table = body["decision"]["draft"]["table_id"]
            db.scalar(select(MappingRow).where(MappingRow.source_table_id == table)).revision += 1
        elif reason == "viewer":
            db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
        baseline = db.scalar(select(func.count()).select_from(MappingRow))
    if reason == "cancel":
        response = client.post(
            f"/api/agent/workflows/{wf['id']}/cancel", headers={"Idempotency-Key": "cancel"}
        )
        assert response.status_code == 200
    response = client.post(
        f"/api/agent/workflows/{wf['id']}/decisions",
        json=body,
        headers={"Idempotency-Key": "denied"},
    )
    assert response.status_code == (403 if reason == "viewer" else 409), response.text
    drain(factory, worker)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MappingRow)) == baseline
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0


def test_agent_approved_contract_runs_without_new_approval_and_verifier_oracle(pg, monkeypatch):  # noqa: F811
    import json

    import studio.agent_jobs as agents
    from studio.agent_intents import compile_routing
    from studio.contracts.reconciliation import ReconciliationPlan

    client, factory, worker = pg
    pid, plan, rule, queued = create_approved_run(pg)
    drain(factory, worker)
    if not isinstance(plan, ReconciliationPlan):
        plan = ReconciliationPlan.model_validate(plan)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda provider, goals, catalogue, policy, reserve: compile_routing(
            json.dumps(
                dict(
                    intents=[
                        dict(
                            intent="RECONCILE_DATASETS",
                            reconciliation=dict(
                                left_canonical_id=plan.left.canonical_id,
                                right_canonical_id=plan.right.canonical_id,
                                confirmed_run_id=queued["run_id"],
                            ),
                        )
                    ]
                )
            ),
            goals,
            catalogue,
        ),
    )
    context = dict(project_id=pid, run_id=queued["run_id"])
    cid = conversation(client, context)
    message = ask_agent(client, context, cid, text="Đối soát kỳ 2026 theo phạm vi đã xác nhận")
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "COMPLETED", wf
    assert wf["detail"]["confirmed_contract_id"] == rule["id"]
    assert wf["context"]["run_id"] == queued["run_id"]
    assert not wf["detail"]["reviews"]
    assert any(b["type"] == "facts" for b in wf["detail"]["blocks"])
    chart = next(b for b in wf["detail"]["blocks"] if b["type"] == "chart")
    assert chart["population"] == 4
    assert {p["label"]: p["value"] for p in chart["points"]} == {
        "EQUAL": "1",
        "AMOUNT_MISMATCH": "1",
        # Hai mã703/704 chỉ ở một phía: chưa đánh giá comparison theo contract.
        "NOT_EVALUATED": "2",
    }
    with factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(JobRow).where(JobRow.kind == "reconcile"))
            == 1
        )
    assert client.get(f"/api/conversations/{cid}").json()["items"][-1]["workflow_id"] == wf["id"]


def test_agent_provider_blocked_is_durable_no_retry_or_fake_complete(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid = project(client)

    def blocked(*args):
        raise DomainError("CLOUD_BUDGET_EXHAUSTED", "Policy blocked")

    monkeypatch.setattr(agents, "interpret_requests", blocked)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    message = ask_agent(client, context, cid)
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "BLOCKED" and wf["detail"]["error_code"] == "CLOUD_BUDGET_EXHAUSTED"
    assert not wf["detail"]["blocks"]
    same = ask_agent(client, context, cid)
    assert same["job_id"] == message["job_id"]


def test_agent_attachments_bootstrap_scope_idempotency_no_cloud(pg):  # noqa: F811
    from studio.database import ArtifactRow, DatasetRow, ProjectRow

    client, factory, worker = pg
    headers = {"Idempotency-Key": "inline-two-files"}
    files = [
        ("files", ("Ledger.csv", b"voucher,amount\n000701,25.00\n", "text/csv")),
        ("files", ("Vouchers.csv", b"voucher,amount\n000701,20.00\n", "text/csv")),
    ]
    path = "/api/agent/attachments"
    response = client.post(path, files=files, headers=headers)
    assert response.status_code == 202, response.text
    receipt = response.json()
    assert not receipt["scope_confirmed"] and len(receipt["items"]) == 2
    assert client.post(path, files=files, headers=headers).json() == receipt
    assert client.post(path, files=files[:1], headers=headers).status_code == 409
    drain(factory, worker)
    with factory() as db:
        project = db.get(ProjectRow, receipt["project_id"])
        assert project.business_scope == f"UNCONFIRMED:{project.id}"
        assert db.scalar(select(func.count()).select_from(ProjectRow)) == 1
        assert db.scalar(select(func.count()).select_from(DatasetRow)) == 2
        assert (
            db.scalar(
                select(func.count()).select_from(ArtifactRow).where(ArtifactRow.kind == "raw")
            )
            == 2
        )
        assert (
            db.scalar(select(func.count()).select_from(JobRow).where(JobRow.kind == "mapping")) == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "GEMINI_REQUEST_RESERVED")
            )
            == 0
        )
        db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
    assert client.post(path, files=files, headers={"Idempotency-Key": "viewer"}).status_code == 403


def test_agent_attachment_invalid_input_rolls_back_bootstrap(pg):  # noqa: F811
    from studio.database import ProjectRow

    client, factory, _ = pg
    response = client.post(
        "/api/agent/attachments",
        files=[
            (
                "files",
                (
                    "broken.xlsx",
                    b"broken",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
        headers={"Idempotency-Key": "invalid"},
    )
    assert response.status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ProjectRow)) == 0


def test_agent_mock_new_rule_requires_review_before_real_verified_run(pg, monkeypatch):  # noqa: F811
    from datetime import date

    import studio.agent_jobs as agents
    import studio.reconciliation_jobs as planning
    from studio.contracts.reconciliation import PlanningRequest, PlanProposal
    from studio.database import ReconciliationContractRow, RunRow

    client, factory, worker = pg
    pid, plan, _, first = create_approved_run(pg)
    drain(factory, worker)
    revised = plan.model_copy(update={"period_end": date(2026, 10, 15)})
    request = PlanningRequest.from_plan(revised)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="RECONCILE_DATASETS", planning_request=request)],
    )
    monkeypatch.setattr(
        planning, "propose_plan", lambda *args: PlanProposal(status="PROPOSED", plan=revised)
    )
    context = dict(project_id=pid)
    cid = conversation(client, context)
    message = ask_agent(client, context, cid, text="Đối soát kỳ1–15/10/2026")
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "WAITING_REVIEW" and wf["context"]["run_id"] is None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 1
        assert db.scalar(select(func.count()).select_from(RunRow)) == 1
    review = wf["detail"]["reviews"][0]
    decision = dict(
        review_id=review["id"],
        nonce=review["nonce"],
        fingerprint=review["fingerprint"],
        decision=dict(type="RECONCILIATION", plan=review["plan"]),
    )
    path = f"/api/agent/workflows/{wf['id']}/decisions"
    accepted = client.post(path, json=decision, headers={"Idempotency-Key": "approve-period"})
    assert accepted.status_code == 200, accepted.text
    drain(factory, worker)
    done = client.get(f"/api/agent/workflows/{wf['id']}").json()
    assert done["state"] == "COMPLETED"
    assert done["context"]["run_id"] != first["run_id"]
    assert (
        client.post(path, json=decision, headers={"Idempotency-Key": "repeat-period"}).status_code
        == 200
    )
    # Tiếp lời trong cùng hội thoại dùng run vừa công bố, không lấy newest của project.
    followup = ask_agent(
        client,
        context,
        cid,
        command="SUMMARIZE_RESULTS",
        key="followup",
        text="Tóm tắt kết quả vừa đối soát",
    )
    drain(factory, worker)
    second = workflow_for(client, factory, followup["job_id"])
    assert (
        second["state"] == "COMPLETED" and second["context"]["run_id"] == done["context"]["run_id"]
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 2
        assert db.scalar(select(func.count()).select_from(RunRow)) == 2


def test_agent_mock_query_chart_uses_all_matching_not_page(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.contracts.data_query import DataQuery

    client, factory, worker = pg
    pid, plan, _, _ = create_approved_run(pg)
    drain(factory, worker)
    query = DataQuery(
        project_id=pid,
        source_kind="CANONICAL",
        source_id=plan.left.canonical_id,
        group_by=["currency"],
        currency_field="currency",
        limit=1,
        aggregations=[dict(op="sum_decimal", field_id="delivery_charge")],
    )
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="CREATE_VISUALIZATION", query=query)],
    )
    context = dict(project_id=pid)
    cid = conversation(client, context)
    message = ask_agent(client, context, cid, text="Vẽ tổng phí giao hàng theo tiền tệ")
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "COMPLETED", wf
    chart = next(b for b in wf["detail"]["blocks"] if b["type"] == "chart")
    from decimal import Decimal

    assert len(chart["points"]) == 1 and chart["points"][0]["label"] == "VND"
    assert isinstance(chart["points"][0]["value"], str)
    assert Decimal(chart["points"][0]["value"]) == Decimal("42.75")
    assert chart["population"] == 3 and chart["unit"] == "VND"
    assert chart["verification_status"] == "CANONICAL" and chart["completeness"] == "COMPLETE"


def test_agent_mock_exact_key_explanation_preserves_zero_prefix_and_evidence(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.agent_tools import GroupLookupAction, execute_tool
    from studio.contracts.assistant import AssistantContext

    client, factory, worker = pg
    pid, _, _, queued = create_approved_run(pg)
    drain(factory, worker)
    context = dict(project_id=pid, run_id=queued["run_id"])
    cid = conversation(client, context)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="EXPLAIN_RESULT", key_value="000702")],
    )
    message = ask_agent(client, context, cid, text="Vì sao giao dịch000702có hai phía nhưng lệch?")
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "COMPLETED" and wf["context"]["group_id"]
    block = next(b for b in wf["detail"]["blocks"] if b["type"] == "facts")
    assert any("12.75 / 10.00 / 2.75 / 0 VND" in line["text"] for line in block["answer"]["lines"])
    refs = block["answer"]["fact_set"]["references"]
    assert len({r["member_id"] for r in refs if r.get("member_id")}) == 2
    with factory() as db:
        actor = Actor("test-owner", "demo", "owner")
        for key, code in [
            ("702", "INSUFFICIENT_EVIDENCE"),
            ("CARRIER-A", "INPUT_AMBIGUOUS"),
            ("000702' OR 1=1 --", "INSUFFICIENT_EVIDENCE"),
        ]:
            with pytest.raises(DomainError, match=code):
                execute_tool(
                    db,
                    actor,
                    GroupLookupAction(
                        name="find_match_group", context=AssistantContext(**context), key_value=key
                    ),
                    "lookup-negative",
                )


@pytest.mark.parametrize("ceiling", [2, None])
def test_agent_durable_unknown_delivery_reserves_once_and_never_resends(pg, monkeypatch, ceiling):  # noqa: F811
    import studio.agent_jobs as agents
    from pydantic import SecretStr
    from studio.config import settings
    from studio.contracts import WorkspacePolicy
    from studio.database import WorkspaceRow

    client, factory, worker = pg
    pid = project(client)
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-only"))
    monkeypatch.setattr(settings, "external_ai_request_budget", ceiling)
    monkeypatch.setattr(settings, "agent_cloud_enabled", True)
    monkeypatch.setattr(settings, "agent_request_budget", ceiling)
    with factory() as db:
        db.get(WorkspaceRow, "demo").policy = WorkspacePolicy(
            mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=ceiling
        ).model_dump(mode="json")
        db.commit()
    calls = []

    def crash_after_reserving(provider, goals, catalogue, policy, reserve):
        calls.append(True)
        assert reserve()
        raise RuntimeError("Synthetic crash between delivery and publication; no actual HTTP")

    monkeypatch.setattr(agents, "interpret_requests", crash_after_reserving)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    message = ask_agent(client, context, cid)
    drain(factory, worker)
    with factory() as db:
        job = db.get(JobRow, message["job_id"])
        assert job.status == "RETRYABLE_FAILURE" and job.attempts == 1
        job.available_at = now()
        db.commit()
    drain(factory, worker)
    wf = workflow_for(client, factory, message["job_id"])
    assert wf["state"] == "BLOCKED" and wf["detail"]["error_code"] == "AI_DELIVERY_UNKNOWN"
    assert len(calls) == 1 and wf["detail"]["model_calls"] == 1
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
                .where(AuditRow.action == "AGENT_REQUEST_RESERVED")
            )
            == 1
        )


@pytest.mark.parametrize("answer", ["complete", "ambiguous", "wrong-source"])
def test_agent_review_natural_reply_is_bound_preview_never_auto_approval(pg, monkeypatch, answer):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.contracts.agent import ReviewInterpretation

    client, factory, worker = pg
    wf, original_decision = mapping_fixture(pg, monkeypatch)
    original = wf["detail"]["reviews"][0]
    candidate = NormalizationDraft.model_validate(original["normalization_draft"])
    candidate.fields[1].amount_basis = "net"
    if answer == "wrong-source":
        candidate.table_id = "foreign-table"
    monkeypatch.setattr(
        agents,
        "interpret_review_reply",
        lambda *args: (
            ReviewInterpretation(questions=["Bạn muốn gross hay net?"])
            if answer == "ambiguous"
            else ReviewInterpretation(draft=candidate)
        ),
    )
    body = dict(
        review_id=original["id"],
        nonce=original["nonce"],
        fingerprint=original["fingerprint"],
        text="Cột tiền là net, VND; để tôi xem trước.",
    )
    path = f"/api/agent/workflows/{wf['id']}"
    queued = client.post(path + "/replies", json=body, headers={"Idempotency-Key": "reply"})
    assert queued.status_code == 202, queued.text
    assert (
        client.post(path + "/replies", json=body, headers={"Idempotency-Key": "reply"}).json()
        == queued.json()
    )
    assert (
        client.post(
            path + "/decisions", json=original_decision, headers={"Idempotency-Key": "too-early"}
        ).status_code
        == 409
    )
    drain(factory, worker)
    current = client.get(path).json()
    assert current["state"] == "WAITING_REVIEW"
    review = current["detail"]["reviews"][0]
    assert review["state"] == "OPEN" and review["pending_reply_job_id"] is None
    messages = client.get(f"/api/conversations/{wf['conversation_id']}").json()["items"]
    assert messages[-2]["text"] == body["text"]
    if answer == "wrong-source":
        assert messages[-1]["role"] == "assistant" and messages[-1]["error_code"]
    if answer != "wrong-source":
        assert messages[-1]["role"] == "assistant" and messages[-1]["answer"] is None
        assert "xác nhận" in messages[-1]["text"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 0
        )
    if answer == "wrong-source":
        assert review["normalization_draft"]["table_id"] == original["resource_id"]
        assert current["detail"]["error_code"] == "INVALID_SOURCE_FIELD"
        return
    assert review["nonce"] != original["nonce"]
    assert (
        client.post(path + "/replies", json=body, headers={"Idempotency-Key": "reply"}).json()[
            "job_id"
        ]
        == queued.json()["job_id"]
    )
    if answer == "ambiguous":
        assert review["reply_questions"] == ["Bạn muốn gross hay net?"]
        assert review["normalization_draft"] == original["normalization_draft"]
    else:
        assert review["normalization_draft"]["fields"][1]["amount_basis"] == "net"
        assert (
            client.post(
                path + "/decisions",
                json=original_decision,
                headers={"Idempotency-Key": "old-nonce"},
            ).status_code
            == 409
        )
        decision = dict(
            review_id=review["id"],
            nonce=review["nonce"],
            fingerprint=review["fingerprint"],
            decision=dict(type="MAPPING", draft=review["normalization_draft"]),
        )
        # Reply chỉ xác nhận net; người vận hành chọn UTC ở bước quyết định cuối.
        for field in decision["decision"]["draft"]["fields"]:
            if field["data_type"] == "date":
                field["timezone"] = "UTC"
        assert (
            client.post(
                path + "/decisions",
                json=decision,
                headers={"Idempotency-Key": "human-final-decision"},
            ).status_code
            == 200
        )
        drain(factory, worker)
        assert client.get(path).json()["state"] == "COMPLETED"
