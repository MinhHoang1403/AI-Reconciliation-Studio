"""Reuse the existing UUID-schema PostgreSQL harness; no second service or test database."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from studio.database import AuditRow, CanonicalRow, ReconciliationContractRow, RunRow
from test_postgres import approve, drain, pg, project, upload  # noqa: F401, F811

pytestmark = pytest.mark.integration


def test_canonical_cursor_pages_do_not_limit_explicit_source_validation(pg):  # noqa: F811
    from copy import deepcopy

    client, factory, _ = pg
    pid, plan = prepare_pair(pg)
    expected = {plan.left.canonical_id, plan.right.canonical_id}
    with factory() as db:
        source = db.get(CanonicalRow, plan.left.canonical_id)
        for index in range(201):
            ident = f"0-history-{index:04}"
            revision = f"catalogue-history-{index}"
            contract = deepcopy(source.contract)
            contract.update(id=ident, normalization_revision=revision)
            db.add(
                CanonicalRow(
                    id=ident,
                    workspace_id=source.workspace_id,
                    source_table_id=source.source_table_id,
                    mapping_id=source.mapping_id,
                    normalization_revision=revision,
                    contract=contract,
                    stale=True,
                )
            )
        db.commit()
    url = f"/api/projects/{pid}/canonical-catalogue"
    first = client.get(url).json()
    assert len(first["items"]) == 200
    assert not expected & {item["canonical"]["id"] for item in first["items"]}
    assert first["next_cursor"]
    second = client.get(url, params={"after_id": first["next_cursor"]}).json()
    assert len(second["items"]) == 3 and second["next_cursor"] is None
    assert expected <= {item["canonical"]["id"] for item in second["items"]}
    selected = client.get(
        url, params=[("canonical_ids", ident) for ident in sorted(expected)]
    ).json()
    assert {item["canonical"]["id"] for item in selected["items"]} == expected
    assert selected["next_cursor"] is None
    checked = client.post(
        "/api/reconciliation-plans/validate",
        json={
            "project_id": pid,
            "plan": plan.model_dump(mode="json"),
        },
    )
    assert checked.status_code == 200, checked.text
    foreign = client.post(
        "/api/reconciliation-plans/validate",
        json={
            "project_id": project(client),
            "plan": plan.model_dump(mode="json"),
        },
    )
    assert foreign.status_code == 422
    assert client.get(url, params={"limit": 201}).status_code == 422
    assert client.get(url, params={"after_id": "../outside"}).status_code == 422


def test_approved_templates_are_available_past_the_first_page(pg):  # noqa: F811
    from copy import deepcopy

    from studio.database import PlanRow

    client, factory, _ = pg
    pid, _, rule, _ = create_approved_run(pg)
    with factory() as db:
        original = db.get(ReconciliationContractRow, rule["id"])
        source = db.get(PlanRow, original.plan_id)
        for index in range(101):
            plan_id, rule_id = f"plan-history-{index:04}", f"0-template-{index:04}"
            db.add(
                PlanRow(
                    id=plan_id,
                    workspace_id=source.workspace_id,
                    project_id=pid,
                    proposal=deepcopy(source.proposal),
                    origin=source.origin,
                    created_by=source.created_by,
                )
            )
            db.flush()
            definition = deepcopy(original.definition)
            definition.update(id=rule_id)
            db.add(
                ReconciliationContractRow(
                    id=rule_id,
                    workspace_id=original.workspace_id,
                    project_id=pid,
                    plan_id=plan_id,
                    definition=definition,
                    source_signatures=deepcopy(original.source_signatures),
                )
            )
        db.commit()
    url = f"/api/projects/{pid}/reconciliation-templates"
    first = client.get(url).json()
    assert len(first["items"]) == 100 and first["next_cursor"]
    second = client.get(url, params={"after_id": first["next_cursor"]}).json()
    assert len(second["items"]) == 2 and second["next_cursor"] is None
    assert rule["id"] in {item["id"] for item in second["items"]}


def test_lifecycle_migration_preserves_existing_approved_canonical(pg):  # noqa: F811
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
    config = Config("alembic.ini")
    command.downgrade(config, "create_agent_workflows")
    # Candidate ORM needs the new columns, so inspect the old schema with SQL.
    with factory() as db:
        assert db.scalar(text("SELECT count(*) FROM canonical_datasets")) == 1
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "create_agent_workflows"
        )
    command.upgrade(config, "head")
    assert client.get(f"/api/datasets/{dataset['id']}/artifacts").json() == before
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CanonicalRow)) == 1
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "add_resource_lifecycle"
        )
    canonical = before["canonical_datasets"][0]
    preview = client.get(
        f"/api/tables/{table_id}/preview",
        params={"kind": "canonical", "canonical_id": canonical["id"]},
    ).json()
    assert preview["total"] == 4
    assert any(row["record_payload"].get("reference_id") == "000123" for row in preview["items"])


def prepare_pair(
    pg,  # noqa: F811
    *,
    workbooks=False,
    grouped=False,
    partial=False,
    report_period=None,
    key_display_name=None,
):
    from reconciliation_cases import FIXTURES

    client, factory, worker = pg
    pid = project(client, "Synthetic delivery")
    ids = []
    for filename in ("shipments.csv", "delivery-confirmations.csv"):
        raw = (FIXTURES / filename).read_bytes()
        if partial and filename == "shipments.csv":
            raw = raw.replace(b",25.00,", b",invalid_amount,", 1)
        detail = grouped and filename == "delivery-confirmations.csv"
        grain = "delivery_line" if detail else "delivery"
        if detail:
            raw = raw.replace(
                b"CARRIER-A,000701,2026-10-01,25.00,VND,Parcel A",
                b"CARRIER-A,000701,2026-10-01,10.00,VND,Parcel A\n"
                b"CARRIER-A,000701,2026-10-01,15.00,VND,Parcel A",
            )
        media_type = "text/csv"
        if workbooks:
            import csv
            import io

            from openpyxl import Workbook

            data = list(csv.DictReader(io.StringIO(raw.decode())))
            order = [
                "tracking_id",
                "event_date",
                "delivery_charge",
                "carrier",
                "currency",
                "description",
            ]
            book = Workbook()
            book.active.title = "Notes"
            book.active.append(["Read me"])
            book.active.append(["Synthetic evidence workbook"])
            sheet = book.create_sheet("Deliveries")
            sheet.append(order)
            for item in data:
                sheet.append([item[k] for k in order])
            buffer = io.BytesIO()
            book.save(buffer)
            raw = buffer.getvalue()
            filename += ".xlsx"
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if report_period:
            filename = filename.replace(".csv", f"_{report_period}.csv", 1)
        response = client.post(
            "/api/datasets/uploads",
            data={"project_id": pid, "request_ai_mapping": "false"},
            files={"files": (filename, raw, media_type)},
        )
        dataset = response.json()["items"][0]
        drain(factory, worker)
        tables = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"]
        table = next(t for t in tables if t["sheet"] == "Deliveries") if workbooks else tables[0]
        proposal = client.get(f"/api/tables/{table['id']}/mappings").json()["items"][0]
        fields = [
            ("carrier", "string"),
            ("tracking_id", "string"),
            ("event_date", "date"),
            ("delivery_charge", "decimal"),
            ("currency", "string"),
            ("description", "string"),
        ]
        if workbooks:
            fields = [(f, dict(fields)[f]) for f in order]
        schema = proposal["schema"] | dict(
            entity_kind="delivery",
            grain=grain,
            business_key_fields=["carrier", "tracking_id"],
            fields=[
                dict(
                    id=f,
                    name=key_display_name if key_display_name and f == "tracking_id" else f,
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
                grain_assumption=grain,
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
        cardinality="ONE_TO_MANY" if grouped else "ONE_TO_ONE",
    )
    return pid, p


def create_approved_run(pg, *, workbooks=False, grouped=False):  # noqa: F811
    client, factory, worker = pg
    pid, p = prepare_pair(pg, workbooks=workbooks, grouped=grouped)
    response = client.post(
        "/api/reconciliation-plans",
        json=dict(project_id=pid, plan=p.model_dump(mode="json")),
        headers={"Idempotency-Key": "delivery-plan:" + pid},
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


def test_archiving_sources_retains_verified_run_evidence_and_export(pg):  # noqa: F811
    client, factory, worker = pg
    pid, _, rule, queued = create_approved_run(pg)
    drain(factory, worker)
    rid = queued["run_id"]
    metrics = client.get(f"/api/runs/{rid}/metrics").json()
    groups = client.get(f"/api/runs/{rid}/matches").json()
    group_id = next(g["id"] for g in groups["items"] if g["linkage_state"] == "LINKED")
    evidence_url = f"/api/runs/{rid}/groups/{group_id}/evidence"
    evidence = client.get(evidence_url)
    assert evidence.status_code == 200
    export = client.post(
        f"/api/runs/{rid}/exports?format=xlsx", headers={"Idempotency-Key": "lifecycle-export"}
    ).json()
    drain(factory, worker)
    download = client.get(f"/api/exports/{export['export_id']}").json()["download_url"]
    export_before = client.get(download).content
    did = client.get(f"/api/datasets?project_id={pid}").json()["items"][0]["id"]
    endpoint = f"/api/datasets/{did}/lifecycle"
    impact = client.get(endpoint).json()
    assert impact["references"]["runs"] == 1
    assert impact["references"]["exports"] == 1
    assert impact["allowed"] == ["archive"]
    archive = {"action": "archive", "expected_state": "active", "expected_version": 0}
    assert client.post(endpoint, json=archive).json()["state"] == "archived"
    blocked = client.post(
        "/api/reconciliation-runs",
        json={"contract_id": rule["id"]},
        headers={"Idempotency-Key": "archived-source"},
    )
    assert blocked.status_code == 409
    assert client.post(
        f"/api/projects/{pid}/lifecycle", json={**archive, "confirmation": "Synthetic delivery"}
    ).json()["state"] == "archived"
    assert client.get(f"/api/runs/{rid}/metrics").json() == metrics
    assert client.get(evidence_url).json() == evidence.json()
    assert client.get(download).content == export_before


def test_owner_mapping_reuse_checks_full_table_and_records_original_approval(pg):  # noqa: F811
    from reconciliation_cases import FIXTURES
    from studio.database import JobRow, MappingRow, MembershipRow

    client, factory, worker = pg
    pid, plan = prepare_pair(pg)
    with factory() as db:
        original = db.get(CanonicalRow, plan.left.canonical_id)
        original_mapping_id = original.mapping_id
        original_decision = db.get(MappingRow, original_mapping_id).decision
        db.get(MembershipRow, ("demo", "test-owner")).role = "editor"
        db.commit()
    policy_path = f"/api/mappings/{original_mapping_id}/reuse-policy"
    enable = {"enabled": True, "expected_enabled": False}
    assert client.patch(policy_path, json=enable).status_code == 403
    with factory() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "owner"
        db.commit()
    assert client.patch(policy_path, json=enable).json() == {"enabled": True}
    assert client.patch(policy_path, json=enable).status_code == 409
    raw = (FIXTURES / "shipments.csv").read_bytes()

    def repeat(data, filename="shipments.csv"):
        response = client.post(
            "/api/datasets/uploads",
            data={"project_id": pid, "request_ai_mapping": "false"},
            files={"files": (filename, data, "text/csv")},
        )
        assert response.status_code == 202, response.text
        item = response.json()["items"][0]
        drain(factory, worker)
        return item["id"]

    new_id = repeat(raw.replace(b"Parcel A", b"Parcel A this month"))
    canonical = client.get(f"/api/datasets/{new_id}/artifacts").json()["canonical_datasets"]
    assert len(canonical) == 1 and canonical[0]["quality_status"] == "READY"
    applied_mapping_id = canonical[0]["mapping_revision_id"]
    with factory() as db:
        applied = db.get(MappingRow, applied_mapping_id).decision
        assert applied["approved_by"] == original_decision["approved_by"]
        assert applied["approved_at"] == original_decision["approved_at"]
        assert db.get(MappingRow, original_mapping_id).decision == original_decision
        event = db.scalar(select(AuditRow).where(AuditRow.resource_id == applied_mapping_id))
        assert event.action == "APPLY_APPROVED_MAPPING" and event.actor_id == "system"
        job = db.scalar(select(JobRow).where(JobRow.kind == "mapping_reuse"))
        assert job.result["template_mapping_id"] == original_mapping_id

    wrong_currency = repeat(raw.replace(b",VND,Parcel A", b",USD,Parcel changed"))
    assert not client.get(f"/api/datasets/{wrong_currency}/artifacts").json()["canonical_datasets"]
    wrong_name = repeat(raw.replace(b"Parcel A", b"Parcel A from another report"), "other.csv")
    assert not client.get(f"/api/datasets/{wrong_name}/artifacts").json()["canonical_datasets"]
    assert client.patch(policy_path, json={"enabled": False, "expected_enabled": True}).json() == {
        "enabled": False
    }
    revoked = repeat(raw.replace(b"Parcel A", b"Parcel A after revocation"))
    assert not client.get(f"/api/datasets/{revoked}/artifacts").json()["canonical_datasets"]


@pytest.mark.parametrize(
    "change", ["period", "reorder", "description", "combined", "approved-label"]
)
def test_mapping_reuse_rebinds_period_and_column_positions_without_new_approval(pg, change):  # noqa: F811
    import csv
    import io

    from reconciliation_cases import FIXTURES
    from studio.database import MappingRow

    client, factory, worker = pg
    pid, plan = prepare_pair(
        pg,
        report_period="2026_10",
        key_display_name="Shipment identifier" if change == "approved-label" else None,
    )
    with factory() as db:
        original = db.get(CanonicalRow, plan.left.canonical_id)
        mapping_id = original.mapping_id
        approval = db.get(MappingRow, mapping_id).decision
    assert (
        client.patch(
            f"/api/mappings/{mapping_id}/reuse-policy",
            json={"enabled": True, "expected_enabled": False},
        ).status_code
        == 200
    )
    records = list(csv.DictReader(io.StringIO((FIXTURES / "shipments.csv").read_text())))
    fields = list(records[0])
    if change == "approved-label":
        fields = ["Shipment identifier" if field == "tracking_id" else field for field in fields]
        for row in records:
            row["Shipment identifier"] = row.pop("tracking_id")
    if change in {"reorder", "combined"}:
        fields = list(reversed(fields))
    if change in {"description", "combined"}:
        fields.insert(0, "Ghi chú")
        for row in records:
            row["Ghi chú"] = "Kỳ mới, dữ liệu tổng hợp"
    for row in records:
        row["description"] += " next period"
        row["event_date"] = row["event_date"].replace("2026-10", "2026-11")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    period = "2026_11" if change in {"period", "combined"} else "2026_10"
    uploaded = client.post(
        "/api/datasets/uploads",
        data={"project_id": pid, "request_ai_mapping": "false"},
        files={"files": (f"shipments_{period}.csv", output.getvalue().encode(), "text/csv")},
    )
    assert uploaded.status_code == 202, uploaded.text
    dataset_id = uploaded.json()["items"][0]["id"]
    drain(factory, worker)
    artifacts = client.get(f"/api/datasets/{dataset_id}/artifacts").json()
    assert len(artifacts["canonical_datasets"]) == 1, artifacts
    canonical = artifacts["canonical_datasets"][0]
    assert canonical["quality_status"] == "READY"
    with factory() as db:
        applied = db.get(MappingRow, canonical["mapping_revision_id"]).decision
        assert applied["approved_by"] == approval["approved_by"]
        assert applied["approved_at"] == approval["approved_at"]
        assert applied["source_signature"] != approval["source_signature"] or change == "period"
        assert db.get(MappingRow, mapping_id).decision == approval
    preview = client.get(
        f"/api/tables/{canonical['source_table_id']}/preview",
        params={"kind": "canonical", "canonical_id": canonical["id"]},
    ).json()
    first = preview["items"][0]["record_payload"]
    assert first["tracking_id"] == "000701"
    assert first["delivery_charge"] == "25.00"
    assert first["currency"] == "VND"


def test_manual_approval_requires_explicit_confirmation_for_invalid_rows(pg):  # noqa: F811
    client, factory, _ = pg
    pid, plan = prepare_pair(pg, partial=True)
    sources = client.get(f"/api/projects/{pid}/canonical-catalogue").json()["items"]
    assert any(c["canonical"]["quality_status"] == "PARTIAL" for c in sources)
    saved = client.post(
        "/api/reconciliation-plans",
        json={"project_id": pid, "plan": plan.model_dump(mode="json")},
        headers={"Idempotency-Key": "manual-partial-rule"},
    )
    assert saved.status_code == 201, saved.text
    endpoint = f"/api/reconciliation-contracts/{saved.json()['id']}/approve"
    for options in ({}, {"json": {"invalid_rows_reviewed": False}}):
        blocked = client.post(endpoint, **options)
        assert blocked.status_code == 422, blocked.text
        assert blocked.json()["code"] == "INVALID_ROWS_REVIEW_REQUIRED"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 0
    approved = client.post(endpoint, json={"invalid_rows_reviewed": True})
    assert approved.status_code == 200, approved.text
    assert client.post(endpoint).json() == approved.json()
    with factory() as db:
        events = (
            select(func.count())
            .select_from(AuditRow)
            .where(
                AuditRow.action == "RECONCILIATION_INVALID_ROWS_REVIEWED",
                AuditRow.resource_id == approved.json()["id"],
            )
        )
        assert db.scalar(events) == 1


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
    preparation = client.get(f"/api/projects/{pid}/summary").json()
    assert preparation["latest_verified_run_id"] == rid
    assert preparation["ready_canonical_count"] == 2
    assert preparation["preparation_action"]["kind"] == "RECONCILE"
    snapshot = client.get(f"/api/runs/{rid}/metrics").json()
    assert (
        client.get(
            "/api/runs", params={"project_id": pid, "source_id": p.left.canonical_id}
        ).json()["total"]
        == 1
    )
    assert (
        client.get("/api/runs", params={"project_id": pid, "period_start": "2026-11-01"}).json()[
            "total"
        ]
        == 0
    )
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
    summary = next(g for g in cases["groups"] if g["id"] == case["match_group_id"])
    assert summary["comparisons"][0]["left_amount"] == "12.75"
    assert summary["comparisons"][0]["right_amount"] == "10.00"
    assert summary["comparisons"][0]["delta"] == "2.75"
    assert summary["key"]
    bounded = client.get(f"/api/runs/{rid}/exceptions?limit=1").json()
    assert len(bounded["items"]) == len(bounded["groups"]) == 1
    assert bounded["groups"][0]["id"] == bounded["items"][0]["match_group_id"]
    selected_case = client.get(f"/api/runs/{rid}/exceptions", params={"case_id": case["id"]}).json()
    assert selected_case["total"] == 1
    assert selected_case["items"][0]["id"] == case["id"]
    assert client.get(f"/api/runs/{rid}/exceptions?case_id=nonexistent").json()["items"] == []
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


def test_planner_accepts_sources_without_keys_but_cannot_execute(pg):  # noqa: F811
    from studio.database import PlanRow

    client, factory, worker = pg
    pid, p = prepare_pair(pg)
    response = client.post(
        "/api/reconciliation-plans/ai",
        json=dict(
            project_id=pid,
            request=dict(
                left={"canonical_id": p.left.canonical_id},
                right={"canonical_id": p.right.canonical_id},
                intent="Suggest keys between these sources",
            ),
        ),
        headers={"Idempotency-Key": "no-keys"},
    )
    assert response.status_code == 202, response.text
    # No worker/provider execution: a queued proposal grants no execution authority.
    assert (
        client.post(
            "/api/reconciliation-runs",
            json={"contract_id": response.json()["job_id"]},
            headers={"Idempotency-Key": "not-approved"},
        ).status_code
        == 404
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0
        row = PlanRow(
            workspace_id="demo",
            project_id=pid,
            origin="GEMINI",
            created_by="test-owner",
            proposal={
                "status": "NEEDS_REVIEW",
                "plan": None,
                "missing_requirements": ["Confirm coverage"],
            },
        )
        db.add(row)
        db.commit()
        plan_id = row.id
    denied = client.post(f"/api/reconciliation-contracts/{plan_id}/approve")
    assert denied.status_code == 422 and denied.json()["code"] == "PLAN_NEEDS_REVIEW"


def test_incompatible_planner_metadata_is_deterministic_review_without_provider_trace(
    pg,  # noqa: F811
    monkeypatch,
):
    from studio import reconciliation_jobs
    from studio.database import JobRow, PlanRow, TraceRow

    client, factory, worker = pg
    pid, plan = prepare_pair(pg)
    original = reconciliation_jobs.selected_catalogue

    def incompatible(*args, **kwargs):
        sources = original(*args, **kwargs)
        money = next(f for f in sources[1].schema_definition.fields if f.data_type == "decimal")
        money.amount_basis = "net"  # Synthetic scoped metadata, not a historical DB edit.
        return sources

    def forbidden(*args, **kwargs):
        pytest.fail("No provider or inference reservation for known incompatible metadata")

    monkeypatch.setattr(reconciliation_jobs, "selected_catalogue", incompatible)
    monkeypatch.setattr(reconciliation_jobs, "GeminiProvider", forbidden)
    queued = client.post(
        "/api/reconciliation-plans/ai",
        json={
            "project_id": pid,
            "request": {
                "left": {"canonical_id": plan.left.canonical_id},
                "right": {"canonical_id": plan.right.canonical_id},
            },
        },
        headers={"Idempotency-Key": "incompatible-metadata-no-provider"},
    )
    assert queued.status_code == 202
    drain(factory, worker)
    with factory() as db:
        job = db.get(JobRow, queued.json()["job_id"])
        assert job.status == "SUCCEEDED" and job.result["source"] == "DETERMINISTIC"
        proposal = db.get(PlanRow, job.result["plan_id"])
        assert proposal.origin == "DETERMINISTIC" and proposal.proposal["status"] == "NEEDS_REVIEW"
        assert proposal.proposal["plan"] is None and proposal.proposal["missing_requirements"]
        assert db.scalar(select(TraceRow.id).where(TraceRow.job_id == job.id)) is None


@pytest.mark.parametrize("entry", ["scoped", "legacy", "chat"])
def test_planner_scoped_candidate_or_missing_plan_review(pg, monkeypatch, entry):  # noqa: F811
    from studio import reconciliation_jobs
    from studio.access import Actor
    from studio.agent_tools import PlanAction, execute_tool
    from studio.contracts.assistant import AssistantContext
    from studio.contracts.reconciliation import PlanningRequest
    from studio.errors import DomainError

    client, factory, worker = pg
    pid, rule = prepare_pair(pg)
    calls = []

    def missing_plan(*_args):
        calls.append(True)
        raise DomainError("AI_PLAN_MISSING", "Synthetic provider did not propose a plan.")

    monkeypatch.setattr(reconciliation_jobs, "propose_plan", missing_plan)
    request = (
        PlanningRequest.from_plan(rule).model_dump(mode="json")
        if entry == "scoped"
        else {
            "left": {"canonical_id": rule.left.canonical_id},
            "right": {"canonical_id": rule.right.canonical_id},
        }
    )
    if entry == "chat":
        with factory() as db:
            ref = execute_tool(
                db,
                Actor("test-owner", "demo", "owner"),
                PlanAction(
                    name="prepare_reconciliation_plan",
                    context=AssistantContext(project_id=pid),
                    request=PlanningRequest.model_validate(request),
                ),
                "deterministic-plan-or-review",
            )
            db.commit()
            job_id = ref.job_id
    else:
        queued = client.post(
            "/api/reconciliation-plans/ai",
            json={"project_id": pid, "request": request},
            headers={"Idempotency-Key": "deterministic-plan-or-review"},
        )
        assert queued.status_code == 202, queued.text
        job_id = queued.json()["job_id"]
    drain(factory, worker)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "SUCCEEDED" and job["result"]["source"] == "DETERMINISTIC"
    plan_id = job["result"]["plan_id"]
    draft = client.get(f"/api/reconciliation-plans/{plan_id}").json()["proposal"]
    if entry == "scoped":
        assert not calls
        assert draft["status"] == "PROPOSED"
        assert {key["left"] for key in draft["plan"]["join_keys"]} == {"carrier", "tracking_id"}
    else:
        assert calls == ([True] if entry == "legacy" else [])
        assert draft["status"] == "NEEDS_REVIEW" and draft["plan"] is None
        assert job["result"].get("provider_error_code") == (
            "AI_PLAN_MISSING" if entry == "legacy" else None
        )
        assert "period_start" in draft["missing_requirements"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ReconciliationContractRow)) == 0
        assert db.scalar(select(func.count()).select_from(RunRow)) == 0


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_export_first_generation_is_immutable_after_review(pg, format):  # noqa: F811
    import csv
    import io

    from openpyxl import load_workbook

    client, factory, worker = pg
    _, _, _, accepted = create_approved_run(pg)
    drain(factory, worker)
    rid = accepted["run_id"]
    snapshot = client.get(f"/api/runs/{rid}/metrics").json()
    endpoint = f"/api/runs/{rid}/exports?format={format}"
    created = client.post(endpoint, headers={"Idempotency-Key": "first"}).json()
    drain(factory, worker)
    info = client.get(f"/api/exports/{created['export_id']}").json()
    before = client.get(info["download_url"]).content
    assert info["review_state_scope"] == "FIRST_GENERATION" and info["review_state_as_of"]
    if format == "csv":
        rows = list(csv.reader(io.StringIO(before.decode("utf-8-sig"))))
        summary = {r[1]: r[2] for r in rows if r[0] == "Summary"}
        states = [r[4] for r in rows if r[0] == "Exceptions"][1:]
    else:
        book = load_workbook(io.BytesIO(before))
        summary = dict(book["Summary"].values)
        states = [r[3] for r in list(book["Exceptions"].values)[1:]]
    assert summary["Report generated at"] == info["review_state_as_of"]
    assert "FIRST_GENERATION" in summary["Review state scope"]
    assert set(states) == {"OPEN"}
    case = client.get(f"/api/runs/{rid}/exceptions").json()["items"][0]
    assert (
        client.patch(
            f"/api/exceptions/{case['id']}/review",
            json={"workflow_state": "RESOLVED", "notes": "Reviewed after immutable export"},
        ).status_code
        == 200
    )
    second = client.post(endpoint, headers={"Idempotency-Key": "again"}).json()
    assert second["export_id"] == created["export_id"]
    assert client.get(info["download_url"]).content == before
    assert client.get(f"/api/runs/{rid}/metrics").json() == snapshot


def test_readiness_duplicates_use_engine_period_partition(pg, monkeypatch):  # noqa: F811
    from datetime import UTC, datetime

    from reconciliation_cases import records
    from studio import reconciliation_api

    client, _, _ = pg
    pid, p = prepare_pair(pg)
    rows = records("shipments.csv")
    earlier = rows[0].model_copy(deep=True)
    earlier.id = "earlier"
    earlier.payload["event_date"] = datetime(2026, 9, 20, tzinfo=UTC)
    monkeypatch.setattr(
        reconciliation_api, "load_canonical_records", lambda *args: [*rows, earlier]
    )
    response = client.post(
        "/api/reconciliation-plans/validate",
        json=dict(project_id=pid, plan=p.model_dump(mode="json")),
    )
    assert response.status_code == 200, response.text
    assert response.json()["sources"][0]["duplicate_key_rows"] == 0
    assert response.json()["sources"][0]["out_of_scope_records"] == 1
    duplicate = rows[0].model_copy(deep=True)
    duplicate.id = "duplicate-in-period"
    missing_date = rows[0].model_copy(deep=True)
    missing_date.id, missing_date.payload["event_date"] = "missing-date", None
    invalid_key = rows[0].model_copy(deep=True)
    invalid_key.id, invalid_key.payload["tracking_id"] = "invalid-key", ""
    outside = rows[0].model_copy(deep=True)
    outside.id, outside.payload["carrier"] = "other-carrier", "OTHER"
    all_rows = [*rows, earlier, duplicate, missing_date, invalid_key, outside]
    monkeypatch.setattr(reconciliation_api, "load_canonical_records", lambda *args: all_rows)
    for slot in (p.left, p.right):
        slot.filters, slot.completeness = {"carrier": "CARRIER-A"}, "INCOMPLETE"
    p.allow_partial = True
    response = client.post(
        "/api/reconciliation-plans/validate",
        json=dict(project_id=pid, plan=p.model_dump(mode="json")),
    )
    source = response.json()["sources"][0]
    assert source["duplicate_key_rows"] == 1 and source["in_scope_records"] == 4
    assert source["invalid_records"] == 2 and source["out_of_scope_records"] == 2
    assert source["coverage_complete"] is False and source["duplicate_population"] == "IN_SCOPE"


def test_planner_exhausted_durable_budget_no_cloud_manual_fallback(pg, monkeypatch):  # noqa: F811
    import httpx
    from pydantic import SecretStr
    from studio import reconciliation_jobs
    from studio.ai_gateway import GeminiProvider
    from studio.config import settings
    from studio.database import AuditRow, JobRow, WorkspaceRow

    client, factory, worker = pg
    pid, p = prepare_pair(pg)
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", 10)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic-test-key"))
    with factory() as db:
        workspace = db.get(WorkspaceRow, "demo")
        workspace.policy = workspace.policy | dict(
            mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=10
        )
        for i in range(10):
            db.add(
                AuditRow(
                    workspace_id="demo",
                    actor_id="test-owner",
                    action="GEMINI_REQUEST_RESERVED",
                    resource_id=str(i),
                )
            )
        db.commit()
    calls = []

    def handle(request):
        calls.append(request)
        pytest.fail("Exhausted budget must never call a provider")

    provider = GeminiProvider(settings, httpx.Client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(reconciliation_jobs, "GeminiProvider", lambda config: provider)
    response = client.post(
        "/api/reconciliation-plans/ai",
        json=dict(
            project_id=pid,
            request=dict(
                left={"canonical_id": p.left.canonical_id},
                right={"canonical_id": p.right.canonical_id},
            ),
        ),
        headers={"Idempotency-Key": "exhausted-planning"},
    )
    assert response.status_code == 202, response.text
    drain(factory, worker)
    with factory() as db:
        job = db.get(JobRow, response.json()["job_id"])
        assert job.status == "BLOCKED" and job.error_code == "CLOUD_BUDGET_EXHAUSTED"
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "GEMINI_REQUEST_RESERVED")
            )
            == 10
        )
    assert calls == []
    manual = client.post(
        "/api/reconciliation-plans",
        json=dict(project_id=pid, plan=p.model_dump(mode="json")),
        headers={"Idempotency-Key": "manual-after-budget"},
    )
    assert manual.status_code == 201, manual.text


def test_source_evidence_real_columns_multisheet_prefix_and_viewer(pg):  # noqa: F811
    from studio.database import MembershipRow

    client, factory, worker = pg
    _, _, _, accepted = create_approved_run(pg, workbooks=True, grouped=True)
    drain(factory, worker)
    rid = accepted["run_id"]
    group = client.get(f"/api/runs/{rid}/matches?comparison=AMOUNT_MISMATCH").json()["items"][0]
    _, _, _, foreign = create_approved_run(pg)
    drain(factory, worker)
    foreign_group = client.get(f"/api/runs/{foreign['run_id']}/matches").json()["items"][0]
    assert client.get(f"/api/runs/{rid}/groups/{foreign_group['id']}/evidence").status_code == 404
    with factory() as db:
        db.get(MembershipRow, ("demo", "test-owner")).role = "viewer"
        db.commit()
    evidence = client.get(f"/api/runs/{rid}/groups/{group['id']}/evidence").json()
    for source, amount in zip(evidence["sources"], ("12.75", "10.00"), strict=True):
        record = source["records"][0]
        refs = record["field_evidence"]
        assert refs["tracking_id"][0]["column"] == "c1"
        ref = refs["delivery_charge"][0]
        assert ref["column"] == "c3" and ref["sheet"] == "Deliveries"
        raw = client.get(f"/api/evidence/{ref['id']}", params={"row": ref["row"]}).json()
        assert raw["sheet"] == "Deliveries" and raw["items"][0]["c3"] == amount
        id_ref = refs["tracking_id"][0]
        raw_id = client.get(f"/api/evidence/{id_ref['id']}", params={"row": id_ref["row"]}).json()
        assert raw_id["items"][0]["c1"] == "000702"
    linked = client.get(f"/api/runs/{rid}/matches?comparison=EQUAL").json()["items"][0]
    grouped_evidence = client.get(f"/api/runs/{rid}/groups/{linked['id']}/evidence").json()
    assert [s["member_count"] for s in grouped_evidence["sources"]] == [1, 2]
    refs = [
        r["field_evidence"]["delivery_charge"][0] for r in grouped_evidence["sources"][1]["records"]
    ]
    assert len({ref["row"] for ref in refs}) == 2
    assert {
        client.get(f"/api/evidence/{ref['id']}", params={"row": ref["row"]}).json()["items"][0][
            "c3"
        ]
        for ref in refs
    } == {"10.00", "15.00"}
    assert (
        client.patch(
            "/api/exceptions/nonexistent/review",
            json={"workflow_state": "RESOLVED", "notes": "viewer denied"},
        ).status_code
        == 403
    )


def test_planner_unlimited_reserves_beyond_historical_ceiling(pg, monkeypatch):  # noqa: F811
    from pydantic import SecretStr
    from sqlalchemy import func
    from studio import reconciliation_jobs
    from studio.config import settings
    from studio.database import AuditRow, TraceRow, WorkspaceRow
    from studio.errors import DomainError

    client, factory, worker = pg
    pid, plan = prepare_pair(pg)
    monkeypatch.setattr(settings, "allow_external_ai", True)
    monkeypatch.setattr(settings, "external_ai_request_budget", None)
    monkeypatch.setattr(settings, "planner_request_budget", None)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("synthetic"))
    with factory() as db:
        row = db.get(WorkspaceRow, "demo")
        row.policy = dict(
            row.policy, mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=None
        )
        for i in range(31):
            db.add(
                AuditRow(
                    workspace_id="demo",
                    actor_id="test-owner",
                    action="RECONCILIATION_PLANNER_ATTEMPT",
                    resource_id=f"historical-{i}",
                )
            )
        db.commit()
    attempts = []

    def propose(provider, catalogue, draft, policy, reserve, *args):
        attempts.append(reserve())
        raise DomainError("GEMINI_UNAVAILABLE", "Synthetic provider unavailable after reservation")

    monkeypatch.setattr(reconciliation_jobs, "propose_plan", propose)
    response = client.post(
        "/api/reconciliation-plans/ai",
        json={
            "project_id": pid,
            "request": {
                "left": {"canonical_id": plan.left.canonical_id},
                "right": {"canonical_id": plan.right.canonical_id},
            },
        },
        headers={"Idempotency-Key": "unlimited-planner"},
    )
    assert response.status_code == 202
    assert (
        client.post(
            "/api/reconciliation-plans/ai",
            json={
                "project_id": pid,
                "request": {
                    "left": {"canonical_id": plan.left.canonical_id},
                    "right": {"canonical_id": plan.right.canonical_id},
                },
            },
            headers={"Idempotency-Key": "unlimited-planner"},
        ).json()
        == response.json()
    )
    drain(factory, worker)
    assert attempts == [True]
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == "RECONCILIATION_PLANNER_ATTEMPT")
            )
            == 32
        )
        trace = db.scalar(select(TraceRow).where(TraceRow.job_id == response.json()["job_id"]))
        assert trace.outcome == "GEMINI_UNAVAILABLE"
