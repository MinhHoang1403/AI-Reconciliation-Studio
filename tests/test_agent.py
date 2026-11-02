"""Contract/safety MOCK; không dùng các ca này để báo độ chính xác Gemini live."""

import json

import httpx
import pytest
from pydantic import ValidationError
from studio.agent_intents import interpret_requests, validate_intents
from studio.ai_gateway import GeminiProvider
from studio.config import Settings
from studio.contracts import WorkspacePolicy
from studio.contracts.agent import AgentIntent, IntentCatalogue
from studio.errors import DomainError


def catalogue():
    return IntentCatalogue.model_validate(
        dict(
            context=dict(project_id="p"),
            run_ids=["run"],
            datasets=[
                dict(
                    id="dataset",
                    name="Ledger",
                    status="READY",
                    tables=[
                        dict(
                            table_id="table",
                            sheet="Sheet1",
                            row_count=3,
                            columns=[],
                            canonical_id="canonical",
                            paid_status_fields=["payment_status"],
                        )
                    ],
                )
            ],
        )
    )


def validate(intent, goal="Liệt kê dữ liệu"):
    return validate_intents(json.dumps(dict(intents=[intent])), [goal], catalogue())[0]


@pytest.mark.parametrize(
    "payload",
    [
        dict(intent="approve_mapping"),
        dict(intent="QUERY_DATA", actor_id="owner"),
        dict(intent="QUERY_DATA", sql="SELECT * FROM secrets"),
        dict(intent="QUERY_DATA", storage_path="/private"),
        dict(intent="EXPLORE_DATA", dataset_ids=["other-project"]),
        dict(intent="SUMMARIZE_RESULTS", run_id="other-run"),
        dict(
            intent="QUERY_DATA",
            query=dict(project_id="other-project", source_kind="CANONICAL", source_id="canonical"),
        ),
        dict(
            intent="QUERY_DATA",
            query=dict(project_id="p", source_kind="RAW_PREVIEW", source_id="run"),
        ),
        dict(
            intent="QUERY_DATA",
            query=dict(project_id="p", source_kind="VERIFIED_RUN", source_id="table"),
        ),
        dict(
            intent="QUERY_DATA",
            query=dict(
                project_id="p", source_kind="CANONICAL", source_id="canonical", limit=100000
            ),
        ),
        dict(
            intent="QUERY_DATA",
            query=dict(
                project_id="p", source_kind="CANONICAL", source_id="canonical", null_policy="ZERO"
            ),
        ),
    ],
)
def test_agent_typed_intent_rejects_invalid_authority_source_and_caps(payload):
    with pytest.raises((DomainError, ValidationError)):
        validate(payload)


@pytest.mark.parametrize(
    "predicate",
    [
        dict(field_id="completed", op="eq", value="COMPLETED"),
        dict(field_id="payment_status", op="eq", value="COMPLETED"),
        dict(field_id="payment_status", op="ne", value="PAID"),
        dict(field_id="payment_status", op="in", value=["PAID", "COMPLETED"]),
    ],
)
def test_paid_is_not_completed_or_not_unpaid(predicate):
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(
            dict(
                intent="QUERY_DATA",
                query=dict(
                    project_id="p",
                    source_kind="CANONICAL",
                    source_id="canonical",
                    filters=[predicate],
                ),
            ),
            "Liệt kê giao dịch đã chuyển tiền",
        )


def test_paid_exact_semantics_and_missing_year_abstention():
    q = dict(
        project_id="p",
        source_kind="CANONICAL",
        source_id="canonical",
        filters=[dict(field_id="payment_status", op="eq", value="PAID")],
    )
    intent = validate(dict(intent="QUERY_DATA", query=q), "Liệt kê đã thanh toán")
    assert intent.query.source_id == "canonical"
    assert intent.query.filters[0].value == "PAID"
    q["filters"] = [dict(field_id="date", op="gte", value="2026-10-01T00:00:00Z")]
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate(dict(intent="QUERY_DATA", query=q), "Các dòng trong tháng 10")
    assert validate(dict(intent="QUERY_DATA", query=q), "Các dòng tháng 10/2026").query


