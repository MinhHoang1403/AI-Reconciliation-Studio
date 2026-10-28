"""Reuse the existing UUID-schema PostgreSQL harness; no second service or test database."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from studio.database import CanonicalRow, RunRow
from test_postgres import approve, drain, pg, project, upload  # noqa: F401, F811

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("pg", ["create_data_foundation"], indirect=True)
def test_additive_migration_preserves_existing_approved_canonical(pg):  # noqa: F811
    client, factory, worker = pg
    project_id = project(client)
    dataset = upload(client, project_id)
    drain(factory, worker)
    table_id = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"][0]["id"]
    mapping, _ = approve(client, table_id)
    response = client.post(
        f"/api/datasets/{dataset['id']}/normalize",
        json={"mapping_id": mapping["id"]},
        headers={"Idempotency-Key": "migration-canonical"},
    )
    assert response.status_code == 202
    drain(factory, worker)
    before = client.get(f"/api/datasets/{dataset['id']}/artifacts").json()
    assert len(before["canonical_datasets"]) == 1
    command.upgrade(Config("alembic.ini"), "head")
    assert client.get(f"/api/datasets/{dataset['id']}/artifacts").json() == before
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 1
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "create_reconciliation"
    canonical = before["canonical_datasets"][0]
    preview = client.get(
        f"/api/tables/{table_id}/preview",
        params={"kind": "canonical", "canonical_id": canonical["id"]},
    ).json()
    assert preview["total"] == 4
    assert any(row["record_payload"].get("reference_id") == "000123" for row in preview["items"])


def prepare_pair(pg):  # noqa: F811
    from reconciliation_cases import FIXTURES

    client, factory, worker = pg
    pid = project(client, "Synthetic delivery")
    ids = []
    for filename in ("shipments.csv", "delivery-confirmations.csv"):
        raw = (FIXTURES / filename).read_bytes()
        response = client.post(
            "/api/datasets/uploads",
            data={"project_id": pid, "request_ai_mapping": "false"},
            files={"files": (filename, raw, "text/csv")},
        )
        dataset = response.json()["items"][0]
        drain(factory, worker)
        table = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"][0]
        proposal = client.get(f"/api/tables/{table['id']}/mappings").json()["items"][0]
        fields = [
            ("carrier", "string"),
            ("tracking_id", "string"),
            ("event_date", "date"),
            ("delivery_charge", "decimal"),
            ("currency", "string"),
            ("description", "string"),
        ]
        schema = proposal["schema"] | dict(
            entity_kind="delivery",
            grain="delivery",
            business_key_fields=["carrier", "tracking_id"],
            fields=[
                dict(
                    id=f,
                    name=f,
                    data_type=t,
                    required=False,
                    **(
                        dict(
                            semantic_metric="delivery_charge",
                            amount_basis="gross",
                            currency="VND",
                            unit="VND",
                        )
                        if t == "decimal"
                        else {}
                    ),
                )
                for f, t in fields
            ],
        )
        decisions = [
            dict(
                source_field=f"c{i}",
                candidate_target=f,
                decision="APPROVED",
                grain_assumption="delivery",
                evidence_ids=[f"{table['id']}:c{i}"],
                transformation_candidate=dict(op="parse_decimal", locale="en-US")
                if t == "decimal"
                else dict(op="parse_date", format="%Y-%m-%d", timezone="UTC")
                if t == "date"
                else dict(op="cast_string_preserve"),
            )
            for i, (f, t) in enumerate(fields, 1)
        ]
        response = client.post(
            f"/api/mappings/{proposal['id']}/approve",
            json=dict(schema_definition=schema, decisions=decisions, extraction_reviewed=True),
        )
        assert response.status_code == 200, response.text
        response = client.post(
            f"/api/datasets/{dataset['id']}/normalize",
            json={"mapping_id": response.json()["id"]},
            headers={"Idempotency-Key": filename},
        )
        assert response.status_code == 202, response.text
        drain(factory, worker)
        ids.append(
            client.get(f"/api/datasets/{dataset['id']}/artifacts").json()["canonical_datasets"][0][
                "id"
            ]
        )
    from reconciliation_cases import plan

    p = plan(
        left=ids[0],
        right=ids[1],
        platform="",
        amount="delivery_charge",
        metric="delivery_charge",
        keys=["carrier", "tracking_id"],
        entity="delivery",
    )
    return pid, p


def create_approved_run(pg):  # noqa: F811
    client, factory, worker = pg
    pid, p = prepare_pair(pg)
    response = client.post(
        "/api/reconciliation-plans",
        json=dict(project_id=pid, plan=p.model_dump(mode="json")),
        headers={"Idempotency-Key": "delivery-plan"},
    )
    assert response.status_code == 201, response.text
    plan_id = response.json()["id"]
    rule = client.post(f"/api/reconciliation-contracts/{plan_id}/approve")
    assert rule.status_code == 200, rule.text
    response = client.post(
        "/api/reconciliation-runs",
        json={"contract_id": rule.json()["id"]},
        headers={"Idempotency-Key": "delivery-run"},
    )
    assert response.status_code == 202, response.text
    return pid, p, rule.json(), response.json()


def test_T20_T34_T35_rule_approval_snapshot_exports_and_workflow(pg):  # noqa: F811
    import csv
    import io
    from zipfile import ZipFile

    from openpyxl import load_workbook

    client, factory, worker = pg
    pid, p, rule, accepted = create_approved_run(pg)
    rid = accepted["run_id"]
    assert client.get(f"/api/runs/{rid}/metrics").status_code == 409
    from studio.reconciliation_jobs import execute_reconciliation

    with factory() as db:
        claimed = worker.claim_job(db)
    execute_reconciliation(*claimed, factory, worker._fence, worker._finish)
    run = client.get(f"/api/runs/{rid}").json()
    assert run["status"] == "VERIFIED", run
    snapshot = client.get(f"/api/runs/{rid}/metrics").json()
    assert snapshot["monetary"][0]["absolute_variance"] == "2.75"
    assert snapshot["full_match_rate"] == dict(numerator=1, denominator=3, percent="33.33")
    duplicate = client.post(
        "/api/reconciliation-runs",
        json={"contract_id": rule["id"]},
        headers={"Idempotency-Key": "another"},
    ).json()
    assert duplicate["run_id"] == rid
    cases = client.get(f"/api/runs/{rid}/exceptions").json()
    case = next(c for c in cases["items"] if c["type"] == "AMOUNT_MISMATCH")
    assert (
        client.patch(
            f"/api/exceptions/{case['id']}/review",
            json=dict(workflow_state="RESOLVED", notes="Reviewed synthetic delta"),
        ).status_code
        == 200
    )
    assert client.get(f"/api/runs/{rid}/metrics").json() == snapshot
    evidence = client.get(f"/api/runs/{rid}/groups/{case['match_group_id']}/evidence")
    assert evidence.status_code == 200, evidence.text
    assert sum(s["member_count"] for s in evidence.json()["sources"]) == 2
    for format in ("csv", "xlsx"):
        exported = client.post(
            f"/api/runs/{rid}/exports?format={format}", headers={"Idempotency-Key": format}
        )
        assert exported.status_code == 202, exported.text
        drain(factory, worker)
        info = client.get(f"/api/exports/{exported.json()['export_id']}").json()
        assert info["status"] == "SUCCEEDED", info
        downloaded = client.get(info["download_url"])
        assert downloaded.status_code == 200
        if format == "csv":
            rows = list(csv.reader(io.StringIO(downloaded.content.decode("utf-8-sig"))))
            stored = next(r[2] for r in rows if r[:2] == ["Summary", "Snapshot JSON"])
        else:
            book = load_workbook(io.BytesIO(downloaded.content), data_only=False)
            stored = next(r[1].value for r in book["Summary"] if r[0].value == "Snapshot JSON")
            assert all(c.data_type != "f" for sheet in book for row in sheet for c in row)
            with ZipFile(io.BytesIO(downloaded.content)) as archive:
                assert any(
                    b"2.75" in archive.read(n)
                    for n in archive.namelist()
                    if n.startswith("xl/worksheets/")
                )
        import json

        assert json.loads(stored) == snapshot
    assert (
        client.post(
            "/api/reconciliation-runs",
            json={"contract_id": rule["plan"]["left"]["canonical_id"]},
            headers={"Idempotency-Key": "unapproved"},
        ).status_code
        == 404
    )


def test_T33_crash_before_publish_and_failed_verification_no_metrics(pg, monkeypatch):  # noqa: F811
    from studio import reconciliation_jobs

    client, factory, worker = pg
    _, _, _, accepted = create_approved_run(pg)
    original = reconciliation_jobs.write_match_artifact

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic crash")

    monkeypatch.setattr(reconciliation_jobs, "write_match_artifact", fail)
    with factory() as db:
        claim = worker.claim_job(db)
    worker.process_job(*claim)
    assert client.get(f"/api/runs/{accepted['run_id']}/metrics").status_code == 409
    with factory() as db:
        from studio.database import JobRow, now

        job = db.get(JobRow, accepted["job_id"])
        job.available_at = now()
        db.commit()
    monkeypatch.setattr(reconciliation_jobs, "write_match_artifact", original)
    drain(factory, worker)
    assert client.get(f"/api/runs/{accepted['run_id']}/metrics").status_code == 200


def test_failed_verification_blocks_metrics_exports_and_cross_run_evidence(pg, monkeypatch):  # noqa: F811
    from decimal import Decimal

    from studio import reconciliation_jobs

    client, factory, worker = pg
    _, _, _, accepted = create_approved_run(pg)
    original = reconciliation_jobs.match_records

    def corrupt(*args):
        result = original(*args)
        next(g for g in result.groups if g.comparisons).comparisons[0].left_amount = Decimal(
            "99999"
        )
        return result

    monkeypatch.setattr(reconciliation_jobs, "match_records", corrupt)
    drain(factory, worker)
    rid = accepted["run_id"]
    run = client.get(f"/api/runs/{rid}").json()
    assert run["status"] == "VERIFICATION_FAILED" and run["metric_snapshot"] is None
    assert any(not c["passed"] for c in run["checks"])
    assert client.get(f"/api/runs/{rid}/metrics").status_code == 409
    assert (
        client.post(f"/api/runs/{rid}/exports", headers={"Idempotency-Key": "bad"}).status_code
        == 409
    )


def test_reconciliation_permissions_scope_and_template_drift(pg):  # noqa: F811
    from studio.database import CanonicalRow, MembershipRow

    client, factory, worker = pg
    pid, p, rule, accepted = create_approved_run(pg)
    drain(factory, worker)
    rid = accepted["run_id"]
    assert client.get(f"/api/runs/{rid}/groups/not-a-group/evidence").status_code == 404
    other = project(client, "other project")
    response = client.post(
        "/api/reconciliation-plans",
        json=dict(project_id=other, plan=p.model_dump(mode="json")),
        headers={"Idempotency-Key": "foreign"},
    )
    assert response.status_code == 422
    payload = dict(
        left_canonical_id=p.left.canonical_id,
        right_canonical_id=p.right.canonical_id,
        period_start="2026-11-01",
        period_end="2026-12-01",
        left_coverage_start="2026-11-01",
        left_coverage_end="2026-12-01",
        right_coverage_start="2026-11-01",
        right_coverage_end="2026-12-01",
        completeness="CONFIRMED",
        snapshot_at="2026-12-02T00:00:00Z",
    )
    response = client.post(f"/api/reconciliation-contracts/{rule['id']}/reuse", json=payload)
    assert response.status_code == 201, response.text
    assert (
        response.json()["contract_id"] is None
        and response.json()["proposal"]["status"] == "PROPOSED"
    )
    with factory() as db:
        membership = db.get(MembershipRow, ("demo", "test-owner"))
        membership.role = "viewer"
        db.commit()
    response = client.post(
        "/api/reconciliation-runs",
        json={"contract_id": rule["id"]},
        headers={"Idempotency-Key": "viewer"},
    )
    assert response.status_code == 403
    with factory() as db:
        membership = db.get(MembershipRow, ("demo", "test-owner"))
        membership.role = "owner"
        source = db.get(CanonicalRow, p.left.canonical_id)
        source.stale = True
        db.commit()
    assert (
        client.post(
            "/api/reconciliation-runs",
            json={"contract_id": rule["id"]},
            headers={"Idempotency-Key": "stale"},
        ).status_code
        == 422
    )
