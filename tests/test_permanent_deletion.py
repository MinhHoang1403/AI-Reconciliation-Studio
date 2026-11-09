"""Destructive tests only use the existing UUID schema fixture and a fresh temporary root."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from studio import permanent_deletion
from studio.access import session_token_hash
from studio.config import settings
from studio.database import (
    ArtifactRow,
    DatasetRow,
    JobRow,
    MembershipRow,
    ProjectRow,
    PurgeReceiptRow,
    RunRow,
    SessionRow,
    WorkspaceRow,
    now,
)
from studio.storage import checksum
from test_postgres import drain, pg, project, upload  # noqa: F401, F811
from test_reconciliation_postgres import create_approved_run

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_purge(pg, tmp_path, monkeypatch):  # noqa: F811
    client, factory, worker = pg
    with factory() as db:
        database, schema = db.execute(text("SELECT current_database(), current_schema()")).one()
    root = tmp_path / schema
    root.mkdir()
    (root / ".studio-purge-test").write_text(f"{database}:{schema}", encoding="ascii")
    monkeypatch.setattr(settings, "storage_root", root)
    monkeypatch.setattr(settings, "purge_test_schema", schema)
    return client, factory, worker, root


def request_body(client, endpoint):
    response = client.get(endpoint)
    assert response.status_code == 200, response.text
    impact = response.json()
    return {"confirmation": impact["name"], "fingerprint": impact["fingerprint"]}, impact


def test_purge_requires_verified_schema_root_and_owner(isolated_purge, monkeypatch):
    client, factory, _, root = isolated_purge
    pid = project(client)
    endpoint = f"/api/permanent-deletion/project/{pid}"
    assert client.get("/api/permanent-deletion/workspace/demo").json()["code"] == (
        "PURGE_ACTIVE_WORKSPACE"
    )
    with monkeypatch.context() as overrides:
        overrides.setattr(settings, "storage_root", root.parent)
        assert client.get(endpoint).json()["code"] == "PURGE_DISABLED"
    with factory() as db:
        db.add(WorkspaceRow(id="isolated-other", name="Other", policy={}))
        db.flush()
        other = ProjectRow(workspace_id="isolated-other", name="Other", business_scope="test")
        db.add(other)
        db.flush()
        other_id = other.id
        db.commit()
    assert client.get(f"/api/permanent-deletion/project/{other_id}").status_code == 404
    body, _ = request_body(client, endpoint)
    for role in ("viewer", "editor"):
        with factory() as db:
            db.get(MembershipRow, ("demo", "test-owner")).role = role
            db.commit()
        assert client.get(endpoint).status_code == 403
        assert client.post(endpoint, json=body).status_code == 403
    with factory() as db:
        assert db.get(ProjectRow, pid) is not None


def test_purge_source_removes_affected_verified_results_and_preserves_other_source(isolated_purge):
    client, factory, worker, root = isolated_purge
    pid, _, _, queued = create_approved_run((client, factory, worker))
    drain(factory, worker)
    run_id = queued["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "VERIFIED"
    for format_name in ("csv", "xlsx"):
        export = client.post(
            f"/api/runs/{run_id}/exports?format={format_name}",
            headers={"Idempotency-Key": f"purge-fixture-{format_name}"},
        )
        assert export.status_code == 202, export.text
    drain(factory, worker)
    items = client.get(f"/api/datasets?project_id={pid}").json()["items"]
    deleted, kept = (row["id"] for row in items)
    kept_before = client.get(f"/api/datasets/{kept}/artifacts").json()
    kept_raw = client.get(f"/api/datasets/{kept}/download").content
    backup = root / "backups" / "retained"
    backup.parent.mkdir()
    backup.write_text("backup kept", encoding="ascii")
    endpoint = f"/api/permanent-deletion/dataset/{deleted}"
    body, impact = request_body(client, endpoint)
    assert impact["counts"]["reconciliation_runs"] == 1
    assert impact["counts"]["run_exports"] == 2
    assert impact["counts"]["canonical_datasets"] == 1
    assert client.post(endpoint, json={**body, "confirmation": "wrong"}).status_code == 409
    completed = client.post(endpoint, json=body)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "DELETED"
    assert client.post(endpoint, json=body).json() == completed.json()
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/datasets/{deleted}/download").status_code == 404
    assert client.get(f"/api/datasets/{kept}/download").content == kept_raw
    assert client.get(f"/api/datasets/{kept}/artifacts").json() == kept_before
    assert backup.read_text(encoding="ascii") == "backup kept"
    with factory() as db:
        assert db.get(DatasetRow, deleted) is None and db.get(RunRow, run_id) is None
        receipt = db.get(PurgeReceiptRow, body["fingerprint"])
        assert receipt.completed_at and not receipt.files
    assert not any(path.is_file() for path in (root / "demo" / "runs" / run_id).rglob("*"))


@pytest.mark.parametrize("removed_before_failure", [0, 1])
def test_purge_project_recovers_after_partial_file_failure(
    isolated_purge, monkeypatch, removed_before_failure
):
    client, factory, worker, root = isolated_purge
    pid = project(client)
    for raw in (b"id,amount\na,12\n", b"id,amount\nb,8\n"):
        upload(client, pid, raw)
    drain(factory, worker)
    endpoint = f"/api/permanent-deletion/project/{pid}"
    body, impact = request_body(client, endpoint)
    assert impact["counts"]["datasets"] == 2
    original = Path.unlink
    calls = 0

    def interrupted(path, *args, **kwargs):
        nonlocal calls
        if calls >= removed_before_failure:
            raise OSError("synthetic interruption")
        calls += 1
        return original(path, *args, **kwargs)

    with monkeypatch.context() as overrides:
        overrides.setattr(Path, "unlink", interrupted)
        response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DELETING"
    with factory() as db:
        assert db.get(ProjectRow, pid) is None
        remaining = db.get(PurgeReceiptRow, body["fingerprint"]).files
        assert sum((root / path).exists() for path in remaining) == len(remaining) - calls
        permanent_deletion.resume_pending(db)
    assert (
        client.get(f"/api/permanent-deletion-receipts/{body['fingerprint']}").json()["status"]
        == "DELETED"
    )
    assert not any((root / path).exists() for path in remaining)


def test_purge_rejects_busy_changed_and_untracked_files_then_allows_missing(isolated_purge):
    client, factory, worker, root = isolated_purge
    pid = project(client)
    uploaded = upload(client, pid)
    endpoint = f"/api/permanent-deletion/dataset/{uploaded['id']}"
    assert client.get(endpoint).json()["code"] == "PURGE_BUSY"
    with factory() as db:
        claim = worker.claim_job(db)
        assert claim is not None
    assert client.get(endpoint).json()["code"] == "PURGE_BUSY"
    worker.process_job(*claim)
    drain(factory, worker)
    body, _ = request_body(client, endpoint)
    with factory() as db:
        artifact = db.scalar(select(ArtifactRow).where(ArtifactRow.kind == "raw"))
        path = root / artifact.storage_key
        expected = artifact.sha256
    data = path.read_bytes()
    path.write_bytes(b"changed")
    assert client.post(endpoint, json=body).json()["code"] == "PURGE_CHECKSUM"
    path.write_bytes(data)
    assert checksum(path) == expected
    orphan = path.with_name("unpublished")
    orphan.write_bytes(b"not in manifest")
    assert client.get(endpoint).json()["code"] == "PURGE_UNTRACKED_FILE"
    orphan.unlink()
    path.unlink()
    assert client.post(endpoint, json=body).json()["code"] == "PURGE_CONFIRMATION_STALE"
    renewed, impact = request_body(client, endpoint)
    assert impact["missing_files"] == 1
    assert client.post(endpoint, json=renewed).json()["status"] == "DELETED"


def test_purge_concurrent_confirmation_and_upload_serialize(isolated_purge, monkeypatch):
    client, factory, worker, _ = isolated_purge
    pid = project(client)
    endpoint = f"/api/permanent-deletion/project/{pid}"
    body, _ = request_body(client, endpoint)
    locked, release = Event(), Event()
    original = permanent_deletion._manifest

    def pause(*args):
        locked.set()
        assert release.wait(15)
        return original(*args)

    monkeypatch.setattr(permanent_deletion, "_manifest", pause)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(client.post, endpoint, json=body)
        assert locked.wait(15)
        retry = pool.submit(client.post, endpoint, json=body)
        upload_after = pool.submit(
            client.post,
            "/api/datasets/uploads",
            data={"project_id": pid},
            files={"files": ("test.csv", b"id,value\na,1\n", "text/csv")},
        )
        release.set()
        assert first.result(15).json()["status"] == "DELETED"
        assert retry.result(15).json()["status"] == "DELETED"
        assert upload_after.result(15).status_code == 404
    with factory() as db:
        assert not list(db.scalars(select(JobRow)))
        assert len(list(db.scalars(select(PurgeReceiptRow)))) == 1


def test_purge_isolated_workspace_with_projects_and_sessions(isolated_purge):
    client, factory, worker, root = isolated_purge
    kept = project(client)
    previous = client.cookies.get("studio_session")
    workspace_id, token = str(uuid4()), uuid4().hex
    with factory() as db:
        db.add(WorkspaceRow(id=workspace_id, name="Synthetic workspace", policy={}))
        db.flush()
        db.add(MembershipRow(workspace_id=workspace_id, actor_id="isolated-owner", role="owner"))
        db.add(
            SessionRow(
                workspace_id=workspace_id,
                actor_id="isolated-owner",
                token_hash=session_token_hash(token),
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.commit()
    client.cookies.set("studio_session", token)
    for name in ("Synthetic one", "Synthetic two"):
        upload(client, project(client, name), b"id,amount\na,12\n")
        drain(factory, worker)
    endpoint = f"/api/permanent-deletion/workspace/{workspace_id}"
    body, impact = request_body(client, endpoint)
    assert impact["counts"]["projects"] == 2 and impact["counts"]["sessions"] == 1
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DELETED"
    assert client.get("/api/projects").status_code == 401
    client.cookies.set("studio_session", previous)
    assert client.get(f"/api/projects/{kept}").status_code == 200
    assert not any(path.is_file() for path in (root / workspace_id).rglob("*"))
    with factory() as db:
        assert db.get(WorkspaceRow, workspace_id) is None
        assert db.get(WorkspaceRow, "demo") is not None
