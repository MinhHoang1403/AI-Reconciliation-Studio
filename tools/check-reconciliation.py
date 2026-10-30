"""Scoped synthetic acceptance through the production API; cloud only via explicit flag.

Reuses the same project/artifact/run refs on rerun. Mapping is always manual.
Optional planner reserves at most the existing task/global ceilings, never retries
an unknown delivery. State and downloaded reports stay under ignored runtime.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime" / "reconciliation-acceptance.json"
sys.path.insert(0, str(ROOT / "backend"))


def planner_input(project_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Use the current proposal input contract without sending executable matching rules."""
    from studio.contracts.reconciliation import PlanningRequest, ReconciliationPlan

    request = PlanningRequest.from_plan(ReconciliationPlan.model_validate(plan))
    return dict(project_id=project_id, request=request.model_dump(mode="json", exclude_unset=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner-live", action="store_true")
    args = parser.parse_args()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

    def save() -> None:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    with httpx.Client(
        base_url="http://127.0.0.1:18180", timeout=30, headers={"Origin": "http://127.0.0.1:18180"}
    ) as client:

        def get(path: str):
            response = client.get("/api" + path)
            response.raise_for_status()
            return response.json()

        def post(path: str, body=None, **kwargs):
            response = client.post(
                "/api" + path, json=body, headers={"Idempotency-Key": str(uuid4())}, **kwargs
            )
            if not response.is_success:
                raise RuntimeError(
                    f"API acceptance blocked: {response.status_code} {response.json().get('code')}"
                )
            return response.json()

        def wait(job_id: str):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                job = get("/jobs/" + job_id)
                if job["status"] == "SUCCEEDED":
                    return job
                if job["status"] in {"FAILED", "BLOCKED", "CANCELLED"}:
                    raise RuntimeError(f"Job blocked: {job['error_code']}; no automatic resubmit")
                time.sleep(0.4)
            raise RuntimeError("Job still pending; do not resend")

        get("/session")
        initial_budget = get("/settings")["gemini_requests_used"]
        if "project_id" not in state:
            state["project_id"] = post(
                "/projects",
                dict(
                    name="Đối soát tổng hợp có oracle",
                    business_scope="synthetic-reconciliation-acceptance",
                    classification="TEST",
                ),
            )["id"]
            save()
        project_id = state["project_id"]
        for filename in (
            "internal-sales.csv",
            "shopee-orders.csv",
            "tiktok-order-lines.csv",
            "shipments.csv",
            "delivery-confirmations.csv",
        ):
            item = state.setdefault("sources", {}).setdefault(filename, {})
            if item.get("canonical_id"):
                continue
            if "dataset_id" not in item:
                uploaded = post(
                    "/datasets/uploads",
                    data={"project_id": project_id, "request_ai_mapping": "false"},
                    files={
                        "files": (
                            filename,
                            (ROOT / "tests" / "fixtures" / filename).read_bytes(),
                            "text/csv",
                        )
                    },
                )
                item.update(
                    dataset_id=uploaded["items"][0]["id"],
                    parse_job=uploaded["items"][0].get("job_id"),
                )
                save()
            if item.get("parse_job"):
                wait(item["parse_job"])
            table = get(f"/datasets/{item['dataset_id']}/tables")["items"][0]
            mapping = get(f"/tables/{table['id']}/mappings")["items"][0]
            ecommerce = "carrier" not in [c["name"] for c in table["parsed"]["columns"]]
            grain = "order_line" if "lines" in filename else "order" if ecommerce else "delivery"
            metric = "item_gross" if ecommerce else "delivery_charge"
            money = "gross_amount" if ecommerce else "delivery_charge"
            columns = table["parsed"]["columns"]
            schema = mapping["schema"] | dict(
                entity_kind=grain,
                grain=grain,
                business_key_fields=[]
                if grain == "order_line"
                else ["platform", "shop_id", "order_id"]
                if ecommerce
                else ["carrier", "tracking_id"],
                fields=[
                    dict(
                        id=c["name"],
                        name=c["name"],
                        data_type="decimal"
                        if c["name"] == money
                        else "date"
                        if c["name"] == "event_date"
                        else "string",
                        required=False,
                        **(
                            dict(
                                semantic_metric=metric,
                                amount_basis="gross",
                                currency="VND",
                                unit="VND",
                            )
                            if c["name"] == money
                            else {}
                        ),
                    )
                    for c in columns
                ],
            )
            decisions = [
                dict(
                    source_field=c["id"],
                    candidate_target=c["name"],
                    decision="APPROVED",
                    grain_assumption=grain,
                    evidence_ids=[f"{table['id']}:{c['id']}"],
                    transformation_candidate=dict(op="parse_decimal", locale="en-US")
                    if c["name"] == money
                    else dict(op="parse_date", format="%Y-%m-%d", timezone="UTC")
                    if c["name"] == "event_date"
                    else dict(op="cast_string_preserve"),
                )
                for c in columns
            ]
            approved = post(
                f"/mappings/{mapping['id']}/approve",
                dict(schema_definition=schema, decisions=decisions, extraction_reviewed=True),
            )
            normalized = post(
                f"/datasets/{item['dataset_id']}/normalize", dict(mapping_id=approved["id"])
            )
            wait(normalized["job_id"])
            canonical = get(f"/datasets/{item['dataset_id']}/artifacts")["canonical_datasets"][-1]
            item.update(
                canonical_id=canonical["id"], table_id=table["id"], schema_id=canonical["schema_id"]
            )
            save()
        specs = [
            ("shopee", "internal-sales.csv", "shopee-orders.csv", "Shopee", "ONE_TO_ONE"),
            ("tiktok", "internal-sales.csv", "tiktok-order-lines.csv", "TikTok", "ONE_TO_MANY"),
            ("delivery", "shipments.csv", "delivery-confirmations.csv", "", "ONE_TO_ONE"),
        ]
        for name, left, right, platform, cardinality in specs:
            a, b = [state["sources"][f]["canonical_id"] for f in (left, right)]
            slot = dict(
                date_field="event_date",
                time_basis="event_date",
                currency_field="currency",
                coverage_start="2026-10-01",
                coverage_end="2026-11-01",
                completeness="CONFIRMED",
                snapshot_at="2026-11-02T00:00:00Z",
            )
            field = "gross_amount" if platform else "delivery_charge"
            plan = dict(
                name="Đối soát " + name,
                entity_kind="order" if platform else "delivery",
                left=dict(
                    canonical_id=a,
                    role="reference",
                    filters={"platform": platform} if platform else {},
                    **slot,
                ),
                right=dict(canonical_id=b, role="counterpart", **slot),
                join_keys=[
                    dict(left=k, right=k)
                    for k in (
                        ["platform", "shop_id", "order_id"]
                        if platform
                        else ["carrier", "tracking_id"]
                    )
                ],
                comparison_metrics=[
                    dict(
                        left=field,
                        right=field,
                        metric_id="item_gross" if platform else field,
                        currency="VND",
                        unit="VND",
                        amount_basis="gross",
                        sign_convention="SOURCE_SIGNED",
                    )
                ],
                comparison_grain="order" if platform else "delivery",
                cardinality=cardinality,
                aggregation="NONE" if cardinality == "ONE_TO_ONE" else "SUM_SIGNED",
                period_start="2026-10-01",
                period_end="2026-10-31",
                timezone="UTC",
                effective_from="2026-10-01",
                evidence_ids=[a, b],
            )
            entry = state.setdefault("runs", {}).setdefault(name, {"plan": plan})
            if "run_id" not in entry:
                proposal = post("/reconciliation-plans", dict(project_id=project_id, plan=plan))
                rule = post(f"/reconciliation-contracts/{proposal['id']}/approve")
                accepted = post("/reconciliation-runs", dict(contract_id=rule["id"]))
                entry.update(
                    run_id=accepted["run_id"], job_id=accepted["job_id"], contract_id=rule["id"]
                )
                save()
            wait(entry["job_id"])
            snapshot = get(f"/runs/{entry['run_id']}/metrics")
            expected = "10.00" if name == "shopee" else "2.75" if name == "delivery" else "0.00"
            from decimal import Decimal

            assert Decimal(snapshot["monetary"][0]["absolute_variance"]) == Decimal(expected)
            if name == "shopee":
                assert (
                    snapshot["full_match_rate"]["numerator"] == 2
                    and snapshot["eligible_units"] == 5
                )
            if name == "delivery":
                assert (
                    snapshot["full_match_rate"]["numerator"] == 1
                    and snapshot["eligible_units"] == 3
                )
            entry["snapshot"] = snapshot
            for format in ("csv", "xlsx"):
                exported = post(f"/runs/{entry['run_id']}/exports?format={format}")
                wait(exported["job_id"])
                info = get("/exports/" + exported["export_id"])
                response = client.get(info["download_url"])
                response.raise_for_status()
                destination = ROOT / "runtime" / f"reconciliation-{name}.{format}"
                destination.write_bytes(response.content)
                entry[format + "_export_id"] = exported["export_id"]
            save()
            print(f"PASS {name}: verified snapshot matches manual oracle; CSV/XLSX ready")
        if args.planner_live:
            cached = bool(state.get("planner_job_id"))
            if state.get("planner_job_id"):
                job = wait(state["planner_job_id"])
            else:
                config = get("/settings")
                assert (
                    config["mapping_ai_provider"] == "GEMINI"
                    and config["gemini_requests_remaining"] >= 1
                )
                job = post(
                    "/reconciliation-plans/ai",
                    planner_input(project_id, state["runs"]["delivery"]["plan"]),
                )
                state["planner_job_id"] = job["job_id"]
                save()
                job = wait(job["job_id"])
            state["planner"] = get("/reconciliation-plans/" + job["result"]["plan_id"])
            assert state["planner"]["contract_id"] is None
            assert state["planner"]["origin"] == "GEMINI"
            evidence = (
                "PASS CACHED historical planner; no new live verification"
                if cached
                else "PASS LIVE planner transport/typed semantic validation"
            )
            print(evidence + "; proposal requires approval")
            save()
        final = get("/settings")
        delta = final["gemini_requests_used"] - initial_budget
        assert delta <= 2 if args.planner_live else delta == 0
        print(
            f"Gemini new attempts={delta}; used={final['gemini_requests_used']}; "
            f"remaining={final['gemini_requests_remaining']}"
        )


if __name__ == "__main__":
    main()
