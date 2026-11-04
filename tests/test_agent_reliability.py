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
    assert wf["state"] == ("WAITING_REVIEW" if count > 2 else "COMPLETED")
    if count > 2:
        assert wf["detail"]["reviews"][0]["kind"] == "CLARIFICATION"
    else:
        assert wf["detail"]["blocks"]


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