def test_agent_cloud_off_calls_no_http_or_reservation():
    def forbidden(request):
        pytest.fail("Cloud OFF must never send HTTP")

    provider = GeminiProvider(
        Settings(allow_external_ai=False), httpx.Client(transport=httpx.MockTransport(forbidden))
    )
    reserved = []
    try:
        with pytest.raises(DomainError):
            interpret_requests(
                provider,
                ["Chuẩn hóa"],
                catalogue(),
                WorkspacePolicy(),
                lambda: reserved.append(True) or False,
            )
    finally:
        provider.close()
    assert not reserved


def test_agent_model_cannot_supply_approval_through_new_contract():
    with pytest.raises(ValidationError):
        AgentIntent(intent="RECONCILE_DATASETS", approved_by="owner", auto_approve=True)


def test_query_deadline_cancels_native_handle_and_never_returns_partial(monkeypatch):
    import studio.data_query as query

    cancelled = []

    class Pending:
        def fetch(self):
            return None

        def cancel(self):
            cancelled.append(True)

    class Lazy:
        def collect(self, **kwargs):
            assert kwargs == dict(background=True, engine="in-memory")
            return Pending()

    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(query.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(query.time, "sleep", lambda _: None)
    with pytest.raises(DomainError, match="QUERY_TIMEOUT"):
        query._collect_bounded(Lazy(), 1.0)
    assert cancelled == [True]


def test_multi_source_single_goal_requires_one_intent_without_provider_retry():
    received = []

    def handler(request):
        received.append(request)
        prompt = request.read().decode()
        assert "exactly 1 input goals" in prompt
        assert "NOT per file" in prompt
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "intents": [
                                                {
                                                    "intent": "PREPARE_NORMALIZATION",
                                                    "dataset_ids": ["dataset"],
                                                },
                                                {
                                                    "intent": "PREPARE_NORMALIZATION",
                                                    "dataset_ids": ["dataset"],
                                                },
                                            ]
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    config = Settings(
        allow_external_ai=True, external_ai_request_budget=5, gemini_api_key="synthetic-key-only"
    )
    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(handler)))
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=5
    )
    reserved = []
    with pytest.raises(DomainError, match="AI_INVALID_INTENT_COUNT"):
        interpret_requests(
            provider,
            ["Chuẩn hóa hai nguồn trong một yêu cầu"],
            catalogue(),
            policy,
            lambda: reserved.append(True) or True,
        )
    assert len(received) == len(reserved) == 1
    assert provider.usage["intent_count"] == 2
    assert provider.usage["expected_intent_count"] == 1
    intent = validate_intents(
        json.dumps({"intents": [{"intent": "PREPARE_NORMALIZATION", "dataset_ids": ["dataset"]}]}),
        ["Chuẩn hóa hai nguồn"],
        catalogue(),
    )[0]
    assert intent.intent == "PREPARE_NORMALIZATION"


