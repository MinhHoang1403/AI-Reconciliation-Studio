"""Real PostgreSQL metadata and queue; provider failures are explicit MOCK cases."""

from datetime import timedelta
from pathlib import Path

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


@pytest.mark.parametrize("encoding", ["legacy", "transient"])
def test_legacy_clarification_decision_replay_preserves_digest_and_creates_no_job(
    pg,  # noqa: F811
    monkeypatch,
    encoding,
):
    """Real API/DB replay of a pre-export-scope decision; initial interpretation is MOCK."""
    from copy import deepcopy

    import studio.agent_jobs as agents
    from studio.agent_workflows import digest
    from studio.database import AgentWorkflowRow

    client, factory, worker = pg
    pid = project(client)
    context = dict(project_id=pid)
    cid = conversation(client, context)
    monkeypatch.setattr(
        agents,
        "interpret_requests",
        lambda *args: [AgentIntent(intent="CLARIFY", questions=["Bạn muốn tra cứu gì?"])],
    )
    first = ask_agent(client, context, cid, text="Tra cứu thông tin")
    drain(factory, worker)
    flow = workflow_for(client, factory, first["job_id"])
    review = flow["detail"]["reviews"][0]
    legacy_intent = AgentIntent(
        intent="UNSUPPORTED", questions=["Không thực hiện tác vụ này."]
    ).model_dump(mode="json", exclude={"export_scope"})
    body = {k: review[k] for k in ("nonce", "fingerprint")}
    body.update(review_id=review["id"], decision=dict(type="CLARIFICATION", intent=legacy_intent))
    path = f"/api/agent/workflows/{flow['id']}/decisions"
    first_decision = client.post(path, json=body, headers={"Idempotency-Key": "legacy-first"})
    assert first_decision.status_code == 200, first_decision.text
    with factory() as db:
        row = db.get(AgentWorkflowRow, flow["id"])
        detail = deepcopy(row.detail)
        stored = next(r for r in detail["reviews"] if r["id"] == review["id"])
        assert stored["state"] == "DECIDED"
        historical = deepcopy(body["decision"])
        if encoding == "transient":
            historical["intent"]["export_scope"] = None
        stored["decision_sha256"] = digest(historical)
        row.detail = detail
        before = db.scalar(select(func.count()).select_from(JobRow))
        db.commit()
    replay = client.post(path, json=body, headers={"Idempotency-Key": "legacy-replay"})
    assert replay.status_code == 200, replay.text
    changed = deepcopy(body)
    changed["decision"]["intent"]["questions"] = ["Một quyết định khác."]
    assert (
        client.post(path, json=changed, headers={"Idempotency-Key": "legacy-conflict"}).status_code
        == 409
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(JobRow)) == before


@pytest.mark.parametrize(
    "code",
    ["OLLAMA_UNAVAILABLE", "OLLAMA_MODEL_MISSING", "OLLAMA_NOT_CONFIGURED", "GEMINI_UNAVAILABLE"],
)
def test_local_provider_failure_blocks_job_without_retry_or_fake_success(pg, monkeypatch, code):  # noqa: F811
    """Real queue/attempt metadata; provider error itself is explicitly synthetic."""
    from studio.database import AttemptRow
    from studio.repository import enqueue_job

    client, factory, worker = pg
    pid = project(client)
    with factory() as db:
        job = enqueue_job(db, "demo", pid, "mapping", "provider-error-probe", {})
        job_id = job.id
        db.commit()
    calls = []

    def fail_once(*args):
        calls.append(code)
        raise DomainError(code, "Synthetic provider failure", 503)

    monkeypatch.setattr(worker, "_mapping", fail_once)
    with factory() as db:
        claimed = worker.claim_job(db)
    assert claimed is not None and claimed[0] == job_id
    worker.process_job(*claimed)
    with factory() as db:
        job = db.get(JobRow, job_id)
        attempt = db.scalar(select(AttemptRow).where(AttemptRow.job_id == job_id))
        assert job.status == attempt.status == "BLOCKED"
        assert job.error_code == attempt.error_code == code
        assert job.result is None and job.attempts == 1 and job.lease_until is None
        job.available_at = now() - timedelta(seconds=1)
        db.commit()
        assert worker.claim_job(db) is None
    assert calls == [code]


