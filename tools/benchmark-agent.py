"""Đo gold tiếng Việt bằng router production, ledger thật; không thực thi model actions.

Chỉ chạy opt-in trong backend hiện có trên hai conversation thuộc project TEST,
--execute-live sau khi đã phân bổ Agent/global quota. Mỗi batch≤10 cùng context;
không coi kết quả batch là đo latency/accuracy độc lập của từng câu đơn.
"""

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select
from studio.access import Actor
from studio.agent_intents import (
    INTENT_REVISION,
    compile_routing,
    interpret_requests,
    validate_intents,
)
from studio.agent_jobs import model_call
from studio.agent_workflows import digest
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue
from studio.config import settings
from studio.contracts.agent import AgentIntent, WorkflowState
from studio.contracts.assistant import AssistantContext
from studio.database import (
    AgentWorkflowRow,
    AttemptRow,
    MembershipRow,
    ProjectRow,
    SessionFactory,
    TraceRow,
    now,
)
from studio.errors import DomainError
from studio.repository import enqueue_job, project_classification_expression
from studio.worker import _fence, _finish


def decimal_equal(value: str, expected: str) -> bool:
    try:
        parsed = Decimal(value)
        return parsed.is_finite() and parsed == Decimal(expected)
    except InvalidOperation:
        return False


def repairable_failure(code: str | None, usage: dict[str, Any]) -> bool:
    """Only a known completed reply may be measured once after an explicit fix."""
    return (
        code in {"QUERY_SEMANTICS_REQUIRED", "AI_INVALID_JSON"}
        and usage.get("http_status") == 200
        and usage.get("finish_reason") == "STOP"
    )


def score_completed_candidates(candidates, cases, catalogue, ids):
    """Score every completed synthetic reply; a rejected case stays in all denominators.

    This never executes or repairs an action. The original batch/job remains BLOCKED.
    Other items use the same production validator independently, not an LLM judge.
    """
    assert len(candidates) == len(cases)
    results = []
    for candidate, case in zip(candidates, cases, strict=True):
        try:
            parsed = compile_routing(
                json.dumps(dict(intents=[candidate])), [case["goal"]], catalogue
            )[0]
            results.append(score(case, parsed, ids, catalogue.confirmed_plan))
        except DomainError as exc:
            # Conservative: failed source/slot validation cannot earn source/slot credit.
            results.append(
                dict(
                    id=case["id"],
                    intent_ok=candidate["intent"] == case["intent"],
                    source_applicable=case.get("source") is not None,
                    source_ok=False,
                    semantic_applicable=any(
                        case.get(k)
                        for k in ("key", "aggregate", "filter", "group", "scope", "format")
                    ),
                    semantic_ok=False,
                    tool_ok=False,
                    abstention_ok=False if case.get("negative") else None,
                    validation_error=exc.code,
                    actual_routing=candidate,
                )
            )
    return results


