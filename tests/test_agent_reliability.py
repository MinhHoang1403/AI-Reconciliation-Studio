"""Real PostgreSQL metadata and queue; provider failures are explicit MOCK cases."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from studio.contracts.agent import AgentIntent
from studio.database import CanonicalRow, DatasetRow, JobRow, MappingRow, MessageRow, TableRow, now
from studio.dataset_status import asks_processing_status, read_processing_status
from studio.errors import DomainError, request_failure_message
from test_agent_postgres import ask_agent, workflow_for
from test_assistant_postgres import conversation
from test_postgres import drain, pg, project  # noqa: F401
from test_reconciliation_postgres import prepare_pair

pytestmark = pytest.mark.integration


def test_chat_upload_prepares_reviews_from_profiles_without_provider_or_approval(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    def forbidden(*args, **kwargs):
        pytest.fail("Upload preparation must not call a provider")

    monkeypatch.setattr(agents, "model_call", forbidden)
    client, factory, worker = pg
    pid = project(client)
    response = client.post(
        "/api/agent/attachments",
        data={"project_id": pid},
        files=[
            (
                "files",
                (
                    "deposit.csv",
                    b"Payment ID,Date,Amount,Currency\n00001,2026-11-01,22.50,VND\n",
                    "text/csv",
                ),
            ),
            (
                "files",
                (
                    "receipts.csv",
                    b"Receipt ID,Date,Amount,Currency\n00002,2026-11-02,23.50,VND\n",
                    "text/csv",
                ),
            ),
        ],
        headers={"Idempotency-Key": "auto-prep-attachments"},
    )
    assert response.status_code == 202, response.text
    context = {"project_id": pid}
    request = dict(
        conversation_id=conversation(client, context),
        context=context,
        mode="AGENT",
        command="PREPARE_UPLOAD",
        text="Chuẩn bị dữ liệu vừa tải",
        dataset_ids=[item["id"] for item in response.json()["items"]],
    )
    headers = {"Idempotency-Key": "auto-prep-message"}
    accepted = client.post("/api/assistant/messages", json=request, headers=headers)
    assert accepted.status_code == 202, accepted.text
    drain(factory, worker)
    flow = workflow_for(client, factory, accepted.json()["job_id"])
    assert flow["state"] == "WAITING_REVIEW", flow
    assert flow["detail"]["model_calls"] == 0
    assert len([b for b in flow["detail"]["blocks"] if b["type"] == "table"]) == 2
    for review in flow["detail"]["reviews"]:
        draft = review["normalization_draft"]
        assert draft["grain"] == "unknown"
        assert not any(field["business_key"] for field in draft["fields"])
        assert draft["fields"][1]["timezone"] is None
        assert draft["fields"][1]["date_format"] == "%Y-%m-%d"
        assert draft["fields"][2]["currency"] == "VND"
        assert draft["fields"][2]["locale"] == "en-US"
        assert draft["fields"][2]["amount_basis"] is None
    assert len(flow["detail"]["reviews"]) == 2
    replay = client.post("/api/assistant/messages", json=request, headers=headers).json()
    assert replay["job_id"] == accepted.json()["job_id"] and replay["status"] == "SUCCEEDED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(JobRow).where(JobRow.kind == "agent_prepare")
            )
            == 2
        )


def test_prepared_chat_preview_and_count_need_no_provider_or_mapping(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.database import TraceRow

    def unavailable(*args):
        pytest.fail("An explicit prepared preview must not call a provider.")

    monkeypatch.setattr(agents, "interpret_requests", unavailable)
    client, factory, worker = pg
    pid = project(client)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid, "request_ai_mapping": "false"},
        files={
            "files": (
                "prepared.csv",
                b"ID,Date\n000123,2026-10-01\n000124,2026-10-02\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 202
    drain(factory, worker)
    context = dict(project_id=pid, dataset_id=response.json()["items"][0]["id"])
    cid = conversation(client, context)
    for index, question in enumerate(
        ("Xem dữ liệu tự chuẩn bị", "Đếm số dòng dữ liệu tự chuẩn bị")
    ):
        queued = ask_agent(client, context, cid, text=question, key=f"prepared-{index}")
        drain(factory, worker)
        flow = workflow_for(client, factory, queued["job_id"])
        assert flow["state"] == "COMPLETED" and flow["detail"]["model_calls"] == 0
        data = next(b["result"] for b in flow["detail"]["blocks"] if b["type"] == "table")
        assert data["source_kind"] == "PREPARED"
        assert data["verification_status"] == "RAW_UNVERIFIED"
        if index:
            assert data["rows"][0]["count_rows_0"] == 2
        else:
            assert data["total_count"] == 2
            assert data["rows"][0]["c1"] == "000123"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TraceRow)) == 0
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert not db.scalar(select(MappingRow.id).where(MappingRow.status == "APPROVED").limit(1))


def test_review_failure_then_valid_partial_reply_clears_current_error_keeps_history(
    pg,  # noqa: F811
    monkeypatch,
):
    import studio.agent_jobs as agents
    from studio.contracts.agent import NormalizationDraft, ReviewInterpretation
    from test_agent_postgres import mapping_fixture

    client, factory, worker = pg
    wf, _ = mapping_fixture(pg, monkeypatch)
    path = f"/api/agent/workflows/{wf['id']}"

    def fail(*args):
        raise DomainError("AI_INVALID_REVIEW", "Không đọc được bản xem trước.")

    monkeypatch.setattr(agents, "interpret_review_reply", fail)
    for number in range(2):
        review = client.get(path).json()["detail"]["reviews"][0]
        if number:
            draft = NormalizationDraft.model_validate(review["normalization_draft"])
            draft.fields[1].amount_basis = "net"
            monkeypatch.setattr(
                agents,
                "interpret_review_reply",
                lambda *args, draft=draft: ReviewInterpretation(
                    draft=draft, questions=["Cần xác nhận múi giờ."]
                ),
            )
        body = {k: review[k] for k in ("nonce", "fingerprint")}
        body.update(review_id=review["id"], text="Cột tiền là net.")
        queued = client.post(
            path + "/replies", json=body, headers={"Idempotency-Key": f"recovery-{number}"}
        )
        assert queued.status_code == 202, queued.text
        drain(factory, worker)
    after = client.get(path).json()
    assert after["detail"]["error_code"] is None
    assert after["state"] == "WAITING_REVIEW"
    assert after["detail"]["reviews"][0]["reply_questions"] == ["Cần xác nhận múi giờ."]
    history = client.get(f"/api/conversations/{wf['conversation_id']}").json()["items"]
    assert any(message["error_code"] == "AI_INVALID_REVIEW" for message in history)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0


def test_manual_mapping_approval_retries_return_one_immutable_receipt(pg, monkeypatch):  # noqa: F811
    from copy import deepcopy

    from studio.agent_preparation import approval_from_draft
    from studio.contracts import DatasetProfile
    from studio.contracts.agent import NormalizationDraft
    from test_agent_postgres import mapping_fixture

    client, factory, _ = pg
    wf, decision = mapping_fixture(pg, monkeypatch)
    draft = NormalizationDraft.model_validate(decision["decision"]["draft"])
    with factory() as db:
        table = db.get(TableRow, draft.table_id)
        body = approval_from_draft(draft, DatasetProfile.model_validate(table.profile), False)
        proposal_id = db.scalar(
            select(MappingRow.id)
            .where(MappingRow.source_table_id == table.id)
            .order_by(MappingRow.revision.desc())
        )
    path = f"/api/mappings/{proposal_id}/approve"
    headers = {"Idempotency-Key": "manual-approval-retry"}
    payload = body.model_dump(mode="json")
    first = client.post(path, json=payload, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(path, json=payload, headers=headers)
    assert second.status_code == 200 and first.json() == second.json()
    changed = deepcopy(payload)
    changed["schema_definition"]["name"] += " changed"
    assert client.post(path, json=changed, headers=headers).status_code == 409
    with factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
    # The original Chat card is fenced by the changed manual mapping fingerprint.
    assert (
        client.post(
            f"/api/agent/workflows/{wf['id']}/decisions",
            json=decision,
            headers={"Idempotency-Key": "stale-chat"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("blocked", [None, "expiry", "source", "viewer", "pending"])
def test_shared_review_draft_save_renew_and_stale_fences(pg, monkeypatch, blocked):  # noqa: F811
    from copy import deepcopy

    from studio.database import AgentWorkflowRow, MembershipRow
    from test_agent_postgres import mapping_fixture

    client, factory, _ = pg
    wf, decision = mapping_fixture(pg, monkeypatch)
    review = wf["detail"]["reviews"][0]
    token = {k: review[k] for k in ("id", "nonce", "fingerprint")}
    token["review_id"] = token.pop("id")
    draft = decision["decision"]["draft"]
    draft["fields"][1]["amount_basis"] = "net"
    path = f"/api/agent/workflows/{wf['id']}"
    with factory() as db:
        if blocked == "viewer":
            db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        elif blocked == "source":
            table = db.get(TableRow, review["resource_id"])
            table.profile = dict(table.profile, row_count=999)
        elif blocked in {"expiry", "pending"}:
            row = db.get(AgentWorkflowRow, wf["id"])
            detail = deepcopy(row.detail)
            if blocked == "expiry":
                detail["reviews"][0]["expires_at"] = (now() - timedelta(minutes=1)).isoformat()
            else:
                detail["reviews"][0]["pending_reply_job_id"] = "pending-reply"
            row.detail = detail
        db.commit()
    found = client.get(f"/api/agent/tables/{review['resource_id']}/mapping-reviews")
    assert found.status_code == 200 and found.json()[0]["id"] == wf["id"]
    assert client.get("/api/agent/tables/foreign-table/mapping-reviews").status_code == 404
    headers = {"Idempotency-Key": "save-draft"}
    saved = client.post(path + "/draft", json=dict(**token, draft=draft), headers=headers)
    if blocked:
        assert saved.status_code == (403 if blocked == "viewer" else 409), saved.text
    else:
        assert saved.status_code == 200, saved.text
        latest = saved.json()["detail"]["reviews"][0]
        assert latest["normalization_draft"] == draft
        assert latest["nonce"] != token["nonce"]
        assert (
            client.post(
                path + "/draft", json=dict(**token, draft=draft), headers=headers
            ).status_code
            == 409
        )
        retrieved = client.get(f"/api/agent/tables/{review['resource_id']}/mapping-reviews").json()
        assert retrieved[0]["detail"]["reviews"][0] == latest
        token = {k: latest[k] for k in ("nonce", "fingerprint")}
        token["review_id"] = latest["id"]
    renewed = client.post(path + "/renew-review", json=token, headers=headers)
    if blocked in {"source", "viewer", "pending"}:
        assert renewed.status_code == (403 if blocked == "viewer" else 409), renewed.text
    else:
        assert renewed.status_code == 200, renewed.text
        latest = renewed.json()["detail"]["reviews"][0]
        assert latest["nonce"] != token["nonce"] and latest["state"] == "OPEN"
        assert client.post(path + "/renew-review", json=token, headers=headers).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 0
        )


def test_mapping_preflight_is_scoped_read_only_and_rechecks_human_decisions(pg, monkeypatch):  # noqa: F811
    from copy import deepcopy

    from test_agent_postgres import mapping_fixture

    client, factory, worker = pg
    wf, decision = mapping_fixture(pg, monkeypatch)
    draft = decision["decision"]["draft"]
    with factory() as db:
        counts = (
            db.scalar(select(func.count()).select_from(MappingRow)),
            db.scalar(select(func.count()).select_from(CanonicalRow)),
        )
    preview = client.post("/api/agent/mapping-preflight", json=draft)
    assert preview.status_code == 200, preview.text
    assert preview.json()["preflight_ready"] and preview.json()["predicted_invalid_rows"] == 0
    invalid = deepcopy(draft)
    invalid["fields"][2]["date_format"] = "%d/%m/%Y"
    blocked = client.post("/api/agent/mapping-preflight", json=invalid)
    assert blocked.status_code == 200 and not blocked.json()["preflight_ready"]
    invalid["table_id"] = "foreign-table"
    assert client.post("/api/agent/mapping-preflight", json=invalid).status_code == 404
    bad_decision = deepcopy(decision)
    bad_decision["decision"]["draft"]["fields"][2]["timezone"] = None
    failed = client.post(
        "/api/agent/workflows/" + wf["id"] + "/decisions",
        json=bad_decision,
        headers={"Idempotency-Key": "missing-timezone"},
    )
    assert failed.status_code == 422 and failed.json()["code"] == "MAPPING_PREFLIGHT_REQUIRED"
    with factory() as db:
        assert counts == (
            db.scalar(select(func.count()).select_from(MappingRow)),
            db.scalar(select(func.count()).select_from(CanonicalRow)),
        )


@pytest.mark.parametrize(
    "goal",
    [
        "2 bộ dữ liệu trên đã được chuẩn hoá chưa",
        "Hai file này chuẩn hóa xong chưa?",
        "Dữ liệu A và B đã xử lý xong chưa?",
        "Tôi có thể đối soát hai file vừa tải chưa?",
        "File nào chưa chuẩn hóa?",
        "Kiểm tra trạng thái xử lý dữ liệu.",
        "Hai nguồn đã sẵn sàng chưa?",
        "Dữ liệu vừa tải đã dùng được chưa?",
        "Có cần xác nhận cột gì nữa không?",
    ],
)
def test_status_questions_are_read_only_variants(goal):
    assert asks_processing_status(goal)


@pytest.mark.parametrize(
    "goal",
    [
        "Hãy chuẩn hóa hai file đã tải",
        "Chuẩn hóa dữ liệu giúp tôi",
        "Chạy đối soát hai nguồn đã chuẩn hóa",
        "Dữ liệu đã chuẩn hóa, sau đó xuất báo cáo",
        "Tự động duyệt các cột đã chuẩn hóa",
        "Tổng số tiền đã thanh toán là bao nhiêu?",
    ],
)
def test_status_shortcut_never_hijacks_actions_or_analytics(goal):
    assert not asks_processing_status(goal)


@pytest.mark.parametrize(
    "goal",
    [
        "Đề xuất cách chuẩn hóa hai nguồn dữ liệu. Hãy hỏi tôi nếu có cột hoặc ý nghĩa chưa rõ.",
        "Chuẩn bị để chuẩn hóa dữ liệu, hỏi nếu chưa rõ.",
        "Tôi muốn thiết lập chuẩn hóa hai file chưa xử lý.",
        "Hãy tạo đề xuất ghép cột cho dữ liệu chưa chuẩn hóa.",
        "Làm sạch và chuẩn hóa dữ liệu nếu đã đọc xong.",
        "Tiếp tục chuẩn hóa nguồn đã tải và hỏi tôi nếu chưa đủ thông tin.",
    ],
)
def test_conditional_words_in_an_instruction_are_not_processing_status_questions(goal):
    assert not asks_processing_status(goal)


def test_normalization_proposal_with_conditional_question_reaches_the_action_router(
    pg,  # noqa: F811
    monkeypatch,
):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid, _ = prepare_pair(pg)
    calls = []

    def interpret(*args):
        calls.append(True)
        return [AgentIntent(intent="PREPARE_NORMALIZATION")]

    monkeypatch.setattr(agents, "interpret_requests", interpret)
    ctx = dict(project_id=pid)
    cid = conversation(client, ctx)
    result = ask_agent(
        client,
        ctx,
        cid,
        text=(
            "Đề xuất cách chuẩn hóa hai nguồn dữ liệu. Hãy hỏi tôi nếu có cột hoặc ý nghĩa chưa rõ."
        ),
    )
    drain(factory, worker)
    wf = workflow_for(client, factory, result["job_id"])
    assert calls == [True]
    assert wf["detail"]["intent"]["intent"] == "PREPARE_NORMALIZATION"
    assert wf["state"] == "COMPLETED"
    assert len([b for b in wf["detail"]["blocks"] if b["type"] == "dataset_summary"]) == 2


@pytest.mark.parametrize(
    "variant", ["READY", "PARTIAL", "FAILED", "STALE", "MAPPED", "MAPPING_REVIEW", "PARSED"]
)
def test_status_reads_current_metadata_without_verified_run_or_model(pg, monkeypatch, variant):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid, _ = prepare_pair(pg)
    with factory() as db:
        canonical = db.scalar(select(CanonicalRow).order_by(CanonicalRow.id))
        table = db.get(TableRow, canonical.source_table_id)
        if variant in {"PARTIAL", "FAILED"}:
            canonical.contract = dict(canonical.contract, quality_status=variant)
        elif variant == "STALE":
            canonical.stale = True
        elif variant in {"MAPPED", "MAPPING_REVIEW", "PARSED"}:
            db.delete(canonical)
            if variant != "MAPPED":
                mapping = db.get(MappingRow, table.active_mapping_id)
                mapping.status = "PROPOSED" if variant == "MAPPING_REVIEW" else "REJECTED"
                table.active_mapping_id = None
                if variant == "PARSED":
                    for draft in db.scalars(
                        select(MappingRow).where(MappingRow.source_table_id == table.id)
                    ):
                        draft.status = "REJECTED"
        db.commit()

    def forbidden(*args):
        raise AssertionError("Metadata question must not call a provider")

    monkeypatch.setattr(agents, "interpret_requests", forbidden)
    ctx = dict(project_id=pid)
    cid = conversation(client, ctx)
    response = ask_agent(client, ctx, cid, text="2 bộ dữ liệu trên đã được chuẩn hoá chưa")
    drain(factory, worker)
    wf = workflow_for(client, factory, response["job_id"])
    assert wf["state"] == "COMPLETED" and wf["detail"]["model_calls"] == 0
    assert wf["detail"]["intent"]["intent"] == "CHECK_DATASET_STATUS"
    from studio.access import Actor
    from studio.contracts.assistant import AssistantContext

    with factory() as db:
        statuses = read_processing_status(
            db, Actor("test-owner", "demo", "owner"), AssistantContext(**ctx), []
        )
        assert variant in {s.state for s in statuses}
        assert (
            db.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.job_id == response["job_id"], MessageRow.role == "assistant")
            )
            == 1
        )
    text = " ".join(b["text"] for b in wf["detail"]["blocks"])
    assert "Đây là trạng thái chuẩn hóa" in text
    assert "đã đối soát" not in text.lower()


@pytest.mark.parametrize("count", [0, 1, 3, 6])
def test_status_empty_uploaded_and_ambiguous_sources_have_a_visible_outcome(pg, count):  # noqa: F811
    client, factory, worker = pg
    pid = project(client)
    with factory() as db:
        for i in range(count):
            db.add(
                DatasetRow(
                    workspace_id="demo",
                    project_id=pid,
                    owner_id="test-owner",
                    name=f"TEST source {i}.csv",
                    sha256=f"{i:064x}",
                    parse_signature="test",
                )
            )
        db.commit()
    ctx = dict(project_id=pid)
    cid = conversation(client, ctx)
    response = ask_agent(client, ctx, cid, text="Hai file này chuẩn hóa xong chưa?")
    drain(factory, worker)
    wf = workflow_for(client, factory, response["job_id"])
    assert wf["state"] == ("COMPLETED" if count == 0 else "WAITING_REVIEW")
    if count:
        assert wf["detail"]["reviews"][0]["kind"] == "CLARIFICATION"
    else:
        assert wf["detail"]["blocks"]


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Hai bộ dữ liệu đã được chuẩn hóa chưa?", "WAITING_REVIEW"),
        ("Nguồn đang xem đã được chuẩn hóa chưa?", "COMPLETED"),
    ],
)
def test_status_respects_single_source_scope_and_never_answers_two_with_one(pg, question, expected):  # noqa: F811
    client, factory, worker = pg
    pid, _ = prepare_pair(pg)
    with factory() as db:
        source = db.scalar(select(DatasetRow).where(DatasetRow.project_id == pid))
        did = source.id
    ctx = dict(project_id=pid, dataset_id=did)
    cid = conversation(client, ctx)
    result = ask_agent(client, ctx, cid, text=question)
    drain(factory, worker)
    wf = workflow_for(client, factory, result["job_id"])
    assert wf["state"] == expected and wf["detail"]["model_calls"] == 0
    if expected == "WAITING_REVIEW":
        assert wf["detail"]["reviews"][0]["kind"] == "CLARIFICATION"
        assert "1 nguồn" in wf["detail"]["reviews"][0]["question"]
        assert not wf["detail"]["blocks"]
    else:
        assert (
            len(
                [
                    b
                    for b in wf["detail"]["blocks"]
                    if b["type"] == "progress" and "Đã chuẩn hóa;" in b["text"]
                ]
            )
            == 1
        )


@pytest.mark.parametrize(
    "code",
    [
        "INSUFFICIENT_EVIDENCE",
        "INPUT_AMBIGUOUS",
        "QUERY_FIELD_INVALID",
        "QUERY_METRIC_AMBIGUOUS",
        "AI_INVALID_SOURCE",
        "STALE_CONTEXT",
        "AUTH_REQUIRED",
        "LOCAL_DEMO_NOT_VERIFIED",
        "GEMINI_RATE_LIMITED",
        "GEMINI_UNAVAILABLE",
        "AI_DELIVERY_UNKNOWN",
    ],
)
def test_terminal_failure_is_persisted_once_and_survives_reload(pg, monkeypatch, code):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    ctx = dict(project_id=project(client))
    cid = conversation(client, ctx)
    calls = []

    def fail(*args):
        calls.append(code)
        raise DomainError(code, "DO NOT PERSIST private provider body")

    monkeypatch.setattr(agents, "interpret_requests", fail)
    response = ask_agent(client, ctx, cid, text="Cho biết tình hình", key="failure")
    drain(factory, worker)
    messages = client.get(f"/api/conversations/{cid}").json()["items"]
    # The two semantic errors already have a legitimate clarification path.
    if code == "INPUT_AMBIGUOUS":
        assert workflow_for(client, factory, response["job_id"])["state"] == "WAITING_REVIEW"
    else:
        reply = next(m for m in messages if m["role"] == "assistant")
        assert reply["text"] == request_failure_message(code)
        assert reply["job_status"] in {"FAILED", "BLOCKED"} and reply["error_code"] == code
        assert "private" not in str(messages)
        again = ask_agent(client, ctx, cid, text="Cho biết tình hình", key="failure")
        assert again["job_id"] == response["job_id"]
        drain(factory, worker)
        assert client.get(f"/api/conversations/{cid}").json()["items"] == messages
    assert calls == [code]


def test_exhausted_worker_lease_publishes_terminal_reply(pg):  # noqa: F811
    client, factory, worker = pg
    ctx = dict(project_id=project(client))
    cid = conversation(client, ctx)
    response = ask_agent(client, ctx, cid, text="Kiểm tra thông tin")
    with factory() as db:
        job = db.get(JobRow, response["job_id"])
        job.status, job.attempts = "RUNNING", 3
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    drain(factory, worker)
    messages = client.get(f"/api/conversations/{cid}").json()["items"]
    assert len(messages) == 2
    assert messages[-1]["error_code"] == "JOB_RETRY_EXHAUSTED"


def test_summary_without_run_asks_for_evidence_instead_of_failing(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    ctx = dict(project_id=project(client))
    cid = conversation(client, ctx)
    monkeypatch.setattr(
        agents, "interpret_requests", lambda *args: [AgentIntent(intent="SUMMARIZE_RESULTS")]
    )
    response = ask_agent(client, ctx, cid, text="Tóm tắt kết quả đối soát")
    drain(factory, worker)
    wf = workflow_for(client, factory, response["job_id"])
    assert wf["state"] == "WAITING_REVIEW"
    assert wf["detail"]["reviews"][0]["kind"] == "CLARIFICATION"
    assert not wf["detail"]["blocks"]


def test_status_reader_preserves_project_isolation_and_viewer_read_access(pg):  # noqa: F811
    from studio.access import Actor
    from studio.contracts.assistant import AssistantContext

    client, factory, _ = pg
    pid, _ = prepare_pair(pg)
    other = project(client, "Other isolated project")
    with factory() as db:
        dataset = db.scalar(select(DatasetRow).where(DatasetRow.project_id == pid))
        viewer = Actor("test-owner", "demo", "viewer")
        assert read_processing_status(db, viewer, AssistantContext(project_id=pid), [])
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            read_processing_status(db, viewer, AssistantContext(project_id=other), [dataset.id])
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            read_processing_status(
                db,
                Actor("foreign", "another-workspace", "owner"),
                AssistantContext(project_id=pid),
                [],
            )


def test_status_reader_does_not_reuse_previous_version_or_old_normalization_engine(pg):  # noqa: F811
    from studio.access import Actor
    from studio.contracts.assistant import AssistantContext
    from studio.database import VersionRow

    client, factory, _ = pg
    pid, _ = prepare_pair(pg)
    actor = Actor("test-owner", "demo", "owner")
    ctx = AssistantContext(project_id=pid)
    with factory() as db:
        canonical = db.scalar(select(CanonicalRow))
        canonical.normalization_revision = "historical-engine"
        db.commit()
        assert "STALE" in {s.state for s in read_processing_status(db, actor, ctx, [])}
        dataset = db.scalar(select(DatasetRow).where(DatasetRow.project_id == pid))
        version = db.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        db.add(
            VersionRow(
                dataset_id=dataset.id,
                revision=version.revision + 1,
                parser_revision="test-next-parser",
                parse_config={},
            )
        )
        db.commit()
        current = read_processing_status(db, actor, ctx, [dataset.id])
        assert len(current) == 1 and current[0].state == "UPLOADED"
        assert current[0].canonical_id is None


def test_exhausted_parse_lease_marks_source_failed_and_reports_real_status(pg):  # noqa: F811
    from studio.access import Actor
    from studio.contracts.assistant import AssistantContext
    from test_postgres import upload

    client, factory, worker = pg
    pid = project(client)
    source = upload(client, pid)
    with factory() as db:
        job = db.scalar(select(JobRow).where(JobRow.kind == "parse"))
        job.status, job.attempts = "RUNNING", 3
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    drain(factory, worker)
    with factory() as db:
        assert db.get(DatasetRow, source["id"]).status == "FAILED"
        status = read_processing_status(
            db,
            Actor("test-owner", "demo", "owner"),
            AssistantContext(project_id=pid),
            [source["id"]],
        )
        assert len(status) == 1 and status[0].state == "PARSE_FAILED"


def test_exhausted_reconciliation_lease_never_leaves_a_published_run_running(pg):  # noqa: F811
    from studio.database import RunRow
    from test_reconciliation_postgres import create_approved_run

    client, factory, worker = pg
    _, _, _, created = create_approved_run(pg)
    with factory() as db:
        job = db.scalar(select(JobRow).where(JobRow.kind == "reconcile"))
        job.status, job.attempts = "RUNNING", 3
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    drain(factory, worker)
    with factory() as db:
        run = db.get(RunRow, created["run_id"])
        assert run.status == "BLOCKED" and run.metric_snapshot is None


@pytest.mark.parametrize(
    "goal",
    [
        "Cho tôi xem trước cả hai nguồn giao nhận",
        "Xem trước hai file giao nhận",
        "Kiểm tra các file vừa tải lên",
        "Khám phá tất cả nguồn giao nhận",
    ],
)
def test_plain_multi_source_preview_is_one_request_without_model_or_financial_claims(
    pg,  # noqa: F811
    monkeypatch,
    goal,
):  # noqa: F811
    import studio.agent_jobs as agents

    client, factory, worker = pg
    pid, _ = prepare_pair(pg)
    # Names are metadata, not new data semantics or business rules.
    with factory() as db:
        for i, dataset in enumerate(
            db.scalars(select(DatasetRow).where(DatasetRow.project_id == pid))
        ):
            dataset.name = f"Giao nhận {'A' if i == 0 else 'B'}.csv"
        db.commit()

    def forbidden(*args):
        raise AssertionError("An unfiltered source preview must not call the model")

    monkeypatch.setattr(agents, "interpret_requests", forbidden)
    ctx = dict(project_id=pid)
    cid = conversation(client, ctx)
    response = ask_agent(client, ctx, cid, text=goal)
    drain(factory, worker)
    wf = workflow_for(client, factory, response["job_id"])
    assert wf["state"] == "COMPLETED" and wf["detail"]["model_calls"] == 0
    assert wf["detail"]["intent"]["intent"] == "EXPLORE_DATA"
    assert len(wf["detail"]["intent"]["dataset_ids"]) == 2
    blocks = [b for b in wf["detail"]["blocks"] if b["type"] == "table"]
    assert len(blocks) == 2 and all(b["result"]["source_kind"] == "RAW_PREVIEW" for b in blocks)