@pytest.mark.parametrize("bad", ["header", "omitted", "wrong_table", "duplicate_target", None])
def test_normalization_provider_preserves_exact_source_ids_and_every_column(profile, bad):
    from studio.agent_preparation import propose_normalization

    fields = [
        dict(source_field=c.column_id, target_id=f"field_{i}", name=c.name, data_type="string")
        for i, c in enumerate(profile.columns)
    ]
    if bad == "header":
        fields[0]["source_field"] = "header_transaction_id"
    if bad == "omitted":
        fields.pop()
    if bad == "duplicate_target":
        fields[-1]["target_id"] = fields[0]["target_id"]
    output = dict(
        table_id="wrong" if bad == "wrong_table" else profile.source_table_id,
        entity_kind="synthetic",
        grain="one record per row",
        fields=fields,
    )
    calls = []

    def handler(request):
        calls.append(request)
        payload = json.loads(request.read())
        assert (
            "source_field equal to columns[i].id"
            in payload["systemInstruction"]["parts"][0]["text"]
        )
        schema = payload["generationConfig"]["responseJsonSchema"]
        field = schema["$defs"]["NormalizationField"]
        assert set(field["required"]) == set(field["properties"])
        assert "maxItems" not in schema["properties"]["fields"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output)}]}}
                ]
            },
        )

    config = Settings(
        allow_external_ai=True, external_ai_request_budget=5, gemini_api_key="synthetic-key-only"
    )
    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(handler)))
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=5
    )
    if bad:
        with pytest.raises(DomainError, match="INVALID_SOURCE_FIELD"):
            propose_normalization(provider, profile.source_table_id, profile, policy, lambda: True)
    else:
        draft = propose_normalization(
            provider, profile.source_table_id, profile, policy, lambda: True
        )
        assert {f.source_field for f in draft.fields} == {c.column_id for c in profile.columns}
    assert len(calls) == 1
    assert provider.usage["draft_shape"]["expected_fields"] == len(profile.columns)
    assert "source_field" not in provider.usage["draft_shape"]


def test_canonical_query_does_not_take_verified_comparison_metric_id():
    payload = dict(
        intent="QUERY_DATA",
        query=dict(
            project_id="p",
            source_kind="CANONICAL",
            source_id="canonical",
            select_fields=["payment_status"],
            filters=[dict(field_id="payment_status", op="eq", value="PAID")],
            metric_id="delivery_charge",
        ),
    )
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Liệt kê các giao dịch đã thanh toán")
    payload["query"]["metric_id"] = None
    assert validate(payload, "Liệt kê các giao dịch đã thanh toán").query.metric_id is None


def test_grouping_all_approved_payment_states_is_not_a_paid_filter():
    payload = dict(
        intent="CREATE_VISUALIZATION",
        query=dict(
            project_id="p",
            source_kind="CANONICAL",
            source_id="canonical",
            group_by=["payment_status"],
            aggregations=[dict(op="count")],
        ),
    )
    assert (
        validate(payload, "Vẽ biểu đồ giao dịch theo trạng thái thanh toán").intent
        == "CREATE_VISUALIZATION"
    )
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Vẽ biểu đồ giao dịch đã thanh toán theo trạng thái thanh toán")
    payload["query"]["filters"] = [dict(field_id="payment_status", op="eq", value="PAID")]
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Vẽ biểu đồ giao dịch theo trạng thái thanh toán")
    payload["query"]["filters"] = []
    payload["query"]["group_by"] = ["completed"]
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Vẽ biểu đồ giao dịch theo trạng thái thanh toán")


def test_benchmark_repair_refuses_unknown_delivery_and_preserves_numeric_rubric():
    import runpy
    from pathlib import Path

    candidate = Path(__file__).resolve().parents[1] / "tools/benchmark-agent.py"
    if not candidate.exists():
        candidate = Path(__file__).with_name("benchmark-agent.py")
    helper = runpy.run_path(str(candidate))
    repairable = helper["repairable_failure"]
    assert repairable("QUERY_SEMANTICS_REQUIRED", dict(http_status=200, finish_reason="STOP"))
    assert repairable("AI_INVALID_JSON", dict(http_status=200, finish_reason="STOP"))
    for code, usage in [
        ("AI_DELIVERY_UNKNOWN", dict(http_status=200, finish_reason="STOP")),
        ("GEMINI_UNAVAILABLE", {}),
        ("AI_INVALID_JSON", dict(http_status=200)),
        ("AI_INVALID_JSON", dict(http_status=400, finish_reason="STOP")),
        ("AI_INVALID_JSON", dict(http_status=200, finish_reason="MAX_TOKENS")),
    ]:
        assert not repairable(code, usage)
    assert helper["decimal_equal"]("10.00", "10")
    assert not helper["decimal_equal"]("wrong", "10")
    assert not helper["decimal_equal"]("NaN", "10")
    proposed = AgentIntent(
        intent="CREATE_VISUALIZATION",
        query=dict(
            project_id="p",
            source_kind="CANONICAL",
            source_id="canonical",
            group_by=["payment_status"],
            aggregations=[dict(op="count")],
            filters=[dict(field_id="payment_status", op="eq", value="PAID")],
        ),
    )
    scored = helper["score"](
        dict(
            id="group",
            intent="CREATE_VISUALIZATION",
            source="CA",
            aggregate="count",
            group="paid_status",
        ),
        proposed,
        dict(A="a", B="b", CA="canonical", paid_field="payment_status"),
    )
    assert scored["intent_ok"] and not scored["semantic_ok"]


