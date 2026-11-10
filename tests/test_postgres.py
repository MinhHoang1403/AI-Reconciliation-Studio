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


def test_local_session_reverification_and_expiry(pg, monkeypatch):
    """Real isolated DB sessions, real proof checks; only internal health is synthetic."""
    import io
    import json
    from contextlib import nullcontext
    from types import SimpleNamespace

    from pydantic import SecretStr
    from studio import access

    client, factory, _ = pg
    client.cookies.clear()  # Only this isolated TestClient, never browser/application sessions.
    monkeypatch.setattr(settings, "access_token", SecretStr(""))
    monkeypatch.setattr(settings, "local_demo_access", True)
    settings.instance_path.write_text("c" * 12)
    identity = {"value": "a" * 12}
    monkeypatch.setattr(
        access.urllib.request,
        "build_opener",
        lambda *_: SimpleNamespace(
            open=lambda *_args, **_kwargs: nullcontext(
                SimpleNamespace(
                    headers={"X-Studio-Instance": identity["value"]},
                )
            ),
        ),
    )

    def verify():
        containers = [
            {
                "Id": (
                    identity["value"]
                    if service == "frontend"
                    else settings.instance_path.read_text()
                )
                + "0" * 52,
                "Config": {
                    "Labels": {
                        "com.docker.compose.project": "ai-reconciliation-studio",
                        "com.docker.compose.service": service,
                    }
                },
                "NetworkSettings": {
                    "Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18180"}]}
                    if service == "frontend"
                    else {}
                },
            }
            for service in ("frontend", "backend", "worker", "postgres")
        ]
        monkeypatch.setattr(access.sys, "stdin", io.StringIO(json.dumps(containers)))
        access.activate_demo()

    response = client.get("/api/session")
    assert response.status_code == 403 and response.json()["code"] == "LOCAL_DEMO_NOT_VERIFIED"
    verify()
    response = client.get("/api/session")
    assert response.status_code == 200
    assert response.json() == {"actor_id": "demo-owner", "workspace_id": "demo", "role": "owner"}
    assert all(
        flag in response.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "path=/api", "max-age=28800")
    )
    assert client.get("/api/settings").status_code == 200
    cookie = client.cookies.get("studio_session")
    assert client.get("/api/session").status_code == 200
    assert client.cookies.get("studio_session") == cookie
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", None)
    created = client.post("/api/workspaces", json={"name": "AI local TEST"})
    assert created.status_code == 201
    with factory() as db:
        policy = db.get(WorkspaceRow, created.json()["id"]).policy
        assert policy["mode"] == "CLOUD_ALLOWED" and policy["external_request_budget"] is None
        assert not policy["allow_cloud_parsing"]
    for change in ("frontend", "backend"):
        if change == "frontend":
            identity["value"] = "b" * 12
        else:
            settings.instance_path.write_text("d" * 12)
        for path in ("/api/session", "/api/settings"):
            response = client.get(path)
            assert (
                response.status_code == 403 and response.json()["code"] == "LOCAL_DEMO_NOT_VERIFIED"
            )
        verify()
        assert client.get("/api/session").status_code == 200
        assert client.cookies.get("studio_session") == cookie
    with factory() as db:
        db.get(SessionRow, access.session_token_hash(cookie)).expires_at = now() - timedelta(
            seconds=1
        )
        db.commit()
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/session").status_code == 200
    assert client.cookies.get("studio_session") != cookie
    assert client.get("/api/settings").status_code == 200
    response = client.get("/api/session", headers={"Host": "attacker.example"})
    assert response.status_code == 403 and response.json()["code"] == "HOST_NOT_ALLOWED"


def test_assistant_raw_download_preserves_bytes_permissions_and_checksum(pg):
    from studio.database import ProjectRow
    from studio.storage import storage_path

    client, factory, _worker = pg
    project = client.post(
        "/api/projects", json={"name": "Synthetic download", "business_scope": "download-oracle"}
    ).json()
    raw = b"id,amount\n000702,12.75\n"
    upload = client.post(
        "/api/datasets/uploads",
        data={"project_id": project["id"], "request_ai_mapping": "false"},
        files=[("files", ("Chung-tu.csv", raw, "text/csv"))],
    )
    assert upload.status_code == 202
    dataset_id = upload.json()["items"][0]["id"]
    path = f"/api/datasets/{dataset_id}/download"
    response = client.get(path)
    assert response.status_code == 200 and response.content == raw
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    with factory() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
    assert client.get(path).content == raw  # Read-only download does not require editor.
    with factory() as db:
        artifact = db.scalar(select(ArtifactRow).where(ArtifactRow.kind == "raw"))
        stored = storage_path(settings.storage_root, artifact.storage_key)
        stored.write_bytes(b"corrupted synthetic fixture")
    assert client.get(path).status_code == 409
    with factory() as db:
        db.add(WorkspaceRow(id="foreign-download", name="Other", policy={}))
        db.flush()
        db.add(
            ProjectRow(
                id="foreign-project",
                workspace_id="foreign-download",
                name="Other",
                business_scope="private",
            )
        )
        db.flush()
        db.add(
            DatasetRow(
                id="foreign-dataset",
                workspace_id="foreign-download",
                project_id="foreign-project",
                owner_id="other",
                name="private.csv",
                sha256="0" * 64,
                parse_signature="private",
            )
        )
        db.commit()
    assert client.get("/api/datasets/foreign-dataset/download").status_code == 404
    client.cookies.clear()
    assert client.get(path).status_code == 401


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