@pytest.mark.parametrize(
    "historical,blocked",
    [
        (False, None),
        (True, None),
        (True, "viewer"),
        (True, "cancelled"),
        (True, "deleted"),
        (True, "stale"),
    ],
)
def test_manual_normalization_resumes_existing_chat_reviews_without_approving_again(
    pg,  # noqa: F811
    monkeypatch,
    historical,
    blocked,
):
    import studio.agent_jobs as agents
    import studio.agent_workflows as workflows
    from test_postgres import approve

    def forbidden(*args, **kwargs):
        pytest.fail("Adopting already approved canonical data must not call a model")

    monkeypatch.setattr(agents, "model_call", forbidden)
    client, factory, worker = pg
    pid = project(client)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid, "request_ai_mapping": "false"},
        files=[
            (
                "files",
                (
                    f"manual-{index}.csv",
                    f"Order ID,Gross amount\n000{index},12.50\n".encode(),
                    "text/csv",
                ),
            )
            for index in (1, 2)
        ],
    )
    assert response.status_code == 202
    datasets = response.json()["items"]
    drain(factory, worker)
    context = {"project_id": pid}
    cid = conversation(client, context)
    queued = client.post(
        "/api/assistant/messages",
        json={
            "conversation_id": cid,
            "context": context,
            "mode": "AGENT",
            "command": "PREPARE_UPLOAD",
            "dataset_ids": [item["id"] for item in datasets],
            "text": "Chuẩn bị các tệp vừa tải",
        },
        headers={"Idempotency-Key": "manual-preparation"},
    )
    assert queued.status_code == 202
    drain(factory, worker)
    initial = workflow_for(client, factory, queued.json()["job_id"])
    assert initial["state"] == "WAITING_REVIEW"
    path = f"/api/agent/workflows/{initial['id']}"
    if historical:
        original = workflows.resume_prepared_reviews
        monkeypatch.setattr(workflows, "resume_prepared_reviews", lambda *args, **kwargs: None)
    for index, dataset in enumerate(datasets):
        (table,) = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"]
        approved, _ = approve(client, table["id"])
        result = client.post(
            f"/api/datasets/{dataset['id']}/normalize",
            json={"mapping_id": approved["id"]},
            headers={"Idempotency-Key": f"manual-normalize-{index}"},
        )
        assert result.status_code == 202
        drain(factory, worker)
        current = client.get(path).json()
        if not historical and index == 0:
            assert current["state"] == "WAITING_REVIEW"
            assert sorted(r["state"] for r in current["detail"]["reviews"]) == [
                "INVALIDATED",
                "OPEN",
            ]
    if historical:
        assert current["state"] == "WAITING_REVIEW"
        monkeypatch.setattr(workflows, "resume_prepared_reviews", original)
        with factory() as db:
            from studio.database import AgentWorkflowRow, ConversationRow, MembershipRow

            row = db.get(AgentWorkflowRow, initial["id"])
            if blocked == "viewer":
                db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
            elif blocked == "cancelled":
                row.state = "CANCELLED_BEFORE_NEXT_STEP"
            elif blocked == "deleted":
                db.get(ConversationRow, row.conversation_id).deleted_at = now()
            elif blocked == "stale":
                for canonical in db.scalars(select(CanonicalRow)):
                    canonical.stale = True
            before_jobs = db.scalar(select(func.count()).select_from(JobRow))
            original(db)
            original(db)
            if blocked:
                assert db.scalar(select(func.count()).select_from(JobRow)) == before_jobs
            db.commit()
        if blocked:
            with factory() as db:
                row = db.get(AgentWorkflowRow, initial["id"])
                assert row.state == (
                    "CANCELLED_BEFORE_NEXT_STEP" if blocked == "cancelled" else "WAITING_REVIEW"
                )
                assert {r["state"] for r in row.detail["reviews"]} == {"OPEN"}
            return
        drain(factory, worker)
        current = client.get(path).json()
    assert current["state"] == "COMPLETED"
    assert {r["state"] for r in current["detail"]["reviews"]} == {"INVALIDATED"}
    assert [r["normalization_draft"] for r in current["detail"]["reviews"]] == [
        r["normalization_draft"] for r in initial["detail"]["reviews"]
    ]
    assert (
        len([block for block in current["detail"]["blocks"] if block["type"] == "dataset_summary"])
        == 2
    )
    with factory() as db:
        from studio.database import AuditRow

        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 2
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 2
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(
                    AuditRow.action == "AGENT_REVIEW_INVALIDATED",
                    AuditRow.actor_id == "system",
                )
            )
            == 2
        )


