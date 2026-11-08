"""Evaluate local LIVE intent + Backend planning against frozen synthetic labels.

No database, approvals or cloud requests. Does not retry any request, and stops
on provider/unknown-delivery errors. This is adapter/Planner evaluation, not UAT.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from studio.agent_intents import INTENT_REVISION, interpret_requests  # noqa: E402
from studio.ai_gateway import OllamaProvider  # noqa: E402
from studio.config import Settings  # noqa: E402
from studio.contracts import WorkspacePolicy  # noqa: E402
from studio.contracts.agent import IntentCatalogue  # noqa: E402
from studio.contracts.reconciliation import CanonicalRecord, PlanningRequest, SourceCatalogue  # noqa: E402
from studio.errors import DomainError  # noqa: E402
from studio.reconciliation_planner import (  # noqa: E402
    PLANNER_REVISION,
    missing_confirmations,
    propose_plan,
    scoped_key_candidates,
)


def evaluate_case(spec: dict[str, Any], config: Settings, task: str = "routing") -> dict[str, Any]:
    """Score every labelled request slot, then the independent full plan labels."""
    row: dict[str, Any] = {"id": spec["id"], "expected": spec["expected"], "correct": False}

    def capture(response: httpx.Response) -> None:
        # Only frozen synthetic model output; never headers, credentials, or
        # application data. Preserve rejected output for root-cause inspection.
        if response.request.url.path == "/api/chat":
            response.read()
            try:
                row["provider_reply"] = response.json().get("message")
            except ValueError:
                row["provider_reply_invalid_json"] = True

    provider = OllamaProvider(
        config,
        "QWEN_8B",
        httpx.Client(trust_env=False, follow_redirects=False, event_hooks={"response": [capture]}),
    )
    started = time.monotonic()
    try:
        if task == "planner":
            request = PlanningRequest.model_validate(spec["request"])
            cats = [
                SourceCatalogue.model_validate(source["catalogue"]) for source in spec["sources"]
            ]
            proposal = propose_plan(
                provider,
                cats,
                request,
                WorkspacePolicy(),
                lambda: True,
                cats[0].canonical.workspace_id,
                cats[0].project_id,
            )
            row["proposal"] = proposal.model_dump(mode="json")
            expected = spec["expected"]
            if expected["proposal_status"] == "PROPOSED":
                actual = proposal.plan.model_dump(mode="json") if proposal.plan else {}
                row["correct"] = (
                    proposal.status == "PROPOSED"
                    and bool(actual)
                    and all(
                        actual.get(key) == value for key, value in expected["plan_slots"].items()
                    )
                )
            else:
                row["correct"] = (
                    proposal.status in {"NEEDS_REVIEW", "UNKNOWN"}
                    and proposal.plan is None
                    and bool(proposal.missing_requirements)
                )
            return row
        catalogue = IntentCatalogue.model_validate(spec["catalogue"])
        result = interpret_requests(
            provider, [spec["goal"]], catalogue, WorkspacePolicy(), lambda: True
        )[0]
        row["intent"] = result.model_dump(mode="json")
        expected = spec["expected"]
        row["intent_correct"] = result.intent == expected["intent"]
        if result.planning_request is None:
            row["correct"] = row["intent_correct"] and expected.get("request") is None
            return row
        request = result.planning_request
        labelled = PlanningRequest.model_validate(expected["request"])
        row["request_correct"] = request.model_dump(exclude={"intent"}) == labelled.model_dump(
            exclude={"intent"}
        )
        sources = {item["catalogue"]["canonical"]["id"]: item for item in spec["sources"]}
        selected = [sources[slot.canonical_id] for slot in (request.left, request.right)]
        cats = [SourceCatalogue.model_validate(s["catalogue"]) for s in selected]
        rows = []
        for source in selected:
            records = []
            for item in source["rows"]:
                payload = dict(item["payload"])
                for field in source["catalogue"]["schema_definition"]["fields"]:
                    key = field["id"]
                    if field["data_type"] == "decimal" and payload.get(key) is not None:
                        payload[key] = Decimal(payload[key])
                    elif field["data_type"] == "date" and payload.get(key) is not None:
                        payload[key] = datetime.fromisoformat(payload[key])
                records.append(CanonicalRecord.model_validate(item | {"payload": payload}))
            rows.append(records)
        proposal = scoped_key_candidates(request, cats, rows[0], rows[1])
        row["missing"] = missing_confirmations(request)
        row["proposal"] = proposal.model_dump(mode="json") if proposal else None
        if expected["proposal_status"] == "PROPOSED":
            actual = proposal.plan.model_dump(mode="json") if proposal and proposal.plan else {}
            row["plan_correct"] = bool(actual) and all(
                actual.get(k) == v for k, v in expected["plan_slots"].items()
            )
        else:
            row["plan_correct"] = proposal is None or (
                proposal.status == "NEEDS_REVIEW" and proposal.plan is None
            )
        row["correct"] = row["intent_correct"] and row["request_correct"] and row["plan_correct"]
    except (DomainError, KeyError) as exc:
        row["error_code"] = exc.code if isinstance(exc, DomainError) else "UNLABELLED_SOURCE"
    finally:
        row["latency_ms"] = (time.monotonic() - started) * 1000
        row["usage"] = provider.usage
        provider.close()
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ids", help="Optional comma-separated case IDs; never auto retry")
    parser.add_argument("--task", choices=("routing", "planner"), default="routing")
    args = parser.parse_args()
    raw = args.spec.read_bytes()
    specs = json.loads(raw)
    selected = set(args.ids.split(",")) if args.ids else None
    receipt: dict[str, Any] = {
        "mode": "LIVE_LOCAL_REGISTERED_PLANNER_SYNTHETIC"
        if args.task == "planner"
        else "LIVE_LOCAL_ADAPTER_AND_BACKEND_PLANNER_SYNTHETIC",
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
        "intent_revision": INTENT_REVISION,
        "planner_revision": PLANNER_REVISION,
        "source_sha256": {
            name: hashlib.sha256(
                (Path(__file__).resolve().parents[1] / "backend/studio" / name).read_bytes()
            ).hexdigest()
            for name in ("agent_intents.py", "reconciliation_planner.py", "ai_gateway.py")
        },
        "cloud_requests": 0,
        "database_execution": False,
        "browser_uat": "NOT_RUN",
        "cases": [],
        "stop_reason": None,
    }
    config = Settings(local_demo_access=True, ollama_url="http://127.0.0.1:11434")
    for spec in specs:
        if selected and spec["id"] not in selected:
            continue
        row = evaluate_case(spec, config, args.task)
        receipt["cases"].append(row)
        if row.get("error_code", "").startswith("OLLAMA_") or row["usage"].get("delivery_unknown"):
            receipt["stop_reason"] = {
                "id": row["id"],
                "error_code": row.get("error_code"),
                "delivery_unknown": row["usage"].get("delivery_unknown"),
            }
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    k: row.get(k)
                    for k in (
                        "id",
                        "correct",
                        "request_correct",
                        "plan_correct",
                        "latency_ms",
                        "error_code",
                    )
                }
            ),
            flush=True,
        )
        if receipt["stop_reason"]:
            break


if __name__ == "__main__":
    main()