def test_project_lifecycle_is_scoped_reversible_and_audited_once(pg):
    from studio.database import AuditRow, ProjectRow

    client, factory, _ = pg
    pid = project(client, "TEST Lifecycle project")
    path = f"/api/projects/{pid}/lifecycle"
    body = {"action": "delete", "expected_state": "active", "expected_version": 0}
    assert client.get(path).json()["allowed"] == ["archive", "delete"]
    assert client.post(path, json=body).status_code == 422
    body["confirmation"] = "TEST Lifecycle project"
    assert client.post(path, json=body).json()["state"] == "deleted"
    assert client.post(path, json=body).json()["state"] == "deleted"
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert pid not in {p["id"] for p in client.get("/api/projects").json()["items"]}
    assert pid in {
        p["id"] for p in client.get("/api/projects?lifecycle=deleted").json()["items"]
    }
    assert client.post(path, json={**body, "action": "archive"}).status_code == 409
    with factory() as db:
        assert db.get(ProjectRow, pid).deleted_at is not None
        events = list(db.scalars(select(AuditRow).where(AuditRow.resource_id == pid)))
        assert [event.action for event in events if event.action == "PROJECT_DELETE"] == [
            "PROJECT_DELETE"
        ]
        member = db.get(MembershipRow, ("demo", "test-owner"))
        member.role = "viewer"
        db.add(WorkspaceRow(id="other", name="Other TEST workspace", policy={}))
        db.flush()
        foreign = ProjectRow(workspace_id="other", name="TEST foreign", business_scope="TEST")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.get(path).status_code == 403
    assert client.get(f"/api/projects/{foreign_id}/lifecycle").status_code == 404
    assert client.get("/api/projects?lifecycle=deleted").status_code == 403
    with factory.begin() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "owner"
    assert client.post(
        path, json={"action": "restore", "expected_state": "deleted", "expected_version": 1}
    ).json()["state"] == "active"
    assert client.get(f"/api/projects/{pid}").status_code == 200
    assert client.post(path, json=body).status_code == 409