def test_agent_rejects_listing_with_aggregation_grouping_and_invented_status():
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate(
            dict(
                intent="QUERY_DATA",
                query=dict(
                    project_id="p",
                    source_kind="CANONICAL",
                    source_id="canonical",
                    group_by=["currency"],
                ),
            )
        )
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(
            dict(
                intent="QUERY_DATA",
                query=dict(
                    project_id="p",
                    source_kind="VERIFIED_RUN",
                    source_id="run",
                    filters=[dict(field_id="comparison_state", op="ne", value="MATCHED")],
                ),
            )
        )


def test_agent_transaction_key_is_not_an_invented_technical_group_id():
    payload = dict(
        intent="QUERY_DATA",
        query=dict(
            project_id="p",
            source_kind="VERIFIED_RUN",
            source_id="run",
            filters=[dict(field_id="group_id", op="eq", value="000702")],
        ),
    )
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate(payload, "Vì sao giao dịch 000702 không khớp?")
    cat = catalogue()
    cat.context.group_id = "known-group"
    payload["query"]["filters"][0]["value"] = "known-group"
    assert validate_intents(json.dumps(dict(intents=[payload])), ["Xem nhóm hiện tại"], cat)[
        0
    ].query


def routing_catalogue():
    from reconciliation_cases import catalogue as source
    from reconciliation_cases import plan, records
    from studio.contracts.agent import DatasetContext, TableContext
    from studio.contracts.assistant import AssistantContext

    candidate = plan()
    tables = [
        source("internal", records("internal-sales.csv")),
        source("shopee", records("shopee-orders.csv")),
    ]
    return IntentCatalogue(
        context=AssistantContext(project_id="project", run_id="run"),
        run_ids=["run"],
        confirmed_plan=candidate,
        datasets=[
            DatasetContext(
                id=f"dataset-{i}",
                name=f"Source {i}",
                status="READY",
                tables=[
                    TableContext(
                        table_id=f"table-{i}",
                        sheet="Sheet1",
                        row_count=3,
                        columns=[],
                        canonical_id=t.canonical.id,
                        canonical_status="READY",
                        schema_definition=t.schema_definition,
                    )
                ],
            )
            for i, t in enumerate(tables)
        ],
    )


def test_routing_scope_reference_preserves_every_confirmed_fact_and_never_mutates_history():
    from studio.agent_intents import compile_routing
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    before = cat.model_dump_json()
    selection = dict(
        left_canonical_id=cat.confirmed_plan.left.canonical_id,
        right_canonical_id=cat.confirmed_plan.right.canonical_id,
        confirmed_run_id="run",
    )
    routed = compile_routing(
        json.dumps(dict(intents=[dict(intent="RECONCILE_DATASETS", reconciliation=selection)])),
        ["Thực hiện đối chiếu trong phạm vi hiện tại"],
        cat,
    )[0]
    expected = PlanningRequest.from_plan(cat.confirmed_plan).model_dump(exclude={"intent"})
    assert routed.planning_request.model_dump(exclude={"intent"}) == expected
    assert cat.model_dump_json() == before
    for change in [
        dict(confirmed_run_id="foreign-run"),
        dict(period_start="2027-01-01"),
        dict(timezone="Asia/Ho_Chi_Minh"),
        dict(left_canonical_id=selection["right_canonical_id"]),
    ]:
        with pytest.raises(DomainError):
            compile_routing(
                json.dumps(
                    dict(
                        intents=[
                            dict(intent="RECONCILE_DATASETS", reconciliation=selection | change)
                        ]
                    )
                ),
                ["Giữ phạm vi hiện tại"],
                cat,
            )
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps(dict(intents=[dict(intent="RECONCILE_DATASETS", reconciliation=selection)])),
            ["Đối chiếu kỳ 2027"],
            cat,
        )


