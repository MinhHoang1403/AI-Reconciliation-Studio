"""Live, scoped worker crash test against the existing local Compose deployment.

Only a newly created synthetic normalization job is interrupted. The test advances
that job's lease after the kill so it need not wait five minutes. No volumes or
business records are deleted; the synthetic project remains as acceptance evidence.
"""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"QUEUED", "RUNNING", "RETRYABLE_FAILURE"}


def docker(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["docker", *args], cwd=ROOT, check=True, capture_output=capture, text=True, timeout=60
    )
    return result.stdout.strip() if capture else ""


def wait_job(client: httpx.Client, job_id: str, desired: str) -> dict[str, object]:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        if job["status"] == desired:
            return job
        if job["status"] in {"FAILED", "BLOCKED", "CANCELLED"}:
            raise RuntimeError(f"Synthetic job stopped with {job['status']}")
        time.sleep(0.03)
    raise RuntimeError("Synthetic job deadline exceeded")


def main() -> None:
    worker_id = docker("compose", "ps", "-q", "worker", capture=True)
    project = docker(
        "inspect",
        "--format",
        '{{index .Config.Labels "com.docker.compose.project"}}',
        worker_id,
        capture=True,
    )
    if project != "ai-reconciliation-studio":
        raise SystemExit("BLOCKED: unexpected worker project")
    with httpx.Client(
        base_url="http://127.0.0.1:18180", timeout=30, headers={"Origin": "http://127.0.0.1:18180"}
    ) as client:
        client.get("/api/session").raise_for_status()
        created = client.post(
            "/api/projects",
            json={
                "name": "Kiểm tra khôi phục worker",
                "business_scope": "synthetic-recovery-" + uuid4().hex,
            },
        )
        created.raise_for_status()
        project_id = created.json()["id"]
        rows = 75000
        raw = ("Order ID,Gross amount\n" + "".join(f"{i:08d},1.25\n" for i in range(rows))).encode()
        uploaded = client.post(
            "/api/datasets/uploads",
            data={"project_id": project_id},
            files={"files": ("synthetic-recovery.csv", raw, "text/csv")},
        )
        uploaded.raise_for_status()
        dataset = uploaded.json()["items"][0]
        wait_job(client, dataset["job_id"], "SUCCEEDED")
        deadline = time.monotonic() + 90
        while True:
            jobs = client.get(f"/api/jobs?project_id={project_id}").json()["items"]
            if not any(job["status"] in ACTIVE for job in jobs):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Wait for synthetic mapping job before fault injection")
            time.sleep(0.1)
        table = client.get(f"/api/datasets/{dataset['id']}/tables").json()["items"][0]
        proposal = client.get(f"/api/tables/{table['id']}/mappings").json()["items"][0]
        schema = proposal["schema"]
        schema.update(
            entity_kind="synthetic_record",
            grain="one synthetic source row",
            fields=[
                {
                    "id": "reference_id",
                    "name": "Mã tổng hợp",
                    "data_type": "string",
                    "required": True,
                },
                {
                    "id": "amount",
                    "name": "Số tiền tổng hợp",
                    "data_type": "decimal",
                    "required": True,
                    "semantic_metric": "synthetic_amount",
                    "amount_basis": "user_defined",
                    "currency": "VND",
                    "unit": "VND",
                },
            ],
        )
        decisions = [
            {
                "source_field": source,
                "candidate_target": target,
                "decision": "APPROVED",
                "evidence_ids": [f"{table['id']}:{source}"],
                "grain_assumption": schema["grain"],
                "transformation_candidate": transform,
            }
            for source, target, transform in [
                ("c1", "reference_id", {"op": "cast_string_preserve"}),
                ("c2", "amount", {"op": "parse_decimal", "locale": "en-US"}),
            ]
        ]
        approved = client.post(
            f"/api/mappings/{proposal['id']}/approve",
            json={"schema_definition": schema, "decisions": decisions, "extraction_reviewed": True},
        )
        approved.raise_for_status()
        mapping_id = approved.json()["id"]
        queued = client.post(
            f"/api/datasets/{dataset['id']}/normalize",
            json={"mapping_id": mapping_id},
            headers={"Idempotency-Key": uuid4().hex},
        )
        queued.raise_for_status()
        job_id = queued.json()["job_id"]
        wait_job(client, job_id, "RUNNING")
        guard = """import sys
from sqlalchemy import select
from studio.database import SessionFactory,JobRow
with SessionFactory() as db:
    active=list(db.scalars(select(JobRow.id).where(JobRow.status.in_(['QUEUED','RUNNING','RETRYABLE_FAILURE']))))
    assert active==[sys.argv[1]], 'Other jobs active; refuse fault injection'
"""
        docker("compose", "exec", "-T", "backend", "python", "-c", guard, job_id)
        try:
            docker("compose", "kill", "-s", "SIGKILL", "worker")
            expire = """import sys
from datetime import timedelta
from studio.database import SessionFactory,JobRow,now
with SessionFactory() as db:
    job=db.get(JobRow,sys.argv[1])
    assert job is not None and job.kind=='normalize' and job.status=='RUNNING'
    assert job.project_id==sys.argv[2] and job.payload['mapping_id']==sys.argv[3]
    job.lease_until=now()-timedelta(seconds=1)
    db.commit()
"""
            docker(
                "compose",
                "exec",
                "-T",
                "backend",
                "python",
                "-c",
                expire,
                job_id,
                project_id,
                mapping_id,
            )
        finally:
            docker("compose", "start", "worker")
        completed = wait_job(client, job_id, "SUCCEEDED")
        assert completed["attempts"] == 2
        artifacts = client.get(f"/api/datasets/{dataset['id']}/artifacts").json()
        canonical = [
            item
            for item in artifacts["canonical_datasets"]
            if item["mapping_revision_id"] == mapping_id
        ]
        assert (
            len(canonical) == 1
            and canonical[0]["row_count"] == rows
            and canonical[0]["invalid_count"] == 0
        )
        raw_ref = next(item for item in artifacts["items"] if item["kind"] == "raw")
        assert raw_ref["sha256"] == hashlib.sha256(raw).hexdigest()
        assert len([item for item in artifacts["items"] if item["kind"] == "parsed"]) == 1
        result = {
            "status": "PASS",
            "rows": rows,
            "attempts": 2,
            "canonical_count": 1,
            "project_id": project_id,
            "dataset_id": dataset["id"],
            "job_id": job_id,
        }
        output = ROOT / "runtime" / "worker-recovery.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            "PASS live worker recovery: SIGKILL during 75k-row normalization; "
            "expired lease reclaimed; exactly one canonical published"
        )


if __name__ == "__main__":
    main()
