"""Replay the frozen held-out fixture over the verified local TEST application."""

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:18180"
FIXTURE = ROOT / "tests/fixtures/agent-workflow-heldout.json"
COUNTS = dict(
    intent_slots=30,
    multi_turn=20,
    data_mapping=20,
    plan_reconcile=20,
    analysis_export=20,
    adversarial_recovery=20,
)
EXPECTED_STATES = dict(
    CLARIFY="WAITING_REVIEW", RECONCILE_DATASETS="WAITING_REVIEW", UNSUPPORTED="BLOCKED"
)


def verify_test_scope(schema: str, gemini: bool) -> None:
    if not re.fullmatch(r"test_[0-9a-f]{32}", schema):
        raise SystemExit("A UUID TEST schema is required.")
    probe = (
        "from studio.config import settings; from studio.database import SessionFactory; "
        "from studio.permanent_deletion import purge_root; "
        "assert not settings.allow_cloud_parsing and not settings.ollama_url; "
        + (
            "assert settings.allow_external_ai and settings.agent_cloud_enabled "
            "and settings.gemini_api_key.get_secret_value(); "
            if gemini
            else "assert not settings.allow_external_ai; "
        )
        + "print(purge_root(SessionFactory()).name)"
    )
    actual = subprocess.check_output(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", probe],
        cwd=ROOT,
        text=True,
    ).strip()
    if actual != schema:
        raise SystemExit("The running backend does not match the requested TEST schema.")


def ask(client: httpx.Client, conversation: str, context: dict, goal: str, gemini: bool) -> dict:
    response = client.post(
        "/api/assistant/messages",
        json=dict(
            conversation_id=conversation,
            context=context,
            mode="AGENT",
            text=goal,
            **({"model_choice": "GEMINI"} if gemini else {}),
        ),
        headers={"Idempotency-Key": str(uuid4())},
    )
    if response.status_code != 202:
        return {"http": response.status_code, "error": response.json().get("code")}
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + (130 if gemini else 40)
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").raise_for_status().json()
        if job["status"] in {"FAILED", "BLOCKED", "CANCELLED"}:
            return {"job_status": job["status"], "error": job.get("error_code")}
        if job["status"] == "SUCCEEDED":
            items = client.get(f"/api/conversations/{conversation}").raise_for_status().json()
            workflow_id = next(
                (
                    item["workflow_id"]
                    for item in items["items"]
                    if item["job_id"] == job_id and item.get("workflow_id")
                ),
                None,
            )
            if workflow_id:
                flow = client.get(f"/api/agent/workflows/{workflow_id}").raise_for_status().json()
                if flow["state"] not in {"CREATED", "RUNNING"}:
                    return flow
        time.sleep(0.35)
    return {"error": "BENCHMARK_DEADLINE"}


def export_readback(client: httpx.Client, block: dict, entry: dict, file_format: str) -> bool:
    if block["run_id"] != entry["run_id"] or block["format"] != file_format:
        return False
    export_id = block["export_id"]
    info = client.get(f"/api/exports/{export_id}").raise_for_status().json()
    data = client.get(f"/api/exports/{export_id}/download").raise_for_status().content
    if hashlib.sha256(data).hexdigest() != info["sha256"]:
        return False
    if file_format == "csv":
        rows = csv.reader(io.StringIO(data.decode("utf-8-sig")))
        stored = next((r[2] for r in rows if r[:2] == ["Summary", "Snapshot JSON"]), "null")
    else:
        book = load_workbook(io.BytesIO(data), data_only=False)
        if any(cell.data_type == "f" for sheet in book for row in sheet for cell in row):
            return False
        stored = next(
            (row[1].value for row in book["Summary"] if row[0].value == "Snapshot JSON"), "null"
        )
    return bool(json.loads(stored) == entry["snapshot"])