def test_routing_query_binds_source_kind_project_and_rejects_wrong_field_or_ambiguous_name():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    query = dict(source_ref="source-2", select_fields=["order_id"])

    def route(q):
        return compile_routing(
            json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=q)])),
            ["Xem mã giao dịch nguồn tham chiếu"],
            cat,
        )[0]

    actual = route(query).query
    assert actual.project_id == "project" and actual.source_kind == "CANONICAL"
    assert actual.source_id == cat.confirmed_plan.left.canonical_id
    for q in [
        query | dict(source_ref="foreign"),
        query | dict(select_fields=["invented_amount"]),
        query | dict(project_id="foreign"),
        query | dict(source_id="foreign"),
    ]:
        with pytest.raises(DomainError):
            route(q)
    cat.datasets[1].name = cat.datasets[0].name
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        route(query)
    cat.context.dataset_id = cat.datasets[0].id
    assert route(query).query.source_id == cat.confirmed_plan.left.canonical_id


def test_payment_population_guard_handles_unpaid_and_grouping_paraphrases_without_coercion():
    payload = dict(
        intent="CREATE_VISUALIZATION",
        query=dict(
            project_id="p",
            source_kind="CANONICAL",
            source_id="canonical",
            group_by=["payment_status"],
            aggregations=[dict(op="count")],
        ),
    )
    assert validate(payload, "Phân bố toàn bộ trạng thái trả tiền").query
    payload["query"]["filters"] = [dict(field_id="payment_status", op="eq", value="PAID")]
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Phân bố toàn bộ trạng thái trả tiền")
    payload["intent"] = "QUERY_DATA"
    payload["query"]["group_by"] = []
    payload["query"]["aggregations"] = []
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(payload, "Cho xem giao dịch chưa thanh toán")
    payload["query"]["filters"] = [dict(field_id="payment_status", op="eq", value="UNPAID")]
    assert validate(payload, "Cho xem giao dịch chưa thanh toán").query.filters[0].value == "UNPAID"


def test_routing_schema_is_small_transport_contract_and_domain_query_shape_stays_compatible():
    from studio.contracts.agent import RoutingBatch
    from studio.contracts.data_query import DataQuery

    schema = RoutingBatch.model_json_schema()
    assert "PlanningRequest" not in schema.get("$defs", {})
    assert "ReconciliationPlan" not in schema.get("$defs", {})
    original = dict(
        project_id="p",
        source_kind="CANONICAL",
        source_id="canonical",
        filters=[dict(field_id="amount", op="gt", value="12.75")],
    )
    actual = DataQuery.model_validate(original)
    assert actual.model_dump()["filters"] == original["filters"]
    assert (
        actual.limit == 25
        and actual.result_scope == "ALL_MATCHING"
        and actual.null_policy == "PRESERVE"
    )