def test_historical_refresh_does_not_prepare_sources_added_after_the_original_review(
    pg,  # noqa: F811
    monkeypatch,
):
    import studio.agent_jobs as agents
    import studio.agent_workflows as workflows
    from studio.agent_preparation import approval_from_draft
    from studio.contracts import DatasetProfile
    from studio.contracts.agent import NormalizationDraft
    from studio.database import VersionRow
    from test_agent_postgres import mapping_fixture

    client, factory, worker = pg
    initial, decision = mapping_fixture(pg, monkeypatch)
    review = initial["detail"]["reviews"][0]
    table_id = review["resource_id"]
    mappings = client.get(f"/api/tables/{table_id}/mappings").json()["items"]
    with factory() as db:
        table = db.get(TableRow, table_id)
        version = db.get(VersionRow, table.dataset_version_id)
        dataset_id = version.dataset_id
        approval = approval_from_draft(
            NormalizationDraft.model_validate(decision["decision"]["draft"]),
            DatasetProfile.model_validate(table.profile),
            True,
        )
    approved = client.post(
        f"/api/mappings/{mappings[0]['id']}/approve",
        json=approval.model_dump(mode="json"),
    )
    assert approved.status_code == 200
    original = workflows.resume_prepared_reviews
    monkeypatch.setattr(workflows, "resume_prepared_reviews", lambda *args, **kwargs: None)
    assert (
        client.post(
            f"/api/datasets/{dataset_id}/normalize",
            json={"mapping_id": approved.json()["id"]},
            headers={"Idempotency-Key": "historical-manual"},
        ).status_code
        == 202
    )
    drain(factory, worker)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": initial["context"]["project_id"], "request_ai_mapping": "false"},
        files={"files": ("later.csv", b"Unknown code,Total\n0009,18.50\n", "text/csv")},
    )
    assert response.status_code == 202
    drain(factory, worker)
    monkeypatch.setattr(workflows, "resume_prepared_reviews", original)
    monkeypatch.setattr(
        agents, "model_call", lambda *args, **kwargs: pytest.fail("Unexpected model call")
    )
    with factory() as db:
        original(db)
        db.commit()
    drain(factory, worker)
    current = client.get(f"/api/agent/workflows/{initial['id']}").json()
    assert current["state"] == "COMPLETED"
    assert current["detail"]["dataset_ids"] == [dataset_id]
    assert current["detail"]["reviews"][0]["state"] == "INVALIDATED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
            )
            == 1
        )


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
    decisions = []
    for review in flow["detail"]["reviews"]:
        draft = review["normalization_draft"]
        draft.update(entity_kind="cash", grain="cash_event")
        draft["fields"][0]["business_key"] = True
        draft["fields"][1]["timezone"] = "UTC"
        draft["fields"][2].update(amount_basis="gross", semantic_metric="received_cash")
        decisions.append(
            dict(
                review_id=review["id"],
                nonce=review["nonce"],
                fingerprint=review["fingerprint"],
                decision={"type": "MAPPING", "draft": draft},
            )
        )
    batch = f"/api/agent/workflows/{flow['id']}/decisions/batch"
    bad = sorted(decisions, key=lambda item: item["decision"]["draft"]["table_id"])
    bad[-1] = {**bad[-1], "nonce": "0" * 32}
    assert client.post(batch, json={"decisions": bad}, headers=headers).status_code == 409
    with factory() as db:
        assert not db.scalar(select(MappingRow.id).where(MappingRow.status == "APPROVED"))
    assert client.post(batch, json={"decisions": decisions}, headers=headers).status_code == 200
    drain(factory, worker)
    assert client.post(batch, json={"decisions": decisions}, headers=headers).status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 2
        assert (
            db.scalar(
                select(func.count()).select_from(MappingRow).where(MappingRow.status == "APPROVED")
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
                b"ID,Date\n000123,2026-10-01\n000124,2026-02-29\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 202
    drain(factory, worker)
    context = dict(project_id=pid, dataset_id=response.json()["items"][0]["id"])
    cid = conversation(client, context)
    for index, question in enumerate(
        (
            "Xem dữ liệu tự chuẩn bị",
            "Đếm số dòng dữ liệu tự chuẩn bị",
            "Những dòng lỗi ngày tháng nằm ở đâu?",
            "Có bao nhiêu bản ghi có ngày không hợp lệ?",
        )
    ):
        queued = ask_agent(client, context, cid, text=question, key=f"prepared-{index}")
        drain(factory, worker)
        flow = workflow_for(client, factory, queued["job_id"])
        assert flow["state"] == "COMPLETED" and flow["detail"]["model_calls"] == 0
        data = next(b["result"] for b in flow["detail"]["blocks"] if b["type"] == "table")
        assert data["source_kind"] == ("PREPARED_FINDINGS" if index >= 2 else "PREPARED")
        assert data["verification_status"] == "RAW_UNVERIFIED"
        if index in {1, 3}:
            assert data["rows"][0]["count_rows_0"] == (2 if index == 1 else 1)
        elif index == 2:
            row = data["rows"][0]
            assert (row["date_findings"], row["c1"], row["c2"]) == (
                "Date",
                "000124",
                "2026-02-29",
            )
            assert data["total_count"] == 1 and row["source_provenance"][0]["row"] == 3
        else:
            assert data["total_count"] == 2
            assert data["rows"][0]["c1"] == "000123"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TraceRow)) == 0
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert not db.scalar(select(MappingRow.id).where(MappingRow.status == "APPROVED").limit(1))


