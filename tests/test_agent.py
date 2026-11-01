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
        assert "responseJsonSchema" in payload["generationConfig"]
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