def measure(case: dict, oracle: dict, gemini: bool) -> dict[str, Any]:
    started = time.monotonic()
    context = {"project_id": oracle["project_id"]}
    source = oracle["sources"].get(case.get("source"))
    run = oracle["runs"].get(case.get("run"))
    if source:
        context["dataset_id"] = source["dataset_id"]
    if run:
        context["run_id"] = run["run_id"]
    with httpx.Client(base_url=ORIGIN, headers={"Origin": ORIGIN}, timeout=15) as client:
        client.get("/api/session").raise_for_status()
        response = client.post(
            "/api/conversations",
            json={"context": context},
            headers={"Idempotency-Key": str(uuid4())},
        )
        conversation = response.raise_for_status().json()["id"]
        if case.get("setup"):
            setup = ask(client, conversation, context, case["setup"], gemini)
            if setup.get("state") != "COMPLETED":
                return dict(ok=False, error="SETUP_FAILED", cause=setup.get("error"))
        flow = ask(client, conversation, context, case["goal"], gemini)
        detail = flow.get("detail", {})
        intent = detail.get("intent") or {}
        query = intent.get("query") or {}
        blocks = detail.get("blocks", [])
        expected = case["intent"]
        checks = dict(
            intent=intent.get("intent") == expected,
            task_state=flow.get("state") == EXPECTED_STATES.get(expected, "COMPLETED"),
        )
        if expected == "UNSUPPORTED":
            checks["no_tool_writes"] = not detail.get("steps")
        if layer := case.get("layer"):
            checks["source"] = (
                query.get("source_kind") == layer
                and query.get("source_id")
                == source["canonical_id" if layer == "CANONICAL" else "table_id"]
            )
            checks["table_published"] = any(b["type"] == "table" for b in blocks)
        if filter_value := case.get("filter"):
            checks["filter"] = any(f["value"] == filter_value for f in query.get("filters", []))
            checks["run"] = query.get("source_id") == context["run_id"]
        if equality := case.get("equality"):
            checks["exact_value"] = query.get("limit") == equality["limit"] and any(
                f["value"] == equality["value"] and f["op"] == "eq"
                for f in query.get("filters", [])
            )
        if pair := case.get("pair"):
            plan = intent.get("planning_request") or {}
            checks["pair_order"] = [
                plan.get(side, {}).get("canonical_id") for side in ("left", "right")
            ] == [oracle["sources"][name]["canonical_id"] for name in pair]
            checks["requires_approval"] = not detail.get("confirmed_contract_id")
        if file_format := case.get("format"):
            checks["export_scope"] = (
                intent.get("run_id") == context["run_id"]
                and intent.get("export_format") == file_format
            )
            downloads = [b for b in blocks if b["type"] == "download"]
            checks["export_readback"] = len(downloads) == 1 and export_readback(
                client, downloads[0], run, file_format
            )
        return dict(
            ok=all(checks.values()),
            checks=checks,
            actual_intent=intent.get("intent"),
            state=flow.get("state"),
            error=flow.get("error") or detail.get("error_code"),
            workflow_id=flow.get("id"),
            model_calls=detail.get("model_calls"),
            ms=round((time.monotonic() - started) * 1000),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--finance-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cases", nargs="+", help="Optional smoke IDs. Default is all 130.")
    parser.add_argument(
        "--gemini", action="store_true", help="Send synthetic TEST cases to Gemini."
    )
    args = parser.parse_args()
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert Counter(c["category"] for c in cases) == COUNTS
    assert len({c["id"] for c in cases}) == len(cases)
    if args.cases:
        assert set(args.cases) <= {c["id"] for c in cases}
        cases = [c for c in cases if c["id"] in args.cases]
    verify_test_scope(args.schema, args.gemini)
    oracle = json.loads(args.finance_receipt.read_text(encoding="utf-8"))
    with httpx.Client(base_url=ORIGIN, timeout=10) as client:
        client.get("/api/session").raise_for_status()
        project = client.get(f"/api/projects/{oracle['project_id']}").raise_for_status().json()
        assert project["classification"] == "TEST"

    def run_case(case: dict) -> dict:
        try:
            result = measure(case, oracle, args.gemini)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            result = dict(ok=False, error=type(exc).__name__)
        return {"id": case["id"], "category": case["category"], **result}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream, ThreadPoolExecutor(3) as pool:
        for row in pool.map(run_case, cases):
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
    rows = [json.loads(line) for line in args.output.read_text(encoding="utf-8").splitlines()]
    print(
        json.dumps(
            dict(
                fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                correct=sum(row["ok"] for row in rows),
                total=len(rows),
            )
        )
    )


if __name__ == "__main__":
    main()