def test_chat_scope_confirmation_builds_a_new_preview_and_never_approves(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.contracts.reconciliation import PlanningRequest
    from studio.database import ReconciliationContractRow, RunRow

    def forbidden(*args, **kwargs):
        pytest.fail("An exact source pair with a typed scope needs no provider")

    monkeypatch.setattr(agents, "model_call", forbidden)
    client, factory, worker = pg
    pid, plan = prepare_pair(pg)
    context = {"project_id": pid}
    message = ask_agent(
        client,
        context,
        conversation(client, context),
        text="Đối soát “shipments.csv” với “delivery-confirmations.csv”",
    )
    drain(factory, worker)
    workflow = workflow_for(client, factory, message["job_id"])
    original = workflow["detail"]["reviews"][0]
    assert workflow["state"] == "WAITING_REVIEW" and original["plan"] is None
    path = f"/api/agent/workflows/{workflow['id']}/draft"
    scope = PlanningRequest.from_plan(plan).model_dump(mode="json")
    body = dict(
        review_id=original["id"],
        nonce=original["nonce"],
        fingerprint=original["fingerprint"],
        check_planning_scope=True,
        planning_request=scope,
    )
    headers = {"Idempotency-Key": "scope-check"}
    wrong = {
        **body,
        "planning_request": {**scope, "right": {**scope["right"], "canonical_id": "unknown"}},
    }
    assert client.post(path, json=wrong, headers=headers).status_code == 422
    assert client.post(path, json=body, headers=headers).status_code == 200
    drain(factory, worker)
    workflow = client.get(f"/api/agent/workflows/{workflow['id']}").json()
    old, new = workflow["detail"]["reviews"]
    assert old["state"] == "INVALIDATED" and new["state"] == "OPEN"
    assert new["plan"]["join_keys"] == [
        {"left": "carrier", "right": "carrier"},
        {"left": "tracking_id", "right": "tracking_id"},
    ]
    assert new["planning_candidates"][0]["overlap"] == 2
    assert client.post(path, json=body, headers=headers).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 0
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0


@pytest.mark.parametrize("route", ["NATIVE", "MODEL", "REPLY", "DECISION"])
def test_chat_exports_the_displayed_verified_query_and_keeps_full_snapshot(pg, monkeypatch, route):  # noqa: F811
    from io import BytesIO

    import studio.agent_jobs as agents
    from openpyxl import load_workbook
    from test_reconciliation_postgres import create_approved_run

    def forbidden(*args, **kwargs):
        pytest.fail("Exporting the displayed verified query must not call a provider")

    original_model_call = agents.model_call
    monkeypatch.setattr(agents, "model_call", forbidden)
    client, factory, worker = pg
    pid, _, _, run = create_approved_run(pg)
    drain(factory, worker)
    context = {"project_id": pid, "run_id": run["run_id"]}
    cid = conversation(client, context)
    message = ask_agent(client, context, cid, text="Cho tôi xem một nhóm lệch tiền lớn nhất")
    drain(factory, worker)
    workflow = workflow_for(client, factory, message["job_id"])
    table = next(
        block["result"] for block in workflow["detail"]["blocks"] if block["type"] == "table"
    )
    assert len(table["rows"]) == 1 and table["rows"][0]["delta"] == "2.75"

    initial_goal = "Bạn tạo tệp Excel giữ nguyên các dòng trên được không?"
    candidate = AgentIntent(
        intent="EXPORT_RESULT",
        run_id=run["run_id"],
        export_format="xlsx",
        export_scope="DISPLAYED_QUERY",
    )
    if route != "NATIVE":
        monkeypatch.setattr(agents, "model_call", original_model_call)
        monkeypatch.setattr(
            agents,
            "interpret_requests",
            lambda _provider, goals, *_: [
                AgentIntent(intent="CLARIFY", questions=["Bạn muốn xuất bảng nào?"])
                if route in {"REPLY", "DECISION"} and goals == [initial_goal]
                else candidate
            ],
        )

    def export(key):
        text = "Xuất danh sách trên" if route == "NATIVE" else initial_goal
        message = ask_agent(client, context, cid, text=text, key=key)
        drain(factory, worker)
        flow = workflow_for(client, factory, message["job_id"])
        if route in {"REPLY", "DECISION"}:
            assert flow["state"] == "WAITING_REVIEW"
            review = flow["detail"]["reviews"][0]
            body = {k: review[k] for k in ("nonce", "fingerprint")}
            body["review_id"] = review["id"]
            path = f"/api/agent/workflows/{flow['id']}"
            if route == "REPLY":
                body["text"] = "Tôi muốn file Excel của bảng đó"
                response = client.post(
                    path + "/replies", json=body, headers={"Idempotency-Key": key + "-reply"}
                )
                assert response.status_code == 202, response.text
            else:
                body["decision"] = dict(
                    type="CLARIFICATION", intent=candidate.model_dump(mode="json")
                )
                response = client.post(
                    path + "/decisions", json=body, headers={"Idempotency-Key": key + "-decision"}
                )
                assert response.status_code == 200, response.text
            drain(factory, worker)
            flow = client.get(path).json()
            if route == "DECISION":
                replay = client.post(
                    path + "/decisions", json=body, headers={"Idempotency-Key": key + "-replay"}
                )
                assert replay.status_code == 200, replay.text
                from copy import deepcopy

                changed = deepcopy(body)
                changed["decision"]["intent"]["export_scope"] = "FULL_RUN"
                assert (
                    client.post(
                        path + "/decisions",
                        json=changed,
                        headers={"Idempotency-Key": key + "-different-scope"},
                    ).status_code
                    == 409
                )
        # Provider output is explicitly MOCK; no reservation/HTTP inference.
        assert flow["state"] == "COMPLETED" and flow["detail"]["model_calls"] == 0
        block = next(block for block in flow["detail"]["blocks"] if block["type"] == "download")
        assert block["displayed_query"] is True
        return block["export_id"]

    export_id = export("filtered-page")
    assert export("filtered-page-again") == export_id
    downloaded = client.get(f"/api/exports/{export_id}/download")
    assert downloaded.status_code == 200, downloaded.text
    book = load_workbook(BytesIO(downloaded.content), read_only=True)
    assert book.sheetnames == ["Summary", "Displayed results"]
    summary = dict(list(book["Summary"].values)[1:])
    assert summary["Export population"] == "DISPLAYED_PAGE" and summary["Rows exported"] == 1
    import json

    assert (
        json.loads(summary["Snapshot JSON"])
        == client.get(f"/api/runs/{run['run_id']}/metrics").json()
    )
    header, item = list(book["Displayed results"].values)
    row = dict(zip(header, item, strict=True))
    assert row["delta"] == 2.75 and row["group_id"] == table["rows"][0]["group_id"]
    book.close()


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
        "Trong dữ liệu đã chuẩn hóa, xem mã đơn và ngày giao dịch.",
        "Liệt kê các dòng có mã đơn trống trong nguồn chưa chuẩn hóa.",
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


def test_project_inventory_and_preparation_use_current_scoped_uploads(pg, monkeypatch):  # noqa: F811
    import studio.agent_jobs as agents
    from studio.contracts.agent import NormalizationDraft
    from studio.database import ProjectRow, RunRow, VersionRow, WorkspaceRow

    client, factory, worker = pg
    pid = project(client)
    other = project(client, "Another project")
    calls = []

    def mock_proposal(provider, table_id, profile, policy, reserve, context=None):
        calls.append(table_id)
        return NormalizationDraft(
            table_id=table_id,
            entity_kind="synthetic_record",
            grain="one synthetic transaction per row",
            fields=[
                dict(
                    source_field="c1",
                    target_id="reference_id",
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
                    semantic_metric="synthetic_net",
                    amount_basis="net",
                ),
            ],
        )

    def unexpected_router(*args):
        pytest.fail("Explicit source requests must not go through the language router")

    monkeypatch.setattr(agents, "propose_normalization", mock_proposal)
    monkeypatch.setattr(agents, "interpret_requests", unexpected_router)

    def upload(name, project_id=pid):
        raw = "ID,Amount\n" + "".join(
            f"{index:07d},{index + sum(map(ord, name))}.25\n" for index in range(3000)
        )
        response = client.post(
            "/api/datasets/uploads",
            data={"project_id": project_id, "request_ai_mapping": "false"},
            files={"files": (name, raw.encode(), "text/csv")},
        )
        assert response.status_code == 202, response.text
        return response.json()["items"][0]["id"]

    names = ("Revenue A.csv", "Sổ kế toán.csv", "Payments C.csv")
    dataset_ids = [upload(name) for name in names]
    outside = upload("Other project.csv", other)
    drain(factory, worker)
    with factory() as db:
        ws = WorkspaceRow(id="scope-isolated", name="Isolated", policy={})
        db.add(ws)
        db.flush()
        foreign = ProjectRow(workspace_id=ws.id, name="Outside workspace", business_scope="test")
        db.add(foreign)
        db.flush()
        db.add(
            DatasetRow(
                workspace_id=ws.id,
                project_id=foreign.id,
                owner_id="foreign",
                name="Other workspace.csv",
                sha256="a" * 64,
                parse_signature="synthetic",
            )
        )
        db.commit()

    project_context = {"project_id": pid}
    cid = conversation(client, project_context)

    def ask(text, key, *, context=project_context, conversation_id=cid):
        job = ask_agent(client, context, conversation_id, key=key, text=text)
        drain(factory, worker)
        return job, workflow_for(client, factory, job["job_id"])

    _, listed = ask("Dự án này có những tệp nào?", "inventory")
    text = " ".join(b["text"] for b in listed["detail"]["blocks"])
    assert "Dự án có 3 nguồn dữ liệu" in text
    assert all(name in text for name in names)
    assert "Other project.csv" not in text and "Other workspace.csv" not in text
    assert "Đã đọc dữ liệu, chưa chuẩn hóa" in text

    for index, question in enumerate(
        ('Tệp "Sổ kế toán.csv" đã chuẩn hóa chưa?', "Kiểm tra riêng sổ kế toán.")
    ):
        _, single = ask(question, f"one-{index}")
        text = " ".join(b["text"] for b in single["detail"]["blocks"])
        assert names[1] in text and all(n not in text for n in (names[0], names[2]))

    for index, unknown in enumerate(
        ("Nonexistent.csv", "Other project.csv", "Other workspace.csv")
    ):
        _, missing = ask(f'Chuẩn bị tệp "{unknown}"', f"unknown-{index}")
        assert missing["state"] == "WAITING_REVIEW"
        assert [r["kind"] for r in missing["detail"]["reviews"]] == ["CLARIFICATION"]
    assert not calls

    pinned = {"project_id": pid, "dataset_id": dataset_ids[0]}
    pinned_cid = conversation(client, pinned, key="one-source-conversation")
    _, widened = ask(
        "Có bao nhiêu nguồn dữ liệu trong dự án?",
        "explicit-project",
        context=pinned,
        conversation_id=pinned_cid,
    )
    assert all(name in " ".join(b["text"] for b in widened["detail"]["blocks"]) for name in names)
    assert widened["context"]["dataset_id"] is None

    question = (
        (Path(__file__).parent / "fixtures/assistant-project-preparation-vi.txt")
        .read_text(encoding="utf-8")
        .strip()
    )
    queued, prepared = ask(question, "all")
    assert prepared["state"] == "WAITING_REVIEW"
    assert prepared["detail"]["dataset_ids"] == dataset_ids
    assert prepared["detail"]["intent"]["intent"] == "PREPARE_NORMALIZATION"
    assert prepared["detail"]["intent"]["dataset_ids"] == dataset_ids
    statuses = [b["text"] for b in prepared["detail"]["blocks"] if b["type"] == "progress"]
    assert all(any(name in text and "3.000 dòng" in text for text in statuses) for name in names)
    reviews = prepared["detail"]["reviews"]
    assert len(reviews) == 3 and all(
        r["kind"] == "MAPPING" and r["state"] == "OPEN" for r in reviews
    )
    with factory() as db:
        actual = set(
            db.scalars(
                select(TableRow.id).join(VersionRow).where(VersionRow.dataset_id.in_(dataset_ids))
            )
        )
        assert set(calls) == actual
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 0
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0
    replay = ask_agent(client, project_context, cid, key="all", text=question)
    assert replay["job_id"] == queued["job_id"]
    _, reviewed = ask("Liệt kê các nguồn dữ liệu trong dự án", "review-status")
    assert (
        sum("chờ kiểm tra, xác nhận" in block["text"] for block in reviewed["detail"]["blocks"])
        == 3
    )

    upload("New upload.csv")
    _, refreshed = ask("Liệt kê các nguồn dữ liệu trong dự án", "fresh")
    text = " ".join(b["text"] for b in refreshed["detail"]["blocks"])
    assert "Dự án có 4 nguồn dữ liệu" in text and "New upload.csv" in text
    old = client.get(f"/api/agent/workflows/{prepared['id']}").json()
    assert old["detail"]["dataset_ids"] == dataset_ids and len(calls) == 3

    path = f"/api/agent/workflows/{prepared['id']}"
    for index, review in enumerate(old["detail"]["reviews"]):
        draft = review["normalization_draft"]
        # Chỉ người duyệt xác nhận cột tiền tổng hợp là doanh thu thuần bằng VND.
        amount = next(field for field in draft["fields"] if field["source_field"] == "c2")
        amount.update(
            semantic_metric="synthetic_net", amount_basis="net", currency="VND", unit="VND"
        )
        approved = client.post(
            path + "/decisions",
            json=dict(
                review_id=review["id"],
                nonce=review["nonce"],
                fingerprint=review["fingerprint"],
                decision=dict(type="MAPPING", draft=draft),
            ),
            headers={"Idempotency-Key": f"manual-mapping-{index}"},
        )
        assert approved.status_code == 200, approved.text
        drain(factory, worker)
    complete = client.get(path).json()
    assert complete["state"] == "COMPLETED", complete
    results = [b for b in complete["detail"]["blocks"] if b["type"] == "dataset_summary"]
    assert {b["dataset_id"] for b in results} == set(dataset_ids)
    assert all(
        b["rows"] == 3000 and b["invalid_rows"] == 0 and b["status"] == "READY" for b in results
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 3

    denied = client.post(
        "/api/conversations",
        json={"context": {"project_id": pid, "dataset_id": outside}},
        headers={"Idempotency-Key": "wrong-project"},
    )
    assert denied.status_code == 404


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