def test_routing_exception_fields_use_the_native_query_catalogue():
    from studio.agent_intents import compile_routing, routing_sources
    from studio.data_query import EXCEPTION_FIELDS

    cat = routing_catalogue()
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "EXCEPTIONS")
    assert [f["id"] for f in source["fields"]] == EXCEPTION_FIELDS
    query = dict(
        source_ref=source["ref"],
        select_fields=["case_id", "group_id"],
        filters=[dict(field_id="state", op="eq", value="OPEN")],
    )
    actual = compile_routing(
        json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=query)])),
        ["Xem ngoại lệ đang mở"],
        cat,
    )[0]
    assert actual.query.source_kind == "EXCEPTIONS"
    assert actual.query.source_id == "run"
    assert actual.query.filters[0].value == "OPEN"
    for field in ("match_group_id", "severity_basis", "id"):
        with pytest.raises(DomainError, match="AI_INVALID_FIELD"):
            compile_routing(
                json.dumps(
                    dict(
                        intents=[
                            dict(intent="QUERY_DATA", query=query | dict(select_fields=[field]))
                        ]
                    )
                ),
                ["Xem ngoại lệ"],
                cat,
            )


def test_routing_refuses_partial_reconciliation_and_duplicate_normalization_source():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    cat.datasets[0].tables[0].canonical_status = "PARTIAL"
    selection = dict(
        left_canonical_id=cat.confirmed_plan.left.canonical_id,
        right_canonical_id=cat.confirmed_plan.right.canonical_id,
        confirmed_run_id="run",
    )
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps(dict(intents=[dict(intent="RECONCILE_DATASETS", reconciliation=selection)])),
            ["Đối soát kỳ hiện tại"],
            cat,
        )
    cat.datasets[1].name = cat.datasets[0].name
    intent = dict(intent="PREPARE_NORMALIZATION", dataset_ids=[cat.datasets[0].id])
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(json.dumps(dict(intents=[intent])), ["Chuẩn hóa tệp"], cat)
    cat.context.dataset_id = cat.datasets[0].id
    assert compile_routing(json.dumps(dict(intents=[intent])), ["Chuẩn hóa tệp đang xem"], cat)[
        0
    ].dataset_ids == [cat.datasets[0].id]


def test_routing_gemini_mock_sends_bounded_schema_once_and_binds_native_source():
    from studio.agent_intents import routing_sources

    received, reserved = [], []
    cat = routing_catalogue()
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "CANONICAL")

    def handler(request):
        payload = json.loads(request.read())
        schema = payload["generationConfig"]["responseJsonSchema"]
        assert schema["properties"]["intents"]["minItems"] == 1
        assert schema["properties"]["intents"]["maxItems"] == 1
        assert "PlanningRequest" not in schema["$defs"]
        received.append(payload)
        reply = dict(
            intents=[
                dict(
                    intent="QUERY_DATA",
                    query=dict(source_ref=source["ref"], aggregations=[dict(op="count")]),
                )
            ]
        )
        return httpx.Response(
            200,
            json=dict(
                candidates=[
                    dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(reply))]))
                ]
            ),
        )

    provider = GeminiProvider(
        Settings(
            allow_external_ai=True,
            external_ai_request_budget=1,
            gemini_api_key="synthetic-key-only",
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        result = interpret_requests(
            provider,
            ["Đếm dữ liệu nguồn"],
            cat,
            WorkspacePolicy(
                mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1
            ),
            lambda: reserved.append(True) or True,
        )
    finally:
        provider.close()
    assert len(received) == len(reserved) == 1
    assert result[0].query.source_id == cat.confirmed_plan.left.canonical_id
    assert result[0].query.project_id == cat.context.project_id


def test_independent_variant_suite_keeps_original_gold_and_negative_rubric():
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures"
    gold = json.loads((fixtures / "agent-intents.json").read_text(encoding="utf-8"))
    variants = json.loads((fixtures / "agent-intent-variants.json").read_text(encoding="utf-8"))
    assert len(gold) == 80 and sum(bool(g.get("negative")) for g in gold) == 20
    assert len(variants) == len({g["id"] for g in variants}) == 24
    assert sum(bool(g.get("negative")) for g in variants) == 8
    assert not {g["goal"] for g in gold} & {g["goal"] for g in variants}
    assert {g["domain"] for g in variants} == {"delivery", "ledger"}
    assert all(g["intent"] in {"CLARIFY", "UNSUPPORTED"} for g in variants if g.get("negative"))