def test_dataset_lifecycle_retains_tables_blocks_work_and_hides_archived_sources(pg):
    client, factory, worker = pg
    pid = project(client, "TEST Dataset retention")
    dataset = upload(client, pid)
    did = dataset["id"]
    path = f"/api/datasets/{did}/lifecycle"
    archive = {"action": "archive", "expected_state": "active", "expected_version": 0}
    assert client.get(path).json()["running_jobs"] > 0
    assert client.post(path, json=archive).status_code == 409
    drain(factory, worker)
    impact = client.get(path).json()
    assert impact["references"]["mappings"] > 0
    assert impact["allowed"] == ["archive"]
    assert client.post(path, json={**archive, "action": "delete"}).status_code == 409
    tables = client.get(f"/api/datasets/{did}/tables").json()
    assert client.post(path, json=archive).json()["state"] == "archived"
    assert client.get(f"/api/datasets?project_id={pid}").json()["total"] == 0
    assert client.get(f"/api/datasets?project_id={pid}&lifecycle=archived").json()["total"] == 1
    assert client.get(f"/api/datasets/{did}/tables").json() == tables
    mapping = client.get(f"/api/tables/{tables['items'][0]['id']}/mappings").json()["items"][0]
    denied = client.post(
        f"/api/mappings/{mapping['id']}/approve",
        json={"schema_definition": mapping["schema"], "decisions": []},
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "SOURCE_ARCHIVED"
    restored = client.post(
        path, json={"action": "restore", "expected_state": "archived", "expected_version": 1}
    )
    assert restored.json()["state"] == "active"
    assert client.get(f"/api/datasets?project_id={pid}").json()["total"] == 1


def test_workspace_management_keeps_policy_membership_and_stale_tab_scoped(pg):
    client, factory, _ = pg
    old_project = project(client)
    origin = {"X-Studio-Workspace": "demo", "Idempotency-Key": "create-test-workspace"}
    created = client.post("/api/workspaces", json={"name": "  Kho TEST  "}, headers=origin)
    assert created.status_code == 201
    choice = created.json()
    workspace_id = choice["id"]
    assert choice["name"] == "Kho TEST"
    assert choice["role"] == "owner"
    replay = client.post("/api/workspaces", json={"name": "Kho TEST"}, headers=origin)
    assert replay.json() == choice
    assert {row["id"] for row in client.get("/api/workspaces").json()} == {"demo", workspace_id}
    assert client.post("/api/workspaces/current", json={"id": "unavailable"}).status_code == 404

    switch = client.post("/api/workspaces/current", json={"id": workspace_id}, headers=origin)
    assert switch.json() == choice
    stale = client.post(
        "/api/projects", json={"name": "Stale tab", "business_scope": "test"}, headers=origin
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "WORKSPACE_CHANGED"
    assert client.get(f"/api/projects/{old_project}").status_code == 404
    assert client.get("/api/projects").json()["total"] == 0
    policy = client.get("/api/settings").json()["policy"]
    assert policy["mode"] == "LOCAL_ONLY"
    assert policy["external_request_budget"] == 0
    path = "/api/workspaces/current/name"
    assert client.patch(path, json={"name": "Kho mới", "expected_name": "Kho TEST"}).json()[
        "name"
    ] == "Kho mới"
    stale_name = client.patch(path, json={"name": "Tên cũ", "expected_name": "Kho TEST"})
    assert stale_name.status_code == 409

    with factory() as db:
        db.get(MembershipRow, (workspace_id, "test-owner")).role = "viewer"
        db.commit()
    assert client.post("/api/workspaces", json={"name": "Không có quyền"}).status_code == 403
    assert client.patch(path, json={"name": "Cấm", "expected_name": "Kho mới"}).status_code == 403
    assert client.post("/api/workspaces/current", json={"id": "demo"}).status_code == 200
    assert client.get(f"/api/projects/{old_project}").status_code == 200


def test_source_rename_preserves_original_download_and_rejects_stale_name(pg):
    from studio.database import AuditRow

    client, factory, worker = pg
    pid = project(client, "TEST source display name")
    source = upload(client, pid)
    drain(factory, worker)
    detail = f"/api/datasets/{source['id']}"
    before = client.get(detail).json()
    download = client.get(f"{detail}/download")
    body = {"name": "Sổ giao dịch.csv", "expected_name": before["name"]}

    invalid = client.patch(f"{detail}/name", json={**body, "name": "../unsafe.csv"})
    assert invalid.json()["code"] == "INVALID_DATASET_NAME"
    wrong_extension = client.patch(f"{detail}/name", json={**body, "name": "unsafe.xlsx"})
    assert wrong_extension.json()["code"] == "INVALID_DATASET_NAME"
    renamed = client.patch(f"{detail}/name", json=body)
    assert renamed.status_code == 200
    assert renamed.json()["name"] == body["name"]
    assert client.patch(f"{detail}/name", json=body).status_code == 200
    stale = client.patch(f"{detail}/name", json={**body, "name": "Another.csv"})
    assert stale.status_code == 409
    assert client.get(detail).json() == {**before, "name": body["name"]}
    after_download = client.get(f"{detail}/download")
    assert after_download.content == download.content
    assert after_download.headers["content-disposition"] == download.headers["content-disposition"]

    with factory() as db:
        assert len(list(db.scalars(select(AuditRow).where(
            AuditRow.resource_id == source["id"], AuditRow.action == "DATASET_RENAMED"
        )))) == 1
        db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
    assert client.patch(f"{detail}/name", json=body).status_code == 403


def test_failed_source_soft_delete_preserves_raw_artifact_and_supports_restore(pg):
    from studio.database import VersionRow
    from studio.storage import checksum, storage_path

    client, factory, worker = pg
    pid = project(client, "TEST Soft delete")
    did = upload(client, pid, b"id,value\n001,10\n002,20,unexpected\n")["id"]
    drain(factory, worker)
    with factory() as db:
        version = db.scalar(select(VersionRow).where(VersionRow.dataset_id == did))
        artifact = db.scalar(
            select(ArtifactRow).where(ArtifactRow.dataset_version_id == version.id)
        )
        file = storage_path(settings.storage_root, artifact.storage_key)
        original = checksum(file)
        artifact_id = artifact.id
    endpoint = f"/api/datasets/{did}/lifecycle"
    assert client.get(endpoint).json()["allowed"] == ["archive", "delete"]
    assert client.post(
        endpoint, json={"action": "delete", "expected_state": "active", "expected_version": 0}
    ).json()["state"] == "deleted"
    assert client.get(f"/api/datasets/{did}/artifacts").status_code == 404
    assert client.get(f"/api/datasets?project_id={pid}&lifecycle=deleted&search=synthetic").json()[
        "total"
    ] == 1
    assert client.get(f"/api/datasets?project_id={pid}&lifecycle=deleted&search=%25").json()[
        "total"
    ] == 0
    with factory() as db:
        assert db.get(ArtifactRow, artifact_id) is not None
        assert db.get(DatasetRow, did).deleted_at is not None
    assert checksum(file) == original
    assert client.post(
        endpoint, json={"action": "restore", "expected_state": "deleted", "expected_version": 1}
    ).json()["state"] == "active"
    assert client.get(f"/api/datasets/{did}/artifacts").status_code == 200


@pytest.mark.parametrize("first", ["archive", "enqueue"])
def test_project_lifecycle_and_job_submission_serialize_in_both_orders(pg, first):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from studio.access import Actor
    from studio.errors import DomainError
    from studio.repository import enqueue_job
    from studio.resource_lifecycle import LifecycleChange, change_resource, lock_project

    client, factory, _ = pg
    name = "TEST Lifecycle concurrency"
    pid = project(client, name)
    actor = Actor(id="test-owner", workspace_id="demo", role="owner")
    started = Event()

    def submit():
        with factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            started.set()
            try:
                if first == "archive":
                    enqueue_job(db, "demo", pid, "parse", "lifecycle-race", {})
                    db.commit()
                else:
                    change_resource(
                        db, actor, "project", pid,
                        LifecycleChange(
                            action="archive", expected_state="active",
                            expected_version=0, confirmation=name,
                        ),
                    )
            except DomainError as error:
                return error.code
        return "unexpected-success"

    with ThreadPoolExecutor(max_workers=1) as pool:
        with factory() as db:
            lock_project(db, pid)
            if first == "enqueue":
                enqueue_job(db, "demo", pid, "parse", "lifecycle-race", {})
            future = pool.submit(submit)
            assert started.wait(timeout=5)
            if first == "archive":
                change_resource(
                    db, actor, "project", pid,
                    LifecycleChange(
                        action="archive", expected_state="active",
                        expected_version=0, confirmation=name,
                    ),
                )
            else:
                db.commit()
        assert future.result(timeout=10) == (
            "PROJECT_ARCHIVED" if first == "archive" else "RESOURCE_LIFECYCLE_CONFLICT"
        )
    with factory() as db:
        assert len(list(db.scalars(select(JobRow).where(JobRow.project_id == pid)))) == (
            0 if first == "archive" else 1
        )


def test_project_classification_owner_audit_conflict_and_scope(pg):
    """Classification changes metadata only; owner, workspace and stale-write gates remain real."""
    from studio.database import AuditRow, ProjectRow

    client, factory, _ = pg
    pid = project(client)
    assert client.get(f"/api/projects/{pid}").json()["classification"] == "WORK"
    created = client.post(
        "/api/projects",
        json={"name": "Fixture", "business_scope": "synthetic", "classification": "TEST"},
    )
    assert created.status_code == 201
    assert created.json()["classification"] == "TEST"
    path = f"/api/projects/{pid}/classification"
    assert (
        client.patch(
            path, json={"classification": "TEST", "expected_classification": "WORK"}
        ).status_code
        == 200
    )
    assert client.get(f"/api/projects/{pid}").json()["classification"] == "TEST"
    assert (
        client.patch(
            path, json={"classification": "UNKNOWN", "expected_classification": "WORK"}
        ).status_code
        == 409
    )
    for role in ("viewer", "editor"):
        with factory() as db:
            db.get(MembershipRow, ("demo", "test-owner")).role = role
            db.commit()
        assert (
            client.patch(
                path, json={"classification": "WORK", "expected_classification": "TEST"}
            ).status_code
            == 403
        )
    with factory() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "owner"
        db.add(WorkspaceRow(id="classification-foreign", name="Other", policy={}))
        db.flush()
        db.add(
            ProjectRow(
                id="classification-foreign-project",
                workspace_id="classification-foreign",
                name="Private",
                business_scope="private",
            )
        )
        db.commit()
    assert (
        client.patch(
            "/api/projects/classification-foreign-project/classification",
            json={"classification": "TEST", "expected_classification": "UNKNOWN"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            path, json={"classification": "WORK", "expected_classification": "TEST"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path, json={"classification": "UNKNOWN", "expected_classification": "WORK"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path, json={"classification": "OTHER", "expected_classification": "UNKNOWN"}
        ).status_code
        == 422
    )
    with factory() as db:
        events = list(
            db.scalars(
                select(AuditRow)
                .where(AuditRow.resource_id == pid, AuditRow.action.like("PROJECT_CLASSIFIED_%"))
                .order_by(AuditRow.created_at, AuditRow.id)
            )
        )
        assert [e.action for e in events] == [
            "PROJECT_CLASSIFIED_WORK",
            "PROJECT_CLASSIFIED_TEST",
            "PROJECT_CLASSIFIED_WORK",
            "PROJECT_CLASSIFIED_UNKNOWN",
        ]
        assert {e.actor_id for e in events} == {"test-owner"}


def test_project_classification_filters_before_pagination_and_preserves_unknown(pg):
    """Unknown legacy projects stay visible; totals/search/pages use the same scoped set."""
    from studio.database import AuditRow, ProjectRow

    client, factory, _ = pg
    with factory() as db:
        for index in range(120):
            pid = f"classified-{index:03}"
            db.add(
                ProjectRow(
                    id=pid,
                    workspace_id="demo",
                    name="Dự án trùng tên",
                    business_scope=f"Kho miền Nam {index:03}",
                )
            )
            if index % 3 != 2:
                db.add(
                    AuditRow(
                        workspace_id="demo",
                        actor_id="fixture",
                        resource_id=pid,
                        action="PROJECT_CLASSIFIED_" + ("TEST" if index % 3 == 0 else "WORK"),
                    )
                )
        db.commit()
    first = client.get("/api/projects?include_test=false&limit=20").json()
    second = client.get("/api/projects?include_test=false&limit=20&offset=20").json()
    assert first["total"] == second["total"] == 80
    assert len(first["items"]) == len(second["items"]) == 20
    assert all(p["classification"] != "TEST" for p in first["items"] + second["items"])
    assert set(p["id"] for p in first["items"]).isdisjoint(p["id"] for p in second["items"])
    assert client.get("/api/projects?include_test=true&limit=20").json()["total"] == 120
    assert (
        client.get("/api/projects?include_test=false&search=KHO%20MIỀN%20NAM%20000").json()["total"]
        == 0
    )
    assert (
        client.get("/api/projects?include_test=true&search=KHO%20MIỀN%20NAM%20000").json()["items"][
            0
        ]["classification"]
        == "TEST"
    )
    assert client.get("/api/projects/classified-000").json()["classification"] == "TEST"
    assert client.get("/api/projects/classified-002").json()["classification"] == "UNKNOWN"


def test_project_classification_concurrent_owners_cannot_overwrite_same_expected_state(pg):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from studio.access import Actor
    from studio.api import ProjectClassificationInput, classify_project
    from studio.contracts import ProjectClassification
    from studio.errors import DomainError

    client, factory, _ = pg
    pid = project(client)
    barrier = Barrier(2)

    def change(category):
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                classify_project(
                    pid,
                    ProjectClassificationInput(
                        classification=category,
                        expected_classification=ProjectClassification.WORK,
                    ),
                    db,
                    Actor("test-owner", "demo", "owner"),
                )
                return 200
            except DomainError as exc:
                return exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(
            executor.map(change, [ProjectClassification.TEST, ProjectClassification.UNKNOWN])
        ) == [200, 409]
    assert client.get(f"/api/projects/{pid}").json()["classification"] in {"TEST", "UNKNOWN"}


def test_recent_dataset_api_stable_tie_order_and_project_scope(pg):
    """Equal upload times use ID as a tie-breaker, independent of list offsets."""
    client, factory, _ = pg
    pid = project(client)
    other = project(client, "Other project")
    timestamp = now()
    with factory() as db:
        for index in reversed(range(30)):
            db.add(
                DatasetRow(
                    id=f"recent-{index:03}",
                    workspace_id="demo",
                    project_id=pid,
                    owner_id="test-owner",
                    name=f"Source {index}",
                    sha256=f"{index:064x}",
                    parse_signature="synthetic",
                    status="UPLOADED",
                    created_at=timestamp,
                )
            )
        db.add(
            DatasetRow(
                id="foreign-recent",
                workspace_id="demo",
                project_id=other,
                owner_id="test-owner",
                name="Other",
                sha256="f" * 64,
                parse_signature="synthetic",
                status="UPLOADED",
                created_at=timestamp,
            )
        )
        db.commit()
    recent = client.get("/api/datasets", params={"project_id": pid, "offset": 0, "limit": 5}).json()
    later = client.get(
        "/api/datasets", params={"project_id": pid, "offset": 25, "limit": 25}
    ).json()
    assert recent["total"] == later["total"] == 30
    assert [item["id"] for item in recent["items"]] == [f"recent-{i:03}" for i in range(5)]
    assert [item["id"] for item in later["items"]] == [f"recent-{i:03}" for i in range(25, 30)]


def test_project_search_pagination_restore_and_workspace_scope(pg):
    """A saved project outside page one remains addressable; search is literal/scoped."""
    from studio.database import ProjectRow

    client, factory, _ = pg
    with factory() as db:
        for index in range(120):
            db.add(
                ProjectRow(
                    id=f"search-{index:03}",
                    workspace_id="demo",
                    name="Đối soát đơn hàng",
                    business_scope=f"Kho miền Nam {index:03}",
                )
            )
        db.add(WorkspaceRow(id="foreign-search", name="Other", policy={}))
        db.flush()
        db.add(
            ProjectRow(
                id="foreign-project",
                workspace_id="foreign-search",
                name="Đối soát đơn hàng",
                business_scope="private",
            )
        )
        db.add(
            ProjectRow(
                id="literal-project",
                workspace_id="demo",
                name="100%_literal",
                business_scope="test",
            )
        )
        db.commit()
    first = client.get("/api/projects?limit=50").json()
    second = client.get("/api/projects?limit=50&offset=50").json()
    assert first["total"] == 121 and len(first["items"]) == len(second["items"]) == 50
    assert not ({p["id"] for p in first["items"]} & {p["id"] for p in second["items"]})
    saved = second["items"][0]
    assert client.get(f"/api/projects/{saved['id']}").json() == saved
    assert client.get("/api/projects/foreign-project").status_code == 404
    assert client.get("/api/projects/missing").status_code == 404
    scoped = client.get("/api/projects", params={"search": "MIỀN NAM 119"}).json()
    assert [p["id"] for p in scoped["items"]] == ["search-119"]
    assert client.get("/api/projects", params={"search": "ĐỐI SOÁT"}).json()["total"] == 120
    assert client.get("/api/projects?search=private").json()["total"] == 0
    assert client.get("/api/projects", params={"search": "%_"}).json()["total"] == 1
    assert client.get("/api/projects?search=absent").json() == {"items": [], "total": 0}
    assert client.get("/api/projects?limit=101").status_code == 422
    assert client.get("/api/projects?offset=-1").status_code == 422
    assert client.get("/api/projects", params={"search": "x" * 201}).status_code == 422


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


def test_mapping_reproposal_joins_pending_job_and_replays_the_same_request(pg):
    client, factory, worker = pg
    source = upload(client, project(client))
    with factory() as db:
        claim = worker.claim_job(db)
        assert claim is not None and claim[0] == source["job_id"]
    worker.process_job(*claim)
    table = client.get(f"/api/datasets/{source['id']}/tables").json()["items"][0]
    route = f"/api/tables/{table['id']}"
    pending = client.get(f"{route}/mappings").json()["job"]
    assert pending["status"] == "QUEUED"
    for key in ("join-one", "join-two"):
        response = client.post(f"{route}/mapping-proposals", headers={"Idempotency-Key": key})
        assert response.status_code == 202
        assert response.json()["job_id"] == pending["id"]
    with factory() as db:
        job = db.get(JobRow, pending["id"])
        assert job is not None
        job.status = "BLOCKED"
        job.error_code = "GEMINI_UNAVAILABLE"
        db.commit()
    assert client.get(f"{route}/mappings").json()["job"]["error_code"] == "GEMINI_UNAVAILABLE"
    headers = {"Idempotency-Key": "one-explicit-retry"}
    fresh = client.post(f"{route}/mapping-proposals", headers=headers).json()
    assert fresh["job_id"] != pending["id"]
    assert client.post(f"{route}/mapping-proposals", headers=headers).json() == fresh
    with factory() as db:
        job = db.get(JobRow, fresh["job_id"])
        assert job is not None and job.payload == {"table_id": table["id"], "refresh": True}



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


def test_mapping_lifecycle_preserves_references_and_revision_numbers(pg):
    from studio.database import MappingRow, MembershipRow, SchemaRow

    client, factory, worker = pg
    source = upload(client, project(client))
    drain(factory, worker)
    dataset = f"/api/datasets/{source['id']}"
    table = client.get(f"{dataset}/tables").json()["items"][0]["id"]
    route = f"/api/tables/{table}"

    def life(mapping_id):
        return f"/api/mappings/{mapping_id}/lifecycle"

    approved, draft = approve(client, table)
    assert client.post(life(approved["id"]), json={"action": "delete"}).status_code == 200
    assert client.get(f"{dataset}/tables").json()["items"][0]["active_mapping_id"] is None
    assert client.get(dataset).json()["status"] == "NEEDS_MAPPING_REVIEW"
    assert client.post(life(draft["id"]), json={"action": "delete"}).status_code == 200
    with factory() as db:
        assert db.get(MappingRow, draft["id"]) is None
        assert db.get(SchemaRow, draft["schema"]["id"]) is not None
    assert client.get(f"{route}/mappings").json()["items"] == []
    assert client.post(f"{route}/mapping-draft").status_code == 201
    fresh, _ = approve(client, table)
    assert fresh["revision"] > approved["revision"]
    response = client.post(
        f"{dataset}/normalize", json={"mapping_id": fresh["id"]},
        headers={"Idempotency-Key": "mapping-history-normalize"},
    )
    assert response.status_code == 202
    assert client.get(life(fresh["id"])).json()["busy"]
    assert client.post(life(fresh["id"]), json={"action": "archive"}).status_code == 409
    assert client.post(life(fresh["id"]), json={"action": "delete"}).status_code == 409
    drain(factory, worker)
    preserved = client.get(f"{dataset}/artifacts").json()["canonical_datasets"][0]
    impact = client.get(life(fresh["id"])).json()
    assert impact["referenced"] and impact["allowed"] == ["archive"]
    assert client.post(life(fresh["id"]), json={"action": "delete"}).status_code == 409
    assert client.post(life(fresh["id"]), json={"action": "archive"}).status_code == 200
    assert all(m["id"] != fresh["id"] for m in client.get(f"{route}/mappings").json()["items"])
    archive = client.get(f"{route}/mappings?include_archived=true").json()["items"][0]
    assert archive["id"] == fresh["id"] and archive["archived"]
    assert client.get(f"{dataset}/artifacts").json()["canonical_datasets"] == [preserved]
    with factory() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
    assert client.get(life(fresh["id"])).status_code == 403
    assert client.post(life(fresh["id"]), json={"action": "delete"}).status_code == 403


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
    other_upload = upload(client, project(client, "Second project"))
    assert other_upload["id"] != first["id"]
    drain(factory, worker)
    with factory() as db:
        other_parse = db.get(JobRow, other_upload["job_id"])
        assert set(other_parse.result["reused_templates"].values()) == {second["id"]}


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

        current_lease = db.get(JobRow, second_claim[0]).lease_until
        worker._renew_lease(db, *first_claim)
        assert db.get(JobRow, second_claim[0]).lease_until == current_lease
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


def test_worker_classifies_json_boolean_consistently_with_dispatch(pg):
    from studio.repository import enqueue_job

    client, factory, worker = pg
    pid = project(client)
    with factory() as db:
        inference = enqueue_job(
            db, "demo", pid, "reconciliation_plan", "string-flag",
            {"verified_candidates_only": "true"},
        )
        native = enqueue_job(
            db, "demo", pid, "reconciliation_plan", "bool-flag",
            {"verified_candidates_only": True},
        )
        db.commit()
        assert worker._needs_inference(inference)
        assert not worker._needs_inference(native)
        assert worker.claim_job(db, inference_busy=True)[0] == native.id
        assert worker.claim_job(db, inference_busy=True) is None


def test_worker_heartbeats_and_renews_during_long_native_job(pg, monkeypatch):
    from threading import Event
    from types import SimpleNamespace

    client, factory, worker = pg
    item = upload(client, project(client))
    start = now()
    elapsed = 0
    beats = []
    started, release, finished = Event(), Event(), Event()

    class EndWorkerLoop(Exception):
        pass

    def process(job_id, token, *, native_only=False):
        assert not native_only
        started.set()
        assert release.wait(15)
        with factory() as db:
            job = worker._fence(db, job_id, token)
            worker._finish(db, job, {})
            db.commit()
        finished.set()

    def sleep(_seconds):
        nonlocal elapsed
        if elapsed >= 340:
            release.set()
            assert finished.wait(15)
            raise EndWorkerLoop
        assert started.wait(15)
        elapsed += 20

    monkeypatch.setattr(
        worker, "Path", lambda _: SimpleNamespace(touch=lambda: beats.append(elapsed))
    )
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=sleep))
    monkeypatch.setattr(worker, "wait", lambda _futures, *, timeout: sleep(timeout), raising=False)
    monkeypatch.setattr(worker, "now", lambda: start + timedelta(seconds=elapsed))
    monkeypatch.setattr(worker.settings, "worker_lease_seconds", 300)
    monkeypatch.setattr(worker, "process_job", process)
    with pytest.raises(EndWorkerLoop):
        worker.main()

    assert beats[-1] == 340
    assert max(b - a for a, b in zip(beats, beats[1:], strict=False)) <= 20
    with factory() as db:
        job = db.get(JobRow, item["job_id"])
        assert job.status == "SUCCEEDED" and job.attempts == 1 and job.lease_until is None


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
    with factory() as db:
        published_before = set(db.execute(select(ArtifactRow.id, ArtifactRow.sha256)))

    def crash(db, job, result):
        raise RuntimeError("synthetic crash before transaction publication")

    monkeypatch.setattr(worker, "_finish", crash)
    drain(factory, worker)
    with factory() as db:
        assert db.get(JobRow, job_id).status == "RETRYABLE_FAILURE"
        assert not list(db.scalars(select(CanonicalRow)))
        assert set(db.execute(select(ArtifactRow.id, ArtifactRow.sha256))) == published_before
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
    initial = client.get(f"/api/projects/{pid}/summary").json()
    assert initial["dataset_count"] == 0 and initial["preparation_action"]["kind"] == "UPLOAD"
    item = upload(client, pid, b"Order ID,Gross amount\n000123,0.00\n000124,12.50\n")
    waiting = client.get(f"/api/projects/{pid}/summary").json()
    assert waiting["active_job_count"] == 1 and waiting["preparation_action"]["kind"] == "WAIT"
    drain(factory, worker)
    table = client.get(f"/api/datasets/{item['id']}/tables").json()["items"][0]
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert (summary["dataset_count"], summary["table_count"], summary["mapping_review_count"]) == (
        1,
        1,
        1,
    )
    assert summary["preparation_action"]["kind"] == "REVIEW_MAPPING"
    assert summary["preparation_action"]["table_id"] == table["id"]
    approved, _ = approve(client, table["id"])
    assert client.get(f"/api/projects/{pid}/summary").json()["preparation_action"] == {
        "kind": "NORMALIZE",
        "dataset_id": item["id"],
        "table_id": table["id"],
        "canonical_id": None,
    }
    response = client.post(
        f"/api/datasets/{item['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "zero-decimal"},
    )
    assert response.status_code == 202
    drain(factory, worker)
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["mapping_review_count"] == 0 and summary["ready_canonical_count"] == 1
    assert summary["active_job_count"] == 0
    assert summary["partial_canonical_count"] == summary["stale_canonical_count"] == 0
    assert summary["preparation_action"]["kind"] == "UPLOAD"  # need a second source
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "SUCCEEDED"
    canonical_id = job["result"]["canonical_id"]
    rows = client.get(
        f"/api/tables/{table['id']}/preview?kind=canonical&canonical_id={canonical_id}&search=000123"
    ).json()
    assert rows["total"] == 1
    assert rows["items"][0]["record_payload"]["gross_amount"] == "0.00"


def test_preparation_summary_partial_stale_failed_and_paginated_sources(pg):
    """Counters use all scoped data; navigation never relabels PARTIAL as mapping failure."""
    client, factory, worker = pg
    pid = project(client)
    item = upload(client, pid)
    drain(factory, worker)
    table = client.get(f"/api/datasets/{item['id']}/tables").json()["items"][0]
    approved, _ = approve(client, table["id"])
    job = client.post(
        f"/api/datasets/{item['id']}/normalize",
        json={"mapping_id": approved["id"]},
        headers={"Idempotency-Key": "partial-summary"},
    )
    assert job.status_code == 202
    drain(factory, worker)
    summary = client.get(f"/api/projects/{pid}/summary").json()
    assert summary["mapping_review_count"] == summary["ready_canonical_count"] == 0
    assert summary["partial_canonical_count"] == 1 and summary["active_job_count"] == 0
    target = summary["preparation_action"]
    assert target["kind"] == "REVIEW_DATA" and target["dataset_id"] == item["id"]
    canonical = client.get(f"/api/datasets/{item['id']}/artifacts").json()["canonical_datasets"][0]
    assert target["canonical_id"] == canonical["id"]
    with factory() as db:
        row = db.get(CanonicalRow, canonical["id"])
        row.contract = {**row.contract, "quality_status": "FAILED"}
        db.commit()
    failed = client.get(f"/api/projects/{pid}/summary").json()
    assert failed["failed_canonical_count"] == 1 and failed["partial_canonical_count"] == 0
    assert failed["preparation_action"]["kind"] == "REVIEW_DATA"
    # New approval marks the old canonical stale, without deleting its quality history.
    approve(client, table["id"])
    stale = client.get(f"/api/projects/{pid}/summary").json()
    assert stale["stale_canonical_count"] == 1 and stale["failed_canonical_count"] == 0
    assert stale["preparation_action"]["kind"] == "NORMALIZE"
    with factory() as db:
        for index in range(79):
            db.add(
                DatasetRow(
                    workspace_id="demo",
                    project_id=pid,
                    owner_id="test-owner",
                    name=f"Synthetic {index}",
                    sha256=f"{index:064x}",
                    parse_signature="summary-fixture",
                    status="UPLOADED",
                )
            )
        db.commit()
    page = client.get(f"/api/datasets?project_id={pid}&limit=25").json()
    assert len(page["items"]) == 25 and page["total"] == 80
    assert client.get(f"/api/projects/{pid}/summary").json()["dataset_count"] == 80
    assert (
        client.get(f"/api/projects/{project(client, 'Empty')}/summary").json()["dataset_count"] == 0
    )


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


def test_prepared_upload_is_queryable_without_mapping_or_provider(pg):
    client, factory, worker = pg
    pid = project(client)
    response = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid, "request_ai_mapping": "false"},
        files={
            "files": (
                "prepared.csv",
                b"ID,Date,Other date,Total\n000123,2026-10-01,2026-02-29,-12.50\n"
                b"000124,2026-10-02,2026-02-28,0\n",
                "text/csv",
            ),
        },
    )
    assert response.status_code == 202
    drain(factory, worker)
    dataset_id = response.json()["items"][0]["id"]
    table = client.get(f"/api/datasets/{dataset_id}/tables").json()["items"][0]
    prepared = table["prepared"]
    assert prepared["prepared_artifact_id"] != table["parsed"]["artifact"]["id"]
    assert prepared["source_artifact_id"] == table["parsed"]["artifact"]["id"]
    assert prepared["review_required"] is True
    assert prepared["eligible_scope"] == "EXPLORATION"
    assert table["active_mapping_id"] is None
    summary = {item["column_id"]: item for item in prepared["quality_summary"]}
    assert summary["c2"]["data_type"] == "date"
    assert summary["c3"]["data_type"] == "string"
    assert summary["c3"]["invalid_date_count"] == 1
    url = f"/api/tables/{table['id']}/preview"
    raw = client.get(url, params={"kind": "raw"}).json()
    preview = client.get(url, params={"kind": "prepared"}).json()
    assert raw["items"] == preview["items"]
    assert raw["total"] == preview["total"] == 2
    assert preview["items"][0]["c1"] == "000123"
    assert preview["items"][0]["c4"] == "-12.50"
    findings = client.get(url, params={"kind": "prepared_findings"}).json()
    assert findings["total"] == 1
    assert findings["items"][0]["_source_row"] == 2
    assert findings["items"][0]["_preparation_flags"] == ["INVALID_DATE:c3"]
    query = {
        "project_id": pid,
        "source_kind": "PREPARED",
        "source_id": table["id"],
        "filters": [{"field_id": "c2", "op": "gt", "value": "2026-10-01"}],
    }
    result = client.post("/api/agent/queries", json=query)
    assert result.status_code == 200
    assert result.json()["verification_status"] == "RAW_UNVERIFIED"
    assert result.json()["rows"][0]["c1"] == "000124"
    assert result.json()["rows"][0]["source_provenance"][0]["row"] == 3
    foreign_query = {**query, "project_id": project(client)}
    assert client.post("/api/agent/queries", json=foreign_query).status_code == 404
    with factory() as db:
        assert [j.kind for j in db.scalars(select(JobRow))] == ["parse"]


def test_parse_can_publish_while_mapping_inference_is_waiting(pg, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from test_agent_postgres import ask_agent, workflow_for
    from test_assistant_postgres import conversation

    client, factory, worker = pg
    pid = project(client)
    upload(client, pid)
    with factory() as db:
        parsed = worker.claim_job(db)
    worker.process_job(*parsed)
    with factory() as db:
        mapping = worker.claim_job(db)
        assert db.get(JobRow, mapping[0]).kind == "mapping"

    started = Event()
    release = Event()

    def stalled_mapping(*_args):
        started.set()
        assert release.wait(20)

    monkeypatch.setattr(worker, "_mapping", stalled_mapping)
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(worker.process_job, *mapping)
        try:
            assert started.wait(5)
            second = project(client, "Independent second queue project")
            incoming = upload(client, second, b"ID,Date\n001,2026-10-01\n")
            ctx = {"project_id": second}
            request = ask_agent(
                client, ctx, conversation(client, ctx), command="EXPLORE_DATA", text="Xem dữ liệu"
            )
            with factory() as db:
                parse_claim = worker.claim_job(db, inference_busy=True)
            assert parse_claim[0] == incoming["job_id"]
            worker.process_job(*parse_claim)
            table = client.get(f"/api/datasets/{incoming['id']}/tables").json()["items"][0]
            assert table["prepared"]["row_count"] == 1
            query = client.post(
                "/api/agent/queries",
                json={"project_id": second, "source_kind": "PREPARED", "source_id": table["id"]},
            )
            assert query.status_code == 200
            assert query.json()["rows"][0]["c1"] == "001"
            with factory() as db:
                preview_claim = worker.claim_job(db, inference_busy=True)
            assert preview_claim[0] == request["job_id"]
            worker.process_job(*preview_claim)
            flow = workflow_for(client, factory, request["job_id"])
            assert flow["state"] == "COMPLETED" and flow["detail"]["model_calls"] == 0
            assert not waiting.done()
            with factory() as db:
                assert worker.claim_job(db, inference_busy=True) is None
        finally:
            release.set()
        waiting.result()


def test_two_authorized_workspace_queues_publish_scoped_artifacts(pg):
    from concurrent.futures import ThreadPoolExecutor

    from studio.access import session_token_hash

    owner, factory, worker = pg
    token = secrets.token_urlsafe(32)
    with factory() as db:
        db.add(WorkspaceRow(id="second-queue", name="Synthetic second queue", policy={}))
        db.flush()
        db.add(MembershipRow(workspace_id="second-queue", actor_id="other-owner", role="owner"))
        db.add(
            SessionRow(
                workspace_id="second-queue",
                actor_id="other-owner",
                token_hash=session_token_hash(token),
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.commit()
    other = TestClient(
        owner.app, base_url="http://127.0.0.1:18180", headers={"Origin": "http://127.0.0.1:18180"}
    )
    other.cookies.set("studio_session", token)
    pairs = [(owner, project(owner)), (other, project(other))]
    with ThreadPoolExecutor(max_workers=2) as pool:
        uploads = list(pool.map(lambda pair: upload(*pair, b"ID,Date\n001,2026-10-01\n"), pairs))
    drain(factory, worker)
    for index, (client, pid) in enumerate(pairs):
        dataset, foreign = uploads[index], uploads[1 - index]
        assert client.get(f"/api/jobs/{dataset['job_id']}").json()["status"] == "SUCCEEDED"
        assert client.get(f"/api/jobs/{foreign['job_id']}").status_code == 404
        assert client.get(f"/api/datasets/{foreign['id']}/tables").status_code == 404
        (table,) = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"]
        response = client.post(
            "/api/agent/queries",
            json={"project_id": pid, "source_kind": "PREPARED", "source_id": table["id"]},
        )
        assert response.status_code == 200 and response.json()["rows"][0]["c1"] == "001"


def test_upload_mapping_memory_reuses_only_compatible_draft(pg):
    client, factory, worker = pg
    pid = project(client)
    original = upload(client, pid, b"Order ID,Gross amount\n001,12.50\n002,0\n")
    drain(factory, worker)
    table = client.get(f"/api/datasets/{original['id']}/tables").json()["items"][0]
    approved, _ = approve(client, table["id"])

    second = upload(client, pid, b"Order ID,Gross amount\n003,15.50\n004,-2\n")
    drain(factory, worker)
    second_table = client.get(f"/api/datasets/{second['id']}/tables").json()["items"][0]
    assert second_table["active_mapping_id"] is None
    job = client.get(f"/api/jobs/{second['job_id']}").json()
    assert list(job["result"]["reused_templates"].values()) == [approved["id"]]
    mappings = client.get(f"/api/tables/{second_table['id']}/mappings").json()["items"]
    assert len(mappings) == 1
    assert mappings[0]["status"] == "PROPOSED" and mappings[0]["decision"] is None
    assert all(
        evidence.startswith(f"{second_table['id']}:")
        for decision in mappings[0]["proposal"]["decisions"]
        for evidence in decision["evidence_ids"]
    )

    drift = upload(client, pid, b"Order ID,Gross amount,New field\n005,3,unknown\n")
    drain(factory, worker)
    assert client.get(f"/api/jobs/{drift['job_id']}").json()["result"]["reused_templates"] == {}


@pytest.mark.parametrize("blocked", [None, "workspace", "global", "key", "finite-workspace"])
def test_unlimited_reservations_preserve_history_and_permissions(pg, monkeypatch, blocked):
    from pydantic import SecretStr
    from studio.database import AuditRow
    from studio.repository import gemini_request_counts, reserve_gemini_request

    client, factory, _ = pg
    monkeypatch.setattr(settings, "local_demo_access", True)
    monkeypatch.setattr(settings, "allow_external_ai", blocked != "global")
    monkeypatch.setattr(settings, "external_ai_request_budget", None)
    monkeypatch.setattr(
        settings, "gemini_api_key", SecretStr("" if blocked == "key" else "synthetic")
    )
    for task in ("agent", "assistant", "planner"):
        monkeypatch.setattr(settings, task + "_request_budget", None)
    monkeypatch.setattr(settings, "agent_cloud_enabled", True)
    monkeypatch.setattr(settings, "assistant_cloud_enabled", True)
    with factory() as db:
        db.get(WorkspaceRow, "demo").policy = dict(
            mode="CLOUD_ALLOWED",
            allow_external_ai=blocked != "workspace",
            external_request_budget=210 if blocked == "finite-workspace" else None,
        )
        for i in range(211):
            db.add(
                AuditRow(
                    workspace_id="demo",
                    actor_id="test-owner",
                    action="GEMINI_REQUEST_RESERVED",
                    resource_id=f"historical-{i}",
                )
            )
        db.commit()
    with factory() as db:
        assert reserve_gemini_request(db, "demo", "new-synthetic-request", settings) is (
            blocked is None
        )
        db.commit()
        assert gemini_request_counts(db, "demo") == ((212, 212) if blocked is None else (211, 211))
    # PG fixture principal is test-owner, so no synthetic deployment proof is needed.
    dto = client.get("/api/settings").json()
    assert dto["gemini_requests_used"] == (212 if blocked is None else 211)
    assert (
        dto["gemini_requests_remaining"] is None
        if blocked in {None, "key"}
        else dto["gemini_requests_remaining"] == 0
    )
    if blocked is None:
        assert all(
            t["remaining"] is None and t["configured_ceiling"] is None
            for t in dto["ai_task_allowances"].values()
        )
        assert dto["agent_cloud_enabled"] and dto["assistant_cloud_enabled"]