def score(gold: dict, intent: AgentIntent, ids: dict, confirmed_plan=None) -> dict:
    expected = gold.get("source")
    dataset_ids = set(intent.dataset_ids)
    requested = {ids["A"], ids["B"]} if expected == "BOTH" else {ids.get(expected)}
    if intent.intent in {"PREPARE_NORMALIZATION", "EXPLORE_DATA"}:
        source_ok = dataset_ids == requested
    elif intent.intent == "RECONCILE_DATASETS":
        p = intent.planning_request
        source_ok = bool(
            p and {p.left.canonical_id, p.right.canonical_id} == {ids["CA"], ids["CB"]}
        )
    elif intent.query:
        source_ok = intent.query.source_id == ids.get(expected) and (
            intent.query.source_kind == gold.get("kind", "CANONICAL")
        )
    else:
        source_ok = expected is None or expected == "RUN" and intent.run_id in {None, ids["RUN"]}
    semantic_ok = True
    if gold.get("key"):
        semantic_ok = intent.key_value == gold["key"]
    if gold.get("aggregate"):
        q = intent.query
        semantic_ok = bool(
            q
            and any(
                a.op == ("sum_decimal" if gold["aggregate"] == "sum" else "count")
                and (gold["aggregate"] != "sum" or a.field_id == ids["amount_field"])
                for a in q.aggregations
            )
            and (
                gold["aggregate"] != "sum"
                or (
                    q.currency_field == ids["currency_field"]
                    and ids["currency_field"] in q.group_by
                )
            )
        )
    if gold.get("filter"):
        q = intent.query
        target = (
            ids[
                {
                    "paid": "paid_field",
                    "unpaid": "paid_field",
                    "id": "id_field",
                    "amount": "amount_field",
                }[gold["filter"]]
            ]
            if gold["filter"] in {"paid", "unpaid", "id", "amount"}
            else ("linkage_state" if gold["filter"] == "missing" else "state")
        )
        semantic_ok = bool(
            q
            and any(
                f.field_id == target
                and (
                    (
                        (
                            f.op == "eq"
                            and isinstance(f.value, str)
                            and f.value in {"PAID", "TRANSFERRED"}
                        )
                        or (
                            f.op == "in"
                            and isinstance(f.value, list)
                            and bool(f.value)
                            and set(f.value) <= {"PAID", "TRANSFERRED"}
                        )
                    )
                    if gold["filter"] == "paid"
                    else f.op == "eq" and f.value == "UNPAID"
                    if gold["filter"] == "unpaid"
                    else f.op == "eq" and f.value == "000702"
                    if gold["filter"] == "id"
                    else f.op in {"eq", "in"}
                    and bool(f.value)
                    and set([f.value] if isinstance(f.value, str) else f.value or [])
                    <= (
                        {"UNMATCHED"}
                        if gold["filter"] == "missing"
                        else {"OPEN"}
                        if gold["filter"] == "open_cases"
                        else {"OPEN", "IN_REVIEW"}
                    )
                    if gold["filter"] in {"missing", "open_cases", "unresolved_cases"}
                    else f.op == "gt" and isinstance(f.value, str) and decimal_equal(f.value, "10")
                )
                for f in q.filters
            )
        )
    if gold.get("group"):
        semantic_ok = semantic_ok and bool(
            intent.query
            and ids["paid_field"] in intent.query.group_by
            and not any(f.field_id == ids["paid_field"] for f in intent.query.filters)
        )
    if gold.get("scope") == "CONFIRMED_PLAN":
        from studio.contracts.reconciliation import PlanningRequest

        semantic_ok = semantic_ok and bool(
            confirmed_plan
            and intent.planning_request
            and intent.planning_request.model_dump(exclude={"intent"})
            == PlanningRequest.from_plan(confirmed_plan).model_dump(exclude={"intent"})
        )
    intent_ok = intent.intent == gold["intent"]
    if gold.get("format"):
        semantic_ok = semantic_ok and intent.export_format == gold["format"]
    dispatch = {
        "PREPARE_NORMALIZATION": "normalization_workflow",
        "EXPLORE_DATA": "query_dataset",
        "RECONCILE_DATASETS": "reconciliation_workflow",
        "QUERY_DATA": "query_dataset",
        "CREATE_VISUALIZATION": "query_dataset",
        "EXPLAIN_RESULT": "read_verified_facts",
        "SUMMARIZE_RESULTS": "read_verified_facts",
        "EXPORT_RESULT": "start_export",
        "CLARIFY": None,
        "UNSUPPORTED": None,
    }
    return dict(
        id=gold["id"],
        intent_ok=intent_ok,
        source_ok=source_ok,
        source_applicable=expected is not None,
        semantic_ok=semantic_ok,
        semantic_applicable=any(
            gold.get(k) for k in ("key", "aggregate", "filter", "group", "scope", "format")
        ),
        tool_ok=dispatch.get(intent.intent) == dispatch.get(gold["intent"]),
        abstention_ok=intent.intent in {"CLARIFY", "UNSUPPORTED"} if gold.get("negative") else None,
        actual=intent.model_dump(mode="json"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--suite", choices=["gold", "variants"], default="gold")
    parser.add_argument("--cases", nargs="+", help="Canary IDs; never changes the full gold rubric")
    parser.add_argument("--repair-known", choices=["payment-status-grouping"])
    parser.add_argument(
        "--evaluate-completed-cases",
        action="store_true",
        help="Score known HTTP200/STOP typed candidates per case; keep original failed jobs",
    )
    args = parser.parse_args()
    assert args.execute_live and settings.agent_cloud_enabled and settings.agent_request_budget != 0
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    contexts = json.loads(args.contexts.read_text(encoding="utf-8"))
    expected_count, expected_negative = (80, 20) if args.suite == "gold" else (24, 8)
    assert len(gold) == expected_count and len({c["id"] for c in gold}) == expected_count
    assert sum(bool(c.get("negative")) for c in gold) == expected_negative
    if args.cases:
        assert set(args.cases) <= {c["id"] for c in gold}
    assert set(contexts) == {"delivery", "ledger"}
    version = hashlib.sha256(args.gold.read_bytes()).hexdigest()
    results, batches = [], []
    stopped = False
    for domain in ("delivery", "ledger"):
        if stopped:
            break
        config = contexts[domain]
        with SessionFactory() as db:
            member = db.get(MembershipRow, (config["workspace_id"], config["actor_id"]))
            assert member is not None
            actor = Actor(member.actor_id, member.workspace_id, member.role)
            conv = own_conversation(db, actor, config["conversation_id"])
            classification = db.scalar(
                select(project_classification_expression()).where(ProjectRow.id == conv.project_id)
            )
            assert classification == "TEST", "Explicit synthetic TEST project required"
            context = AssistantContext.model_validate(config["context"])
            assert context.project_id == conv.project_id
            catalogue = agent_catalogue(db, actor, context, [])
            assert set(config["ids"][k] for k in ("A", "B")) == {d.id for d in catalogue.datasets}
            context_hash = digest(catalogue.model_dump(mode="json"))
        cases = [
            g for g in gold if g["domain"] == domain and (not args.cases or g["id"] in args.cases)
        ]
        for offset in range(0, len(cases), 10):
            subset = cases[offset : offset + 10]
            selection_hash = digest([g["id"] for g in subset])[:12]
            key = f"nl-gold:{INTENT_REVISION}:{version[:12]}:{context_hash[:12]}:{selection_hash}"
            token = str(uuid5(NAMESPACE_URL, key + ":claim"))
            with SessionFactory() as db:
                job = enqueue_job(
                    db,
                    actor.workspace_id,
                    context.project_id,
                    "agent_benchmark",
                    key,
                    dict(
                        gold_sha256=version,
                        context_sha256=context_hash,
                        cases=[g["id"] for g in subset],
                    ),
                )
                job_id = job.id
                repair_of = None
                if job.status == "BLOCKED" and args.evaluate_completed_cases:
                    trace = db.scalar(select(TraceRow).where(TraceRow.job_id == job.id))
                    assert trace and trace.usage.get("http_status") == 200
                    assert trace.usage.get("finish_reason") == "STOP"
                    assert job.result and job.result.get("routing_candidates")
                    results.extend(
                        score_completed_candidates(
                            job.result["routing_candidates"]["intents"],
                            subset,
                            catalogue,
                            config["ids"],
                        )
                    )
                    batches.append(
                        dict(
                            domain=domain,
                            offset=offset,
                            job_id=job_id,
                            status="CACHED_COMPLETED_CASE_EVALUATION",
                            original_status="BLOCKED",
                        )
                    )
                    continue
                if job.status == "BLOCKED" and args.repair_known:
                    trace = db.scalar(select(TraceRow).where(TraceRow.job_id == job.id))
                    # Explicit, one repair round after a reproduced validator fix.
                    # Never resend unknown delivery or overwrite the failed attempt.
                    assert trace is not None and repairable_failure(job.error_code, trace.usage), (
                        "Only known completed semantic/JSON failures may be re-evaluated"
                    )
                    repair_of = job.id
                    key += ":repair:" + args.repair_known
                    token = str(uuid5(NAMESPACE_URL, key + ":claim"))
                    job = enqueue_job(
                        db,
                        actor.workspace_id,
                        context.project_id,
                        "agent_benchmark",
                        key,
                        dict(
                            gold_sha256=version,
                            context_sha256=context_hash,
                            cases=[g["id"] for g in subset],
                            repair_of=repair_of,
                        ),
                    )
                    job_id = job.id
                if job.status == "SUCCEEDED":
                    # Cache không được bỏ qua semantic validator hiện hành.
                    parsed = validate_intents(
                        json.dumps(dict(intents=job.result["intents"])),
                        [g["goal"] for g in subset],
                        catalogue,
                    )
                    reused = True
                else:
                    if job.status != "QUEUED":
                        raise DomainError(
                            "AI_DELIVERY_UNKNOWN", "Benchmark chưa rõ delivery; không gửi lại."
                        )
                    workflow_id = str(uuid5(NAMESPACE_URL, key + ":workflow"))
                    job.status, job.claim_token, job.attempts = "RUNNING", token, 1
                    job.lease_until = now() + timedelta(minutes=5)
                    db.add(AttemptRow(job_id=job.id, number=1))
                    db.add(
                        AgentWorkflowRow(
                            id=workflow_id,
                            workspace_id=actor.workspace_id,
                            project_id=context.project_id,
                            conversation_id=conv.id,
                            actor_id=actor.id,
                            parent_job_id=job.id,
                            goal="Synthetic NL gold evaluation; no action execution",
                            context=context.model_dump(mode="json"),
                            fingerprint=context_hash,
                            state="RUNNING",
                            detail=WorkflowState().model_dump(mode="json"),
                        )
                    )
                    db.commit()
                    reused = False
            if not reused:
                goals = [g["goal"] for g in subset]
                captured = []

                def invoke(
                    provider, policy, reserve, goals=goals, catalogue=catalogue, captured=captured
                ):
                    return interpret_requests(
                        provider, goals, catalogue, policy, reserve, capture_routing=captured.append
                    )

                try:
                    parsed = model_call(
                        job_id,
                        token,
                        workflow_id,
                        "benchmark_agent_intents",
                        INTENT_REVISION,
                        SessionFactory,
                        _fence,
                        invoke,
                    )
                    with SessionFactory() as db:
                        job = _fence(db, job_id, token)
                        _finish(db, job, dict(intents=[i.model_dump(mode="json") for i in parsed]))
                        db.get(AgentWorkflowRow, workflow_id).state = "COMPLETED"
                        db.commit()
                except Exception as exc:
                    with SessionFactory() as db:
                        job = _fence(db, job_id, token)
                        job.status, job.lease_until = "BLOCKED", None
                        job.error_code = (
                            exc.code if isinstance(exc, DomainError) else "BENCHMARK_FAILED"
                        )
                        # Chỉ project TEST đã xác minh; lưu typed candidates cho offline
                        # diagnosis, không thực thi hoặc tự sửa câu trả lời không hợp lệ.
                        if captured:
                            job.result = dict(
                                routing_candidates=captured[-1].model_dump(mode="json")
                            )
                        row = db.get(AgentWorkflowRow, workflow_id)
                        row.state = "BLOCKED"
                        attempt = db.scalar(select(AttemptRow).where(AttemptRow.job_id == job.id))
                        attempt.status, attempt.error_code, attempt.finished_at = (
                            "BLOCKED",
                            job.error_code,
                            now(),
                        )
                        db.commit()
                    # Batch không đạt schema/semantic: các ca chưa đo không được chấm PASS.
                    if args.evaluate_completed_cases and captured:
                        with SessionFactory() as db:
                            trace = db.scalar(select(TraceRow).where(TraceRow.job_id == job_id))
                            known_complete = bool(
                                trace
                                and trace.usage.get("http_status") == 200
                                and trace.usage.get("finish_reason") == "STOP"
                            )
                        if known_complete:
                            results.extend(
                                score_completed_candidates(
                                    captured[-1].model_dump(mode="json")["intents"],
                                    subset,
                                    catalogue,
                                    config["ids"],
                                )
                            )
                            batches.append(
                                dict(
                                    domain=domain,
                                    offset=offset,
                                    job_id=job_id,
                                    status="LIVE_COMPLETED_CASE_EVALUATION",
                                    original_status="BLOCKED",
                                )
                            )
                            continue
                    results.extend(dict(id=g["id"], blocked=job.error_code) for g in subset)
                    batches.append(
                        dict(
                            domain=domain,
                            offset=offset,
                            job_id=job_id,
                            status="BLOCKED",
                            repair_of=repair_of,
                        )
                    )
                    args.output.write_text(
                        json.dumps(dict(results=results, batches=batches), indent=2),
                        encoding="utf-8",
                    )
                    # Không tốn các batch tiếp theo khi transport/schema/semantic gate lỗi.
                    stopped = True
                    break
            results.extend(
                score(g, i, config["ids"], catalogue.confirmed_plan)
                for g, i in zip(subset, parsed, strict=True)
            )
            batches.append(
                dict(
                    domain=domain,
                    offset=offset,
                    job_id=job_id,
                    status="CACHED" if reused else "LIVE",
                    repair_of=repair_of,
                )
            )
            args.output.write_text(
                json.dumps(dict(results=results, batches=batches), indent=2), encoding="utf-8"
            )
    measured = [r for r in results if not r.get("blocked")]
    summary = dict(
        suite=args.suite,
        prompt_revision=INTENT_REVISION,
        stopped_on_block=stopped,
        requested_total=sum(1 for g in gold if not args.cases or g["id"] in args.cases),
        total=len(results),
        measured=len(measured),
        blocked=len(results) - len(measured),
        intent_correct=sum(r["intent_ok"] for r in measured),
        source_measured=sum(r["source_applicable"] for r in measured),
        source_correct=sum(r["source_applicable"] and r["source_ok"] for r in measured),
        semantic_measured=sum(r["semantic_applicable"] for r in measured),
        semantic_correct=sum(r["semantic_applicable"] and r["semantic_ok"] for r in measured),
        tool_correct=sum(r["tool_ok"] for r in measured),
        negative_measured=sum(r["abstention_ok"] is not None for r in measured),
        correct_abstentions=sum(r["abstention_ok"] is True for r in measured),
        case_validation_failures=sum(bool(r.get("validation_error")) for r in measured),
        completed_case_evaluation=args.evaluate_completed_cases,
        action_execution="NONE; router only, workflow completion measured separately",
        tool_measurement="Inferred fixed dispatch from typed intent; no action tools executed here",
    )
    args.output.write_text(
        json.dumps(dict(summary=summary, results=results, batches=batches), indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
