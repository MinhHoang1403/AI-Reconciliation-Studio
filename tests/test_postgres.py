"""Real PostgreSQL integration in a UUID schema, never in application tables."""

import secrets
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from studio.config import settings
from studio.database import (
    ArtifactRow,
    AttemptRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MembershipRow,
    SessionRow,
    TableRow,
    WorkspaceRow,
    now,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def pg(monkeypatch, tmp_path):
    import os

    if os.environ.get("STUDIO_POSTGRES_TESTS") != "1":
        pytest.skip("Explicit isolated PostgreSQL execution required")
    import studio.api as api
    import studio.database as database
    import studio.worker as worker
    from studio.access import seed_demo, session_token_hash

    schema = "test_" + uuid4().hex
    admin = create_engine(settings.database_url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(api, "SessionFactory", factory)
    monkeypatch.setattr(worker, "SessionFactory", factory)
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    monkeypatch.setattr(settings, "qwen_enabled", False)
    monkeypatch.setattr(settings, "mapping_ai_provider", "QWEN")
    monkeypatch.setattr(settings, "instance_path", tmp_path / "instance")
    monkeypatch.setattr(settings, "demo_proof_path", tmp_path / "proof")
    monkeypatch.setattr(settings, "local_demo_access", False)
    command.upgrade(Config("alembic.ini"), "head")
    with factory() as db:
        seed_demo(db)
        token = secrets.token_urlsafe(32)
        db.add(MembershipRow(workspace_id="demo", actor_id="test-owner", role="owner"))
        db.add(
            SessionRow(
                token_hash=session_token_hash(token),
                actor_id="test-owner",
                workspace_id="demo",
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.commit()
    client = TestClient(
        api.app,
        base_url="http://127.0.0.1:18180",
        headers={"Origin": "http://127.0.0.1:18180"},
        raise_server_exceptions=True,
    )
    client.cookies.set("studio_session", token)
    try:
        yield client, factory, worker
    finally:
        client.close()
        engine.dispose()
        assert schema.startswith("test_") and len(schema) == 37
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def project(client, name="Synthetic project"):
    response = client.post(
        "/api/projects", json={"name": name, "business_scope": "synthetic scope"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(
    client,
    project_id,
    raw=b"Order ID,Gross amount\n000123,1234.50\n000124,invalid\n000125,\n000126,0\n",
):
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": project_id},
        files={"files": ("synthetic.csv", raw, "text/csv")},
    )
    assert response.status_code == 202, response.text
    return response.json()["items"][0]


def drain(factory, worker):
    for _ in range(10):
        with factory() as db:
            claimed = worker.claim_job(db)
        if claimed is None:
            return
        worker.process_job(*claimed)
    pytest.fail("queue did not drain")


def approve(client, table_id):
    mapping = client.get(f"/api/tables/{table_id}/mappings").json()["items"][0]
    schema = mapping["schema"]
    schema.update(entity_kind="order", grain="one source order row")
    schema["fields"] = [
        {"id": "reference_id", "name": "Reference", "data_type": "string", "required": True},
        {
            "id": "gross_amount",
            "name": "Gross amount",
            "data_type": "decimal",
            "required": True,
            "semantic_metric": "synthetic_gross",
            "amount_basis": "gross",
            "currency": "VND",
            "unit": "VND",
        },
    ]
    decisions = [
        {
            "source_field": "c1",
            "candidate_target": "reference_id",
            "decision": "APPROVED",
            "evidence_ids": [f"{table_id}:c1"],
            "grain_assumption": "order",
            "transformation_candidate": {"op": "cast_string_preserve"},
        },
        {
            "source_field": "c2",
            "candidate_target": "gross_amount",
            "decision": "APPROVED",
            "evidence_ids": [f"{table_id}:c2"],
            "grain_assumption": "order",
            "transformation_candidate": {"op": "parse_decimal", "locale": "en-US"},
        },
    ]
    response = client.post(
        f"/api/mappings/{mapping['id']}/approve",
        json={"schema_definition": schema, "decisions": decisions, "extraction_reviewed": True},
    )
    assert response.status_code == 200, response.text
    return response.json(), mapping


def test_postgres_migration_T02_T13_pipeline_and_idempotency(pg):
    client, factory, worker = pg
    pid = project(client)
    first = upload(client, pid)
    duplicate = upload(client, pid)
    assert duplicate["reused"] and duplicate["id"] == first["id"]
    drain(factory, worker)
    tables = client.get(f"/api/datasets/{first['id']}/tables").json()["items"]
    assert len(tables) == 1
    table_id = tables[0]["id"]
    parsed = client.get(f"/api/tables/{table_id}/preview").json()
    assert [r["c1"] for r in parsed["items"]] == ["000123", "000124", "000125", "000126"]
    approved, original = approve(client, table_id)
    headers = {"Idempotency-Key": "synthetic-normalize"}
    response = client.post(
        f"/api/datasets/{first['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    duplicate_job = client.post(
        f"/api/datasets/{first['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers=headers,
    )
    assert response.json()["job_id"] == duplicate_job.json()["job_id"]
    drain(factory, worker)
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "SUCCEEDED", job
    canonical_id = job["result"]["canonical_id"]
    canonical = client.get(
        f"/api/tables/{table_id}/preview?kind=canonical&canonical_id={canonical_id}"
    ).json()
    assert [r["record_payload"]["gross_amount"] for r in canonical["items"]] == [
        "1234.50",
        None,
        None,
        "0.00",
    ]
    errors = client.get(
        f"/api/tables/{table_id}/preview?kind=errors&canonical_id={canonical_id}"
    ).json()
    assert [r["value_state"] for r in errors["items"]] == ["INVALID", "NULL"]
    with factory() as db:
        original_refs = [
            (a.id, a.sha256)
            for a in db.scalars(select(ArtifactRow).where(ArtifactRow.kind.in_(["raw", "parsed"])))
        ]
    second, _ = approve(client, table_id)
    assert second["revision"] > approved["revision"]
    with factory() as db:
        assert db.get(CanonicalRow, canonical_id).stale
        assert [
            (a.id, a.sha256)
            for a in db.scalars(select(ArtifactRow).where(ArtifactRow.kind.in_(["raw", "parsed"])))
        ] == original_refs
    stale = client.post(
        f"/api/datasets/{first['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "stale"},
    )
    assert stale.status_code == 409
    # Same bytes in another project must not reuse the first project's Dataset/FileArtifact.
    assert upload(client, project(client, "Second project"))["id"] != first["id"]
    drain(factory, worker)
    with factory() as db:
        jobs = list(db.scalars(select(JobRow).where(JobRow.kind == "mapping")))
        assert any(j.result and j.result.get("cache_hit") is True for j in jobs)


def test_T12_viewer_and_cross_workspace_csrf(pg):
    client, factory, worker = pg
    pid = project(client)
    dataset = upload(client, pid)
    drain(factory, worker)
    table = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"][0]
    mapping = client.get(f"/api/tables/{table['id']}/mappings").json()["items"][0]
    with factory() as db:
        membership = db.get(MembershipRow, ("demo", "test-owner"))
        membership.role = "viewer"
        db.commit()
    denied = client.post(
        f"/api/mappings/{mapping['id']}/approve",
        json={"schema_definition": mapping["schema"], "decisions": []},
    )
    assert denied.status_code == 403
    from studio.database import AuditRow

    with factory() as db:
        assert db.scalar(select(AuditRow).where(AuditRow.action == "ACCESS_DENIED")) is not None
    with factory() as db:
        membership = db.get(MembershipRow, ("demo", "test-owner"))
        membership.role = "owner"
        db.add(WorkspaceRow(id="other", name="other synthetic", policy={}))
        db.flush()
        from studio.database import ProjectRow

        foreign = ProjectRow(workspace_id="other", name="Secret", business_scope="other")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.get(f"/api/datasets?project_id={foreign_id}").status_code == 404
    assert (
        client.post(
            "/api/projects",
            json={"name": "bad", "business_scope": "bad"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    no_origin = TestClient(client.app, base_url="http://127.0.0.1:18180")
    no_origin.cookies.update(client.cookies)
    assert (
        no_origin.post("/api/projects", json={"name": "bad", "business_scope": "bad"}).status_code
        == 403
    )
    assert client.get("/api/projects", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/api/projects", headers={"X-Forwarded-Host": "localhost"}).status_code == 403
    anonymous = TestClient(client.app, base_url="http://127.0.0.1:18180")
    assert anonymous.get("/api/projects").status_code == 401
    assert anonymous.get("/api/session").status_code == 403


def test_worker_skip_locked_fencing_and_restart_recovery(pg):
    client, factory, worker = pg
    pid = project(client)
    upload(client, pid)
    with factory() as first, factory() as second:
        locked = first.scalar(select(JobRow).with_for_update())
        assert locked is not None
        assert worker.claim_job(second) is None
        first.rollback()
    with factory() as db:
        first_claim = worker.claim_job(db)
    assert first_claim is not None
    with factory() as db:
        job = db.get(JobRow, first_claim[0])
        job.lease_until = now() - timedelta(seconds=1)
        db.commit()
    with factory() as db:
        second_claim = worker.claim_job(db)
    assert second_claim and second_claim[0] == first_claim[0] and second_claim[1] != first_claim[1]
    with factory() as db:
        from studio.errors import DomainError

        with pytest.raises(DomainError, match="JOB_LEASE_LOST"):
            worker._fence(db, *first_claim)
    worker.process_job(*second_claim)
    drain(factory, worker)
    with factory() as db:
        assert db.get(JobRow, second_claim[0]).status == "SUCCEEDED"
        attempts = list(
            db.scalars(
                select(AttemptRow)
                .where(AttemptRow.job_id == second_claim[0])
                .order_by(AttemptRow.number)
            )
        )
        assert [a.status for a in attempts] == ["FAILED", "SUCCEEDED"]
        assert len(list(db.scalars(select(TableRow)))) == 1


def test_parse_failure_never_publishes_artifact(pg):
    client, factory, worker = pg
    item = upload(client, project(client), b"id,value\n001,10\n002,20,unexpected\n")
    drain(factory, worker)
    with factory() as db:
        assert len(list(db.scalars(select(TableRow)))) == 0
        assert len(list(db.scalars(select(ArtifactRow)))) == 1  # raw only
        assert db.get(DatasetRow, item["id"]).status == "FAILED"


def test_normalize_crash_before_publish_is_atomic_and_retry_safe(pg, monkeypatch):
    client, factory, worker = pg
    item = upload(client, project(client))
    drain(factory, worker)
    table = client.get(f"/api/datasets/{item['id']}/tables").json()["items"][0]
    approved, _ = approve(client, table["id"])
    response = client.post(
        f"/api/datasets/{item['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "crash-test"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    original_finish = worker._finish

    def crash(db, job, result):
        raise RuntimeError("synthetic crash before transaction publication")

    monkeypatch.setattr(worker, "_finish", crash)
    drain(factory, worker)
    with factory() as db:
        assert db.get(JobRow, job_id).status == "RETRYABLE_FAILURE"
        assert not list(db.scalars(select(CanonicalRow)))
        assert len(list(db.scalars(select(ArtifactRow)))) == 2  # raw + parsed only
        job = db.get(JobRow, job_id)
        job.available_at = now()
        db.commit()
    monkeypatch.setattr(worker, "_finish", original_finish)
    drain(factory, worker)
    with factory() as db:
        assert db.get(JobRow, job_id).status == "SUCCEEDED"
        assert len(list(db.scalars(select(CanonicalRow)))) == 1


def test_zero_decimal_and_backend_summary(pg):
    client, factory, worker = pg
    pid = project(client)
    item = upload(client, pid, b"Order ID,Gross amount\n000123,0.00\n000124,12.50\n")
    drain(factory, worker)
    table = client.get(f"/api/datasets/{item['id']}/tables").json()["items"][0]
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert (summary["dataset_count"], summary["table_count"], summary["mapping_review_count"]) == (
        1,
        1,
        1,
    )
    approved, _ = approve(client, table["id"])
    response = client.post(
        f"/api/datasets/{item['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "zero-decimal"},
    )
    assert response.status_code == 202
    drain(factory, worker)
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["mapping_review_count"] == 0 and summary["ready_canonical_count"] == 1
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "SUCCEEDED"
    canonical_id = job["result"]["canonical_id"]
    rows = client.get(
        f"/api/tables/{table['id']}/preview?kind=canonical&canonical_id={canonical_id}&search=000123"
    ).json()
    assert rows["total"] == 1
    assert rows["items"][0]["record_payload"]["gross_amount"] == "0.00"


def test_multi_upload_csv_xlsx_and_extraction_approval_gate(pg):
    import io

    import openpyxl

    client, factory, worker = pg
    pid = project(client)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Synthetic sheet"
    sheet.append(["Synthetic report"])
    sheet.append(["Order ID", "Gross amount"])
    sheet.append(["000123", 12.50])
    second = book.create_sheet("Other sheet")
    second.append(["Order ID", "Gross amount"])
    second.append(["000124", 0])
    stream = io.BytesIO()
    book.save(stream)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid},
        files=[
            ("files", ("synthetic.csv", b"Order ID,Gross amount\n000123,0.00\n", "text/csv")),
            (
                "files",
                (
                    "synthetic.xlsx",
                    stream.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )
    assert response.status_code == 202, response.text
    assert len(response.json()["items"]) == 2
    drain(factory, worker)
    xlsx_id = next(d["id"] for d in response.json()["items"] if d["name"].endswith(".xlsx"))
    tables = client.get(f"/api/datasets/{xlsx_id}/tables").json()["items"]
    assert len(tables) == 2
    table = next(t for t in tables if t["sheet"] == "Synthetic sheet")
    assert (
        table["parsed"]["header_row"] == 2
        and "HEADER_INFERRED_REVIEW" in table["parsed"]["warnings"]
    )
    evidence = client.get(f"/api/evidence/{table['id']}:c1?row=3").json()
    assert evidence["items"][0]["c1"] == "000123"
    mapping = client.get(f"/api/tables/{table['id']}/mappings").json()["items"][0]
    denied = client.post(
        f"/api/mappings/{mapping['id']}/approve",
        json={"schema_definition": mapping["schema"], "decisions": []},
    )
    assert denied.status_code == 422 and denied.json()["code"] == "EXTRACTION_REVIEW_REQUIRED"
    approved, _ = approve(client, table["id"])
    normalized = client.post(
        f"/api/datasets/{xlsx_id}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "synthetic-xlsx-normalization"},
    )
    assert normalized.status_code == 202
    drain(factory, worker)
    job = client.get(f"/api/jobs/{normalized.json()['job_id']}").json()
    assert job["status"] == "SUCCEEDED"
    canonical_id = job["result"]["canonical_id"]
    values = client.get(
        f"/api/tables/{table['id']}/preview?kind=canonical&canonical_id={canonical_id}"
    ).json()["items"]
    assert values[0]["record_payload"]["reference_id"] == "000123"
    assert values[0]["record_payload"]["gross_amount"] == "12.5"


def test_unexpected_errors_are_redacted_without_traceback(pg, monkeypatch, caplog):
    import studio.api as api

    client, _, _ = pg
    pid = project(client)

    def fail(*args, **kwargs):
        raise ValueError("synthetic-sensitive-content-must-not-be-logged")

    monkeypatch.setattr(api, "get_scoped", fail)
    response = client.get(f"/api/projects/{pid}/summary")
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert "synthetic-sensitive-content" not in response.text
    assert "synthetic-sensitive-content" not in caplog.text


def test_gemini_worker_uses_durable_budget_and_validated_proposal(pg, monkeypatch):
    import json

    import httpx
    from pydantic import SecretStr
    from studio.ai_gateway import GeminiProvider
    from studio.contracts import WorkspacePolicy
    from studio.database import AuditRow, MappingRow, TraceRow

    client, factory, worker = pg
    monkeypatch.setattr(settings, "mapping_ai_provider", "GEMINI")
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", 1)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-key"))
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.host == "generativelanguage.googleapis.com"
        context = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        evidence = context["context"]["untrusted_data"]["columns"][0]["evidence_ids"]
        proposal = {
            "entity_kind": "unknown",
            "grain": "unknown",
            "status": "PROPOSED",
            "decisions": [
                {
                    "source_field": "c1",
                    "candidate_target": "reference_id",
                    "decision": "PROPOSED",
                    "evidence_ids": evidence,
                    "grain_assumption": "unknown",
                    "transformation_candidate": {"op": "cast_string_preserve"},
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(proposal)}]}}],
                "usageMetadata": {"totalTokenCount": 17},
            },
        )

    class MockGemini(GeminiProvider):
        def __init__(self, config):
            super().__init__(config, httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(worker, "GeminiProvider", MockGemini)
    with factory() as db:
        ws = db.get(WorkspaceRow, "demo")
        ws.policy = WorkspacePolicy(
            mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=2
        ).model_dump()
        db.commit()
    pid = project(client)
    first = upload(client, pid)
    drain(factory, worker)
    with factory() as db:
        job = db.scalar(select(JobRow).where(JobRow.kind == "mapping"))
        assert job.status == "SUCCEEDED" and job.result["source"] == "GEMINI"
        mapping = db.get(MappingRow, job.result["mapping_id"])
        assert mapping.status == "PROPOSED" and mapping.decision is None
        trace = db.scalar(select(TraceRow).where(TraceRow.job_id == job.id))
        assert trace.provider == "GEMINI" and trace.usage["cloud_requests"] == 1
        assert trace.usage["tokens"]["totalTokenCount"] == 17
        assert (
            len(
                list(
                    db.scalars(select(AuditRow).where(AuditRow.action == "GEMINI_REQUEST_RESERVED"))
                )
            )
            == 1
        )
    second = upload(client, pid, b"Order ID,Gross amount\n000555,5.00\n")
    assert second["id"] != first["id"]
    drain(factory, worker)
    with factory() as db:
        jobs = list(db.scalars(select(JobRow).where(JobRow.kind == "mapping")))
        assert any(j.status == "BLOCKED" and j.error_code == "CLOUD_BUDGET_EXHAUSTED" for j in jobs)
    assert len(calls) == 1
    config_dto = client.get("/api/settings").json()
    assert config_dto["mapping_ai_provider"] == "GEMINI"
    assert config_dto["gemini_requests_remaining"] == 0
    assert "synthetic-test-key" not in str(config_dto)


def test_gemini_budget_serializes_concurrent_reservations_across_workspaces(pg, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from pydantic import SecretStr
    from studio.contracts import WorkspacePolicy
    from studio.repository import gemini_request_counts, reserve_gemini_request

    _, factory, _ = pg
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", 3)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-key"))
    with factory() as db:
        db.get(WorkspaceRow, "demo").policy = WorkspacePolicy(
            mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1
        ).model_dump()
        db.add(
            WorkspaceRow(
                id="second",
                name="synthetic",
                policy=WorkspacePolicy(
                    mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=5
                ).model_dump(),
            )
        )
        db.commit()

    def attempt(workspace):
        with factory() as db:
            allowed = reserve_gemini_request(db, workspace, "synthetic-job", settings)
            db.commit()
            return allowed

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, ["demo"] * 4 + ["second"] * 6))
    assert sum(results) == 3 and sum(results[:4]) == 1
    with factory() as db:
        assert gemini_request_counts(db, "demo") == (3, 1)
    assert not attempt("second")  # a fresh session never resets consumed budget


def test_document_pipeline_reservation_artifact_scope_and_reuse_after_revocation(pg, monkeypatch):
    import hashlib
    import io
    import zipfile

    import httpx
    from pydantic import SecretStr
    from studio.contracts import WorkspacePolicy
    from studio.database import AuditRow

    client, factory, worker = pg
    pdf = b"%PDF-1.7 synthetic fixture"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "word/document.xml", '<w:document xmlns:w="urn:synthetic"><w:p/></w:document>'
        )
    docx = stream.getvalue()
    monkeypatch.setattr(settings, "allow_cloud_parsing", True)
    monkeypatch.setattr(settings, "cloud_parser_request_budget", 2)
    monkeypatch.setattr(settings, "cloud_parser_credit_budget", 20)
    monkeypatch.setattr(settings, "llama_cloud_api_key", SecretStr("synthetic-test-key"))
    with factory() as db:
        db.get(WorkspaceRow, "demo").policy = WorkspacePolicy(
            allow_cloud_parsing=True,
            parser_request_budget=2,
            parser_allowed_sha256=[hashlib.sha256(v).hexdigest() for v in [pdf, docx]],
        ).model_dump()
        db.commit()
    original_client = httpx.Client
    creates = []
    remote_id = str(uuid4())

    def respond(request):
        if request.method == "POST":
            creates.append(request)
            assert b'"tier": "cost_effective"' in request.content
            assert b'"max_pages": 2' in request.content
            return httpx.Response(200, json={"id": remote_id, "status": "PENDING"})
        if request.url.path == "/api/v2/organizations":
            return httpx.Response(200, json={"items": [{"id": "synthetic-org"}]})
        if request.url.path.endswith("/usage"):
            return httpx.Response(
                200,
                json={
                    "plan": {},
                    "usage": {
                        "active_free_credits_usage": [
                            {"remaining_balance": 100, "expires_at": "2099-01-01T00:00:00Z"}
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "job": {"status": "COMPLETED", "usage": {"credits": 3}},
                "markdown": {
                    "pages": [
                        {
                            "page_number": 1,
                            "markdown": "| ID | Amount |\n| --- | --- |\n| 000123 | 12.50 |",
                        }
                    ]
                },
                "items": {"pages": [{"page_number": 1, "items": [{"type": "table", "rows": 2}]}]},
            },
        )

    monkeypatch.setattr(
        worker.httpx,
        "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )
    pid = project(client)
    ids = []
    for extension, content, mime in [
        ("pdf", pdf, "application/pdf"),
        ("docx", docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ]:
        response = client.post(
            "/api/datasets/uploads",
            data={"project_id": pid},
            files={"files": (f"synthetic.{extension}", content, mime)},
        )
        assert response.status_code == 202, response.text
        dataset_id = response.json()["items"][0]["id"]
        ids.append(dataset_id)
        drain(factory, worker)
        documents = client.get(f"/api/datasets/{dataset_id}/documents").json()
        assert len(documents) == 1, documents
        artifact = documents[0]
        assert artifact["artifact"]["quality"] == "UNVERIFIED_EXTRACTION"
        assert artifact["extraction"]["verification_status"] == "UNVERIFIED_EXTRACTION"
        assert artifact["source_file"]["sha256"] == hashlib.sha256(content).hexdigest()
        assert artifact["extraction"]["pages"][0]["page_number"] == 1
        assert not client.get(f"/api/datasets/{dataset_id}/artifacts").json()["canonical_datasets"]
    assert len(creates) == 2
    with factory() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditRow).where(AuditRow.action == "LLAMAPARSE_DOCUMENT_RESERVED")
                    )
                )
            )
            == 2
        )
        policy = db.get(WorkspaceRow, "demo").policy
        db.get(WorkspaceRow, "demo").policy = {**policy, "allow_cloud_parsing": False}
        db.commit()
    monkeypatch.setattr(settings, "allow_cloud_parsing", False)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid},
        files={"files": ("synthetic.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 202 and response.json()["items"][0]["reused"]
    assert response.json()["items"][0]["id"] == ids[0]
    assert client.get(f"/api/datasets/{ids[0]}/documents").status_code == 200
    assert len(creates) == 2
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid},
        files={"files": ("synthetic-other.pdf", pdf + b"other", "application/pdf")},
    )
    assert response.status_code == 422


def test_explicit_manual_upload_never_enqueues_ai_or_spends_quota(pg, monkeypatch):
    client, factory, worker = pg
    monkeypatch.setattr(settings, "mapping_ai_provider", "GEMINI")
    pid = project(client)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid, "request_ai_mapping": "false"},
        files={"files": ("manual.csv", b"ID,Value\n000123,12.50\n", "text/csv")},
    )
    assert response.status_code == 202
    drain(factory, worker)
    with factory() as db:
        assert [j.kind for j in db.scalars(select(JobRow))] == ["parse"]
    dataset_id = response.json()["items"][0]["id"]
    table = client.get(f"/api/datasets/{dataset_id}/tables").json()["items"][0]
    assert len(client.get(f"/api/tables/{table['id']}/mappings").json()["items"]) == 1
