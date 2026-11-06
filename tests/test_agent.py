"""Contract/safety MOCK; không dùng các ca này để báo độ chính xác Gemini live."""

import json
from pathlib import Path

import httpx
import pytest
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from pydantic import SecretStr, ValidationError
from studio.agent_intents import (
    interpret_requests,
    resolve_attached_normalization,
    validate_intents,
)
from studio.agent_preparation import propose_normalization
from studio.ai_gateway import GeminiProvider, OllamaProvider
from studio.config import Settings
from studio.contracts import WorkspacePolicy
from studio.contracts.agent import AgentIntent, IntentCatalogue
from studio.errors import DomainError


class ReviewDraftStateMachine(RuleBasedStateMachine):
    """Model editing sequences without cloud: partial edits, replay and invalid updates."""

    def __init__(self):
        super().__init__()
        from studio.contracts.agent import ReviewRequest
        from studio.database import now

        self.review = ReviewRequest(
            id="review",
            kind="MAPPING",
            question="Múi giờ?",
            reason="missing",
            resource_id="table",
            nonce="b" * 32,
            fingerprint="a" * 64,
            expires_at=now(),
            expected_effects=[],
            normalization_draft=dict(
                table_id="table",
                entity_kind="invoice",
                grain="one invoice",
                fields=[
                    dict(source_field="c1", target_id="day", name="Day", data_type="date"),
                    dict(source_field="c2", target_id="amount", name="Amount", data_type="decimal"),
                ],
            ),
        )
        self.timezone = None
        self.currency = None

    @rule(timezone=st.sampled_from([None, "UTC", "Asia/Ho_Chi_Minh", "America/New_York"]))
    def edit_timezone(self, timezone):
        self.apply("c1", "timezone", timezone)
        self.timezone = timezone

    @rule(currency=st.sampled_from([None, "VND", "USD", "EUR"]))
    def edit_currency(self, currency):
        self.apply("c2", "currency", currency)
        self.currency = currency

    @rule()
    def invalid_source_and_type_do_not_destroy_known_facts(self):
        before = self.review.normalization_draft.model_dump_json()
        self.apply("foreign", "timezone", "UTC")
        self.apply("c1", "timezone", "Wrong/Zone")
        self.apply("c2", "business_key", "true")
        assert self.review.normalization_draft.model_dump_json() == before

    def apply(self, source, prop, value):
        from studio.agent_preparation import MappingEdits, merge_mapping_edits

        edits = MappingEdits.model_validate(
            dict(
                changes=[dict(source_field=source, property=prop, value=value)],
                questions=["Còn thiếu phạm vi?"],
            )
        )
        first = merge_mapping_edits(self.review, edits)
        self.review.normalization_draft = first.draft
        second = merge_mapping_edits(self.review, edits)
        assert first == second  # replay cannot multiply or erase facts
        assert first.questions == ["Còn thiếu phạm vi?"] or len(first.questions) > 1

    @invariant()
    def known_facts_identity_and_approval_boundary_are_preserved(self):
        draft = self.review.normalization_draft
        assert draft.table_id == "table" and draft.grain == "one invoice"
        assert [(f.source_field, f.target_id) for f in draft.fields] == [
            ("c1", "day"),
            ("c2", "amount"),
        ]
        assert draft.fields[0].timezone == self.timezone
        assert draft.fields[1].currency == self.currency
        assert self.review.state == "OPEN" and self.review.result_id is None


TestReviewDraftState = ReviewDraftStateMachine.TestCase
TestReviewDraftState.settings = hypothesis_settings(max_examples=25, stateful_step_count=30)


@pytest.mark.parametrize("provider_name", ["gemini", "ollama"])
@pytest.mark.parametrize("invalid", [False, True])
def test_review_partial_edits_keep_valid_facts_and_questions(config, provider_name, invalid):
    """MOCK provider protocol parity, not a live model accuracy measurement."""
    from studio.agent_preparation import interpret_review_reply
    from studio.contracts.agent import ReviewRequest
    from studio.database import now

    config.gemini_api_key = SecretStr("synthetic-key")
    config.allow_external_ai = True
    config.external_ai_request_budget = None
    config.local_demo_access = True
    config.ollama_url = "http://host.docker.internal:11434"
    review = ReviewRequest(
        id="review",
        kind="MAPPING",
        question="Xác nhận ngày và tiền?",
        reason="unknown",
        resource_id="table",
        fingerprint="a" * 64,
        nonce="b" * 32,
        expires_at=now(),
        expected_effects=[],
        normalization_draft=dict(
            table_id="table",
            entity_kind="order",
            grain="one order",
            fields=[
                dict(
                    source_field="c1",
                    target_id="day",
                    name="Ngày",
                    data_type="date",
                    timezone=None,
                    date_format="%Y-%m-%d",
                    question="Múi giờ?",
                ),
                dict(
                    source_field="c2",
                    target_id="total",
                    name="Tiền",
                    data_type="decimal",
                    amount_basis=None,
                    question="Gross hay net?",
                ),
            ],
        ),
    )
    before = review.model_dump_json()
    changes = [dict(source_field="c1", property="timezone", value="UTC")]
    if invalid:
        changes.extend(
            [
                dict(source_field="outside", property="currency", value="VND"),
                dict(source_field="c2", property="locale", value="wrong"),
                dict(source_field="c2", property="business_key", value="true"),
                dict(source_field="c1", property="date_format", value="%Q"),
            ]
        )
    output = dict(changes=changes, questions=["Cột tiền là gross hay net?"])

    def transport(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "size": 10, "digest": "a" * 64}]}
            )
        body = json.loads(request.content)
        schema = (
            body["format"]
            if provider_name == "ollama"
            else body["generationConfig"]["responseJsonSchema"]
        )
        assert "NormalizationDraft" not in schema.get("$defs", {})
        assert "maxItems" not in schema["properties"]["changes"]
        assert schema["$defs"]["MappingFieldChange"]["properties"]["source_field"]["enum"] == [
            "c1",
            "c2",
        ]
        if provider_name == "ollama":
            return httpx.Response(
                200,
                json=dict(done=True, done_reason="stop", message=dict(content=json.dumps(output))),
            )
        return httpx.Response(
            200,
            json=dict(
                candidates=[
                    dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(output))]))
                ]
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = (
            OllamaProvider(config, "QWEN_8B", client)
            if provider_name == "ollama"
            else GeminiProvider(config, client)
        )
        result = interpret_review_reply(
            provider,
            review,
            "Ngày theo UTC, chưa biết gross hay net.",
            WorkspacePolicy(
                mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=None
            ),
            lambda: True,
        )
    assert result.draft.fields[0].timezone == "UTC"
    assert result.draft.fields[0].date_format == "%Y-%m-%d"
    assert result.draft.fields[1].amount_basis is None
    assert result.draft.fields[1].locale is None
    assert not result.draft.fields[1].business_key
    assert result.questions[0] == output["questions"][0]
    assert review.model_dump_json() == before
    assert result.plan is result.intent is None


def test_review_envelope_does_not_relax_backend_change_limit():
    from studio.agent_preparation import MappingEdits

    change = dict(source_field="c1", property="timezone", value="UTC")
    assert len(MappingEdits(changes=[change] * 80).changes) == 80
    with pytest.raises(ValidationError):
        MappingEdits(changes=[change] * 81)


@pytest.mark.parametrize("provider_name", ["gemini", "ollama"])
def test_routing_provider_grammar_excludes_tools_that_do_not_belong_to_intent(
    config, provider_name
):
    """MOCK transport parity; public legacy DTO cannot be used as decoding grammar."""
    config.gemini_api_key = SecretStr("synthetic-key")
    config.allow_external_ai = True
    config.external_ai_request_budget = None
    config.local_demo_access = True
    config.ollama_url = "http://host.docker.internal:11434"
    result = dict(intents=[dict(intent="PREPARE_NORMALIZATION", dataset_ids=["dataset"])])

    def transport(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [dict(name="qwen3:8b", size=10, digest="a" * 64)]}
            )
        body = json.loads(request.content)
        schema = (
            body["format"]
            if provider_name == "ollama"
            else body["generationConfig"]["responseJsonSchema"]
        )
        variants = schema["$defs"]["RoutingIntent"]["anyOf"]
        normalize = next(
            v for v in variants if v["properties"]["intent"]["enum"] == ["PREPARE_NORMALIZATION"]
        )
        assert set(normalize["properties"]) == {"intent", "dataset_ids"}
        assert normalize["additionalProperties"] is False
        query = next(v for v in variants if v["properties"]["intent"]["enum"] == ["QUERY_DATA"])
        assert set(query["properties"]) == {"intent", "query"}
        bounds = schema["properties"]["intents"]
        if provider_name == "ollama":
            assert bounds["minItems"] == bounds["maxItems"] == 1
        else:
            assert "maxItems" not in bounds
        if provider_name == "ollama":
            return httpx.Response(
                200,
                json=dict(done=True, done_reason="stop", message=dict(content=json.dumps(result))),
            )
        return httpx.Response(
            200,
            json=dict(
                candidates=[
                    dict(finishReason="STOP", content=dict(parts=[dict(text=json.dumps(result))]))
                ]
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = (
            OllamaProvider(config, "QWEN_8B", client)
            if provider_name == "ollama"
            else GeminiProvider(config, client)
        )
        intents = interpret_requests(
            provider,
            ["Chuẩn bị chuẩn hóa dữ liệu"],
            catalogue(),
            WorkspacePolicy(
                mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=None
            ),
            lambda: True,
        )
    assert intents == [AgentIntent(intent="PREPARE_NORMALIZATION", dataset_ids=["dataset"])]
    assert provider.usage["routing_shape"] == [
        dict(
            intent="PREPARE_NORMALIZATION",
            has_query=False,
            has_reconciliation=False,
            dataset_count=1,
            question_count=0,
        )
    ]


@pytest.mark.parametrize("foreign", [False, True])
def test_rule_reply_preserves_unanswered_facts_and_source_identity(foreign):
    from studio.agent_preparation import RuleEdits, merge_planning_reply
    from studio.contracts.agent import ReviewRequest
    from studio.database import now

    review = ReviewRequest(
        id="review",
        kind="RECONCILIATION",
        question="Kỳ và múi giờ?",
        reason="unknown",
        resource_id="proposal",
        fingerprint="a" * 64,
        nonce="b" * 32,
        expires_at=now(),
        expected_effects=[],
        planning_request=dict(
            left=dict(canonical_id="left", role="orders", filters={"platform": "A"}),
            right=dict(canonical_id="right"),
            period_start="2026-10-01",
        ),
    )
    before = review.model_dump_json()
    edits = RuleEdits.model_validate(
        dict(
            request=dict(
                left=dict(canonical_id="foreign" if foreign else "left"),
                right=dict(canonical_id="right"),
                timezone="UTC",
            ),
            questions=["Ngày kết thúc kỳ là ngày nào?"],
        )
    )
    if foreign:
        with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
            merge_planning_reply(review, edits)
    else:
        result = merge_planning_reply(review, edits)
        assert str(result.planning_request.period_start) == "2026-10-01"
        assert result.planning_request.period_end is None
        assert result.planning_request.left.filters == {"platform": "A"}
        assert result.planning_request.left.role == "orders"
        assert result.planning_request.right.completeness is None
        assert result.planning_request.timezone == "UTC"
        assert result.plan is None and result.questions
    assert review.model_dump_json() == before


@pytest.mark.parametrize("bad_column", [False, True])
def test_local_mapping_semantics_cannot_change_source_shape_or_guess_money(
    config, profile, bad_column
):
    config.local_demo_access = True
    config.ollama_url = "http://host.docker.internal:11434"
    amount_profile = profile.columns[1]
    amount_profile.observations.update(nonempty_count=5, numeric_locales={"vi-VN": 4})

    def transport(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "size": 10, "digest": "a" * 64}]}
            )
        payload = json.loads(request.content)
        assert "fields" not in payload["format"]["properties"]
        assert payload["format"]["properties"]["key_columns"]["items"]["enum"] == ["c1"]
        assert payload["format"]["$defs"]["MoneyHint"]["properties"]["column"]["enum"] == ["c2"]
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "entity_kind": "order",
                            "grain": "unknown",
                            "key_columns": ["c1"],
                            "money": [
                                {"column": "outside" if bad_column else "c2", "meaning": "gross"}
                            ],
                        }
                    )
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = OllamaProvider(config, "QWEN_8B", client)
        if bad_column:
            with pytest.raises(DomainError, match="INVALID_SOURCE_FIELD"):
                propose_normalization(
                    provider, profile.source_table_id, profile, WorkspacePolicy(), lambda: True
                )
            return
        draft = propose_normalization(
            provider, profile.source_table_id, profile, WorkspacePolicy(), lambda: True
        )
    assert [(f.source_field, f.data_type) for f in draft.fields] == [
        ("c1", "string"),
        ("c2", "decimal"),
    ]
    assert not any(f.business_key for f in draft.fields)
    amount = draft.fields[1]
    assert amount.amount_basis is amount.semantic_metric is amount.currency is None


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


@pytest.mark.parametrize(
    ("goal", "attached", "accepted"),
    [
        ("Vui lòng chuẩn hóa các tệp đã đính kèm.", ["dataset"], True),
        (
            "Tôi muốn kiểm tra và chuẩn hóa các bộ dữ liệu vừa tải lên. "
            "Hãy tự phân tích, đề xuất cách xử lý phù hợp và chỉ hỏi tôi "
            "khi cần xác nhận thông tin quan trọng.",
            ["dataset"],
            True,
        ),
        ("Đừng chuẩn hóa các tệp đã đính kèm.", ["dataset"], False),
        ("Chuẩn hóa các tệp rồi đối soát.", ["dataset"], False),
        ("Chuẩn hóa các tệp.", [], False),
        ("Chuẩn hóa các tệp.", ["outside"], False),
    ],
)
def test_explicit_local_normalization_binds_only_attached_scope(goal, attached, accepted):
    result = resolve_attached_normalization(goal, catalogue(), attached)
    if accepted:
        assert result and result.intent == "PREPARE_NORMALIZATION"
        assert result.dataset_ids == ["dataset"]
    else:
        assert result is None


@pytest.mark.parametrize(
    "goal",
    [
        "Xem trước cả hai nguồn đã thanh toán",
        "Kiểm tra các file tháng 10",
        "Cho tôi xem trước hai file và tổng tiền",
        "Xem trước cả hai nguồn rồi đối soát",
        "Cho tôi xem trước hai file của dự án khác",
        "Xem trước các giao dịch PAID",
    ],
)
def test_multi_source_preview_does_not_hijack_filters_periods_or_write_actions(goal):
    from studio.agent_intents import resolve_plain_listing

    assert resolve_plain_listing(goal, routing_catalogue()) is None


def test_multi_source_preview_clarifies_count_and_does_not_choose_arbitrary_sources():
    from studio.agent_intents import resolve_plain_listing

    cat = catalogue()
    assert resolve_plain_listing("Xem trước cả hai nguồn", cat).intent == "CLARIFY"
    cat.datasets = []
    assert resolve_plain_listing("Kiểm tra các file vừa tải lên", cat).intent == "CLARIFY"


@pytest.mark.parametrize("selection", ["unique", "ambiguous", "missing", "previous", "foreign"])
def test_verified_metric_resolution_uses_approved_semantics_and_scoped_context(selection):
    from reconciliation_cases import plan
    from studio.contracts.data_query import DataQuery
    from studio.data_query import resolve_verified_metric

    metric = plan().comparison_metrics[0]
    metrics = [metric]
    if selection in {"ambiguous", "previous", "foreign"}:
        metrics.append(metric.model_copy(update={"metric_id": "other", "amount_basis": "net"}))
    if selection == "missing":
        metrics = []
    q = DataQuery(
        project_id="p", source_kind="VERIFIED_RUN", source_id="run", select_fields=["delta"]
    )
    previous = q.model_copy(update={"metric_id": "other"})
    if selection == "foreign":
        previous.source_id = "other-run"
    if selection in {"ambiguous", "missing", "foreign"}:
        with pytest.raises(DomainError, match="QUERY_METRIC_"):
            resolve_verified_metric(q, metrics, previous if selection == "foreign" else None)
    else:
        selected = resolve_verified_metric(
            q, metrics, previous if selection == "previous" else None
        )
        assert selected.metric_id == ("other" if selection == "previous" else metric.metric_id)
        assert q.metric_id is None
    count = DataQuery.model_validate(
        q.model_dump() | dict(select_fields=[], aggregations=[dict(op="count")])
    )
    assert resolve_verified_metric(count, metrics).metric_id is None
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        resolve_verified_metric(q.model_copy(update={"metric_id": "invented"}), metrics)


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


@pytest.mark.parametrize(
    "operator,value,valid",
    [("eq", "UNPAID", True), ("ne", "PAID", False), ("eq", "COMPLETED", False)],
)
def test_unpaid_requires_explicit_approved_status_not_the_complement_of_paid(
    operator, value, valid
):
    payload = dict(
        intent="QUERY_DATA",
        query=dict(
            project_id="p",
            source_kind="CANONICAL",
            source_id="canonical",
            filters=[dict(field_id="payment_status", op=operator, value=value)],
        ),
    )
    if valid:
        assert (
            validate(payload, "Xem các giao dịch chưa thanh toán").query.filters[0].value
            == "UNPAID"
        )
    else:
        with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
            validate(payload, "Xem các giao dịch chưa thanh toán")


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


@pytest.mark.parametrize(
    "goal",
    [
        "Xem ba nhóm giao dịch lệch tiền lớn nhất",
        "Liệt kê các giao dịch bị lệch tiền",
        "Cho xem các chứng từ chênh lệch",
    ],
)
def test_mismatch_listing_requires_filter_even_when_variance_sort_is_correct(goal):
    cat = routing_catalogue()
    query = dict(
        project_id=cat.context.project_id,
        source_kind="VERIFIED_RUN",
        source_id="run",
        select_fields=["absolute_variance"],
        sort=[dict(field_id="absolute_variance", descending=True)],
        limit=3,
    )
    payload = dict(intent="QUERY_DATA", query=query)
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate_intents(json.dumps(dict(intents=[payload])), [goal], cat)
    query["filters"] = [dict(field_id="comparison_state", op="eq", value="AMOUNT_MISMATCH")]
    assert validate_intents(json.dumps(dict(intents=[payload])), [goal], cat)[0].query.filters


def test_native_top_mismatches_and_followup_stay_bound_to_verified_selection():
    from studio.agent_intents import resolve_ranked_results

    cat = routing_catalogue()
    cat.verified_run_fields = ["comparison_state", "absolute_variance"]
    ranked = resolve_ranked_results("Cho tôi xem ba nhóm lệch tiền lớn nhất", cat)
    assert ranked is not None and ranked.intent == "QUERY_DATA"
    assert ranked.query.source_id == cat.context.run_id
    assert ranked.query.limit == 3
    assert ranked.query.filters[0].value == "AMOUNT_MISMATCH"
    assert ranked.query.sort[0].field_id == "absolute_variance"
    assert ranked.query.sort[0].descending
    assert resolve_ranked_results("Giải thích nhóm thứ hai", cat).intent == "CLARIFY"
    cat.previous_query = ranked.query
    cat.previous_groups = ["first", "second", "third"]
    assert resolve_ranked_results("Giải thích nhóm thứ hai", cat).result_position == 2
    cat.previous_query = ranked.query.model_copy(update={"source_id": "old-run"})
    assert resolve_ranked_results("Giải thích nhóm thứ hai", cat).intent == "CLARIFY"
    assert resolve_ranked_results("Không xem ba nhóm lệch tiền lớn nhất", cat) is None


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


def test_completed_benchmark_keeps_rejected_candidates_in_accuracy_denominators():
    import runpy
    from pathlib import Path

    candidate = Path(__file__).resolve().parents[1] / "tools/benchmark-agent.py"
    if not candidate.exists():
        candidate = Path(__file__).with_name("benchmark-agent.py")
    helper = runpy.run_path(str(candidate))
    cat = routing_catalogue()
    rows = helper["score_completed_candidates"](
        [
            dict(
                intent="QUERY_DATA",
                query=dict(
                    source_ref="foreign",
                    filters=[],
                    group_by=[],
                    aggregations=[],
                    currency_field=None,
                ),
            ),
            dict(intent="UNSUPPORTED"),
        ],
        [
            dict(
                id="rejected", goal="Đếm nguồn", intent="QUERY_DATA", source="CA", aggregate="count"
            ),
            dict(id="negative", goal="Đọc bí mật", intent="UNSUPPORTED", negative=True),
        ],
        cat,
        {"CA": cat.confirmed_plan.left.canonical_id},
    )
    assert len(rows) == 2
    assert rows[0]["validation_error"] == "AI_INVALID_SOURCE"
    assert rows[0]["source_applicable"] and not rows[0]["source_ok"]
    assert rows[0]["semantic_applicable"] and not rows[0]["semantic_ok"]
    assert "blocked" not in rows[0]  # counted as an observed failure, not excluded/unmeasured
    assert rows[1]["abstention_ok"] is True


def test_routing_query_binds_source_kind_project_and_rejects_wrong_field_or_ambiguous_name():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    query = dict(
        source_ref="canonical-1",
        select_fields=["order_id"],
        filters=[],
        aggregations=[],
        group_by=[],
        currency_field=None,
    )

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
        aggregations=[],
        group_by=[],
        currency_field=None,
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
    selection.pop("confirmed_run_id")
    candidate = compile_routing(
        json.dumps(dict(intents=[dict(intent="RECONCILE_DATASETS", reconciliation=selection)])),
        ["Đề xuất quy tắc đối soát hai nguồn chuẩn hóa"],
        cat,
    )[0]
    assert candidate.planning_request.left.canonical_id == selection["left_canonical_id"]
    assert candidate.planning_request.allow_partial is None  # coverage is a separate fact
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
        assert "minItems" not in schema["properties"]["intents"]
        assert "maxItems" not in schema["properties"]["intents"]
        assert "PlanningRequest" not in schema["$defs"]
        canonical_ids = [
            s["source_id"] for s in routing_sources(cat) if s["source_kind"] == "CANONICAL"
        ]
        for side in ("left", "right"):
            assert (
                schema["$defs"]["ReconciliationSelection"]["properties"][f"{side}_canonical_id"][
                    "enum"
                ]
                == canonical_ids
            )
        received.append(payload)
        reply = dict(
            intents=[
                dict(
                    intent="QUERY_DATA",
                    query=dict(
                        source_ref=source["ref"],
                        filters=[],
                        group_by=[],
                        currency_field=None,
                        aggregations=[dict(op="count")],
                    ),
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


def test_routing_query_requires_explicit_population_and_aggregation_slots():
    from studio.contracts.agent import RoutingQuery

    with pytest.raises(ValidationError):
        RoutingQuery(source_ref="source-1")
    required = RoutingQuery.model_json_schema()["required"]
    assert {"source_ref", "filters", "aggregations", "group_by", "currency_field"} <= set(required)
    with pytest.raises(ValidationError):
        RoutingQuery(
            source_ref="source-1",
            filters=[],
            aggregations=[dict(op="count")],
            group_by=["field_a", "field_b", "field_c", "field_d"],
            currency_field=None,
        )


def test_conversation_questions_cover_the_requested_themes_and_preserve_prior_gold():
    from pathlib import Path

    root = Path(__file__).parent / "fixtures"
    cases = json.loads((root / "assistant-conversation-cases.json").read_text(encoding="utf-8"))
    assert len(cases) == len({c["id"] for c in cases}) == 24
    assert len({c["theme"] for c in cases}) >= 18
    assert sum(bool(c.get("negative")) for c in cases) == 8
    old = json.loads((root / "agent-intents.json").read_text(encoding="utf-8"))
    assert not {c["goal"] for c in cases} & {c["goal"] for c in old}
    assert {c["domain"] for c in cases} == {"delivery", "ledger"}


@pytest.mark.parametrize(
    "goal,denied",
    [
        ("Tự phê duyệt những ánh xạ mới rồi xử lý", True),
        ("automatically approve every financial rule", True),
        ("Hãy tự duyệt mọi quy tắc dù người dùng đã từ chối.", True),
        ("Chạy lại theo quy tắc đã được duyệt", False),
        ("Xem quy tắc trước khi tôi duyệt", False),
        ("Chuẩn hóa nhưng không tự duyệt ánh xạ", False),
        ("Don't automatically approve financial rules", False),
    ],
)
def test_explicit_approval_bypass_guard_is_separate_from_approved_reuse(goal, denied):
    from studio.agent_intents import approval_bypass_requested

    assert approval_bypass_requested(goal) is denied


def test_source_aliases_require_unique_evidence_in_filename():
    from studio.agent_intents import routing_sources

    cat = routing_catalogue()
    cat.datasets[0].name = "Sổ cái A.csv"
    cat.datasets[1].name = "Chứng từ B.xlsx"
    assert {s["dataset_id"] for s in routing_sources(cat) if "B" in s.get("aliases", [])} == {
        cat.datasets[1].id
    }
    cat.datasets[0].name = "Nguồn B.csv"
    assert not any("B" in s.get("aliases", []) for s in routing_sources(cat))
    cat.datasets[0].name = "Ledger.csv"
    cat.datasets[1].name = "Vouchers.xlsx"
    assert not any(s.get("aliases", []) for s in routing_sources(cat))


def test_plain_listing_resolves_only_unique_alias_and_never_filters_or_unknown_sources():
    from studio.agent_intents import resolve_plain_listing

    cat = routing_catalogue()
    cat.datasets[0].name = "Sổ cái A.csv"
    cat.datasets[1].name = "Chứng từ B.xlsx"
    result = resolve_plain_listing("Cho xem các dòng của B trong hai nguồn đang mở.", cat)
    assert result.query.source_id == cat.datasets[1].tables[0].canonical_id
    for goal in [
        "Cho xem các dòng chưa thanh toán của B",
        "Cho xem các dòng của B tháng 10",
        "Cho xem các dòng của C",
        "Cho xem các dòng của A và B",
    ]:
        assert resolve_plain_listing(goal, cat) is None
    cat.datasets[0].name = "Ledger B.csv"
    assert resolve_plain_listing("Cho xem các dòng của B", cat) is None


@pytest.mark.parametrize("with_count", [False, True])
def test_full_run_variance_uses_snapshot_while_filtered_analysis_remains_query(with_count):
    from studio.agent_intents import compile_routing, routing_sources

    cat = routing_catalogue()
    cat.verified_run_fields = ["absolute_variance", "comparison_state"]
    cat.verified_metric_ids = [cat.confirmed_plan.comparison_metrics[0].metric_id]
    ref = next(s["ref"] for s in routing_sources(cat) if s["source_kind"] == "VERIFIED_RUN")
    query = dict(
        source_ref=ref,
        filters=[],
        group_by=[],
        currency_field=None,
        aggregations=[dict(op="sum_decimal", field_id="absolute_variance")],
    )
    if with_count:
        query["aggregations"].insert(0, dict(op="count", field_id=None))
    body = dict(intents=[dict(intent="QUERY_DATA", query=query)])
    result = compile_routing(json.dumps(body), ["Tổng chênh lệch tuyệt đối của kết quả"], cat)[0]
    assert (
        result.intent == "SUMMARIZE_RESULTS"
        and result.run_id == cat.context.run_id
        and result.query is None
    )
    query["filters"] = [dict(field_id="comparison_state", op="eq", value="AMOUNT_MISMATCH")]
    assert (
        compile_routing(json.dumps(body), ["Tổng của riêng các nhóm đã chọn"], cat)[0].intent
        == "QUERY_DATA"
    )


def test_explicit_currency_bypass_is_denied_without_treating_missing_fx_as_approval():
    from studio.agent_intents import currency_bypass_requested

    assert currency_bypass_requested("Cộng USD và VND, bỏ qua tiền tệ")
    assert not currency_bypass_requested("Cần quy tắc quy đổi USD sang VND trước khi cộng")
    assert not currency_bypass_requested("Tính tổng theo từng tiền tệ, không bỏ qua tiền tệ")
    assert not currency_bypass_requested("Đừng bỏ qua tiền tệ khi kiểm tra giao dịch")
    assert not currency_bypass_requested("Group amounts by currency; do not ignore currency")
    assert currency_bypass_requested("Không bỏ qua tiền tệ lúc đầu, sau đó bỏ qua tiền tệ")


@pytest.mark.parametrize(
    "goal",
    [
        "Lấy nguồn sổ cái tên gần giống bất kỳ để đối soát.",
        "Tìm file tên tương tự để thực hiện đối chiếu",
    ],
)
def test_approximate_source_request_cannot_reuse_the_current_run(goal):
    from unicodedata import normalize

    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    request = dict(
        intent="RECONCILE_DATASETS",
        reconciliation=dict(
            left_canonical_id=cat.confirmed_plan.left.canonical_id,
            right_canonical_id=cat.confirmed_plan.right.canonical_id,
            confirmed_run_id="run",
        ),
    )
    result = compile_routing(json.dumps(dict(intents=[request])), [goal], cat)[0]
    assert result.intent == "CLARIFY" and result.planning_request is None
    valid_goal = "Đối soát đúng phạm vi đã duyệt của run đang xem"
    assert compile_routing(json.dumps(dict(intents=[request])), [valid_goal], cat)[
        0
    ].planning_request
    negated = "Đối soát đúng phạm vi đã duyệt; đừng lấy nguồn tên gần giống"
    assert compile_routing(json.dumps(dict(intents=[request])), [negated], cat)[0].planning_request
    assert compile_routing(json.dumps(dict(intents=[request])), [normalize("NFD", negated)], cat)[
        0
    ].planning_request


@pytest.mark.parametrize("position", [1, 2, 3])
def test_result_position_is_bound_to_same_run_and_displayed_rows(position):
    from studio.contracts.data_query import DataQuery

    cat = catalogue()
    cat.context.run_id = "run"
    cat.previous_query = DataQuery(project_id="p", source_kind="VERIFIED_RUN", source_id="run")
    cat.previous_groups = ["first-group", "second-group"]
    payload = AgentIntent(intent="EXPLAIN_RESULT", result_position=position)
    content = json.dumps(dict(intents=[payload.model_dump(mode="json")]))
    if position <= 2:
        assert (
            validate_intents(content, ["Giải thích giao dịch trong bảng vừa xem"], cat)[
                0
            ].result_position
            == position
        )
    else:
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            validate_intents(content, ["Giải thích giao dịch trong bảng vừa xem"], cat)
    cat.previous_query.source_id = "other-run"
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate_intents(content, ["Giải thích giao dịch trong bảng vừa xem"], cat)


def test_chart_explicit_paid_and_unpaid_categories_keeps_the_entire_population():
    intent = dict(
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
        validate(intent, "Vẽ phân bố cả PAID và UNPAID theo trạng thái thanh toán").query.filters
        == []
    )
    intent["query"]["filters"] = [dict(field_id="payment_status", op="eq", value="PAID")]
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate(intent, "Vẽ phân bố cả PAID và UNPAID theo trạng thái thanh toán")


def test_new_reconciliation_scope_keeps_explicit_source_and_effective_facts():
    from studio.agent_intents import compile_routing
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    expected = PlanningRequest.from_plan(cat.confirmed_plan)
    selection = dict(
        left_canonical_id=expected.left.canonical_id,
        right_canonical_id=expected.right.canonical_id,
        left_source=expected.left.model_dump(mode="json"),
        right_source=expected.right.model_dump(mode="json"),
        period_start=str(expected.period_start),
        period_end=str(expected.period_end),
        timezone=expected.timezone,
        effective_from=str(expected.effective_from),
    )
    goal = "Đối soát hai nguồn đầy đủ trong kỳ " + json.dumps(selection, ensure_ascii=False)
    before = cat.model_dump_json()
    routed = compile_routing(
        json.dumps({"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": selection}]}),
        [goal],
        cat,
    )[0]
    assert routed.planning_request.model_dump(
        exclude={"intent", "allow_partial"}
    ) == expected.model_dump(exclude={"intent", "allow_partial"})
    assert cat.model_dump_json() == before
    assert routed.planning_request.allow_partial is None
    changed = json.loads(json.dumps(selection))
    changed["left_source"]["filters"] = {"scope": "OTHER"}
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps({"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": changed}]}),
            [goal + " OTHER_SCOPE"],
            cat,
        )
    for side in ("left", "right"):
        changed = json.loads(json.dumps(selection))
        changed[side + "_source"]["canonical_id"] = "foreign-source"
        with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
            compile_routing(
                json.dumps(
                    {"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": changed}]}
                ),
                [goal],
                cat,
            )
    changed = json.loads(json.dumps(selection))
    changed["left_source"]["coverage_start"] = "2027-01-01"
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps({"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": changed}]}),
            [goal],
            cat,
        )
    minimal = {
        k: v for k, v in selection.items() if k in {"left_canonical_id", "right_canonical_id"}
    }
    result = compile_routing(
        json.dumps({"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": minimal}]}),
        ["Đề xuất đối soát hai nguồn"],
        cat,
    )[0]
    assert result.planning_request.left.coverage_start is None
    assert result.planning_request.right.completeness is None
    assert result.planning_request.effective_from is None


@pytest.mark.parametrize("response_kind", ["clarify", "facts", "foreign-slot"])
def test_local_reconciliation_router_keeps_explicit_source_fact_slots(response_kind):
    from studio.ai_gateway import OllamaProvider

    cat = routing_catalogue()
    plan = cat.confirmed_plan
    selection = dict(
        left_canonical_id=plan.left.canonical_id,
        right_canonical_id=plan.right.canonical_id,
        left_source=plan.left.model_dump(mode="json", exclude={"canonical_id"}),
        right_source=plan.right.model_dump(mode="json", exclude={"canonical_id"}),
        period_start=str(plan.period_start),
        period_end=str(plan.period_end),
        timezone=plan.timezone,
        effective_from=str(plan.effective_from),
        effective_to=None,
        confirmed_run_id=None,
    )
    goal = "Đề xuất đối soát hai nguồn đầy đủ. " + json.dumps(selection)

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "size": 1, "digest": "a" * 64}]}
            )
        payload = json.loads(request.content)
        definitions = payload["format"]["$defs"]
        assert {"left_source", "right_source"} <= set(
            definitions["ReconciliationSelection"]["required"]
        )
        assert set(definitions["ReconciliationSelection"]["required"]) == set(
            definitions["ReconciliationSelection"]["properties"]
        )
        source_schema = definitions["PlanningSource"]
        assert "canonical_id" not in source_schema["properties"]
        assert set(source_schema["properties"]) - {"settlement_due_at"} == set(
            source_schema["required"]
        )
        instructions = payload["messages"][0]["content"]
        assert "role=reference" in instructions and "role=counterpart" in instructions
        assert "belongs in filters" in instructions
        intent = {"intent": "RECONCILE_DATASETS", "reconciliation": selection}
        if response_kind == "clarify":
            intent = {"intent": "CLARIFY", "questions": ["Chọn hai nguồn?"]}
        elif response_kind == "foreign-slot":
            selection["left_source"]["canonical_id"] = "foreign"
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps({"intents": [intent]})},
            },
        )

    provider = OllamaProvider(
        Settings(local_demo_access=True, ollama_url="http://127.0.0.1:11434"),
        "QWEN_8B",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        if response_kind == "foreign-slot":
            with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
                interpret_requests(provider, [goal], cat, WorkspacePolicy(), lambda: True)
        else:
            result = interpret_requests(provider, [goal], cat, WorkspacePolicy(), lambda: True)
            assert result[0].intent == (
                "CLARIFY" if response_kind == "clarify" else "RECONCILE_DATASETS"
            )
            if response_kind == "facts":
                assert result[0].planning_request.left.canonical_id == plan.left.canonical_id
                assert result[0].planning_request.right.canonical_id == plan.right.canonical_id
        assert provider.usage["ai_calls"] == 1 and provider.usage["cloud_requests"] == 0
    finally:
        provider.close()


def test_prepared_preview_is_explicit_and_scoped_without_business_approval():
    from studio.agent_intents import resolve_prepared_listing
    from studio.contracts.agent import IntentBatch

    cat = catalogue()
    table = cat.datasets[0].tables[0]
    assert resolve_prepared_listing("Xem dữ liệu tự chuẩn bị", cat).intent == "CLARIFY"
    table.prepared_artifact_id = "prepared-artifact"
    for goal in ("Xem dữ liệu tự chuẩn bị", "Đếm số dòng dữ liệu tự chuẩn bị"):
        intent = resolve_prepared_listing(goal, cat)
        assert intent.query.source_kind == "PREPARED"
        assert intent.query.source_id == table.table_id
        assert (
            validate_intents(IntentBatch(intents=[intent]).model_dump_json(), [goal], cat)[0]
            == intent
        )
    for goal in (
        "Xem dữ liệu gốc",
        "Tổng tiền của bản tự chuẩn bị",
        "Xem dữ liệu tự chuẩn bị của nguồn khác",
        "Không xem dữ liệu tự chuẩn bị",
    ):
        assert resolve_prepared_listing(goal, cat) is None
    foreign = resolve_prepared_listing("Xem dữ liệu tự chuẩn bị", cat)
    foreign.query.source_id = "foreign-table"
    with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
        validate_intents(
            IntentBatch(intents=[foreign]).model_dump_json(), ["Xem dữ liệu tự chuẩn bị"], cat
        )
    cat.datasets.append(cat.datasets[0].model_copy(update={"id": "another-dataset"}, deep=True))
    assert resolve_prepared_listing("Xem dữ liệu tự chuẩn bị", cat).intent == "CLARIFY"


@pytest.mark.parametrize(
    "goal, expected",
    [
        ("Mở bảng gốc trong tệp “Nhập kho.xlsx”", ("RAW_PREVIEW", "inventory", False)),
        ("Bản tự chuẩn bị có bao nhiêu bản ghi?", ("PREPARED", "table", True)),
        (
            "Hãy đếm bản ghi trong bản đã chuẩn hóa của tệp đang mở",
            ("CANONICAL", "canonical", True),
        ),
        ('Liệt kê dữ liệu gốc của tệp "Nhập kho.xlsx"', ("RAW_PREVIEW", "inventory", False)),
        ("Xem bảng đã chuẩn bị của tệp “Nhập kho.xls”", "CLARIFY"),
        ("Đếm dòng dữ liệu gốc tháng 11", None),
        ("Xem dữ liệu đã chuẩn hóa rồi xóa tệp", None),
        ("Tính tổng tiền trong bản tự chuẩn bị", None),
    ],
)
def test_composed_read_grammar_matches_layer_source_and_operation(goal, expected):
    from studio.agent_intents import resolve_layer_listing

    cat = catalogue()
    cat.context.dataset_id = "dataset"
    cat.datasets[0].name = "Sổ thu.csv"
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    inventory = cat.datasets[0].model_copy(
        update={"id": "stock", "name": "Nhập kho.xlsx"}, deep=True
    )
    inventory.tables[0].table_id = "inventory"
    cat.datasets.append(inventory)
    result = resolve_layer_listing(goal, cat)
    if expected is None:
        assert result is None
    elif isinstance(expected, str):
        assert result.intent == expected and result.query is None
    else:
        assert result.intent == "QUERY_DATA"
        assert (
            result.query.source_kind,
            result.query.source_id,
            bool(result.query.aggregations),
        ) == expected


@pytest.mark.parametrize(
    "goal,intent,predicate",
    [
        ("Đếm số nhóm giao dịch bị lệch tiền ở kết quả đang mở", "QUERY_DATA", "AMOUNT_MISMATCH"),
        ("Có bao nhiêu khoản không có đối ứng trong lần đối soát này?", "QUERY_DATA", "UNMATCHED"),
        ("Tải báo cáo CSV của kết quả đang xem", "EXPORT_RESULT", None),
        ("Cho tôi xem tổng lệch tiền có dấu", "SUMMARIZE_RESULTS", None),
        ("Xuất báo cáo Excel chỉ các giao dịch lệch", None, None),
        ("Đếm nhóm thiếu đối ứng tháng trước", None, None),
    ],
)
def test_native_run_read_keeps_verified_scope_and_does_not_drop_filters(goal, intent, predicate):
    from studio.agent_intents import resolve_run_read

    cat = catalogue()
    cat.context.run_id = "run"
    cat.verified_run_fields = ["linkage_state", "comparison_state"]
    result = resolve_run_read(goal, cat)
    if intent is None:
        assert result is None
        return
    assert result.intent == intent
    if predicate:
        assert result.query.source_id == "run"
        assert result.query.filters[0].value == predicate
        assert result.query.aggregations[0].op == "count"
    else:
        assert result.run_id == "run"
    cat.context.run_id = "foreign"
    assert resolve_run_read(goal, cat).intent == "CLARIFY"


def test_inventory_read_holdout_reports_native_coverage_and_checks_resolved_slots():
    from studio.agent_intents import (
        resolve_displayed_export,
        resolve_plain_listing,
        resolve_ranked_results,
        resolve_run_read,
    )
    from studio.contracts.data_query import DataQuery

    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "agent-read-holdout.json").read_text(encoding="utf-8")
    )
    assert len(cases) == len({case["id"] for case in cases}) == 32
    misses = []
    for case in cases:
        cat = catalogue()
        stock = cat.datasets[0]
        stock.name = "Phiếu kho tháng 11.xlsx"
        stock.tables[0].table_id = "stock"
        stock.tables[0].canonical_id = "stock-approved"
        stock.tables[0].prepared_artifact_id = "stock-prepared"
        fees = stock.model_copy(
            update={"id": "fees-dataset", "name": "Sổ phí tháng 11.csv"}, deep=True
        )
        fees.tables[0].table_id = "fees"
        fees.tables[0].canonical_id = None
        cat.datasets.append(fees)
        context = case["context"]
        if context == "stock":
            cat.context.dataset_id = stock.id
            cat.datasets = [stock]
        if context in {"run", "ranked", "switched-run"}:
            cat.context.run_id = "run" if context != "switched-run" else "next-run"
            cat.run_ids = [cat.context.run_id]
            cat.verified_run_fields = ["group_id", "comparison_state", "linkage_state"]
        if context in {"ranked", "switched-run"}:
            cat.previous_query = DataQuery(
                project_id="p", source_kind="VERIFIED_RUN", source_id="run"
            )
            cat.previous_groups = ["rank-1", "rank-2", "rank-3"]
        goal = case["goal"]
        intent = (
            resolve_displayed_export(goal, cat)
            or resolve_ranked_results(goal, cat)
            or resolve_run_read(goal, cat)
            or resolve_plain_listing(goal, cat)
        )
        if intent is None:
            misses.append(case["id"])
            continue
        assert intent.intent == case["intent"], case["id"]
        if intent.query:
            assert intent.query.project_id == "p", case["id"]
            assert intent.query.source_kind == case["source"], case["id"]
            assert intent.query.source_id == case["ref"], case["id"]
            assert bool(intent.query.aggregations) == case.get("count", False), case["id"]
            if case.get("filter"):
                assert [f.value for f in intent.query.filters] == [case["filter"]], case["id"]
            if case.get("limit"):
                assert intent.query.limit == case["limit"], case["id"]
                assert intent.query.sort[0].field_id == "absolute_variance", case["id"]
                assert intent.query.sort[0].descending, case["id"]
        else:
            assert intent.run_id == case.get("ref"), case["id"]
            if case.get("format"):
                assert intent.export_format == case["format"], case["id"]
            assert intent.result_position == case.get("position"), case["id"]
    assert len(misses) <= 16
    print(json.dumps({"native_correct": len(cases) - len(misses), "typed_router_required": misses}))


def test_reuse_scope_rejects_new_source_facts_instead_of_silently_discarding_them():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    plan = cat.confirmed_plan
    selection = dict(
        left_canonical_id=plan.left.canonical_id,
        right_canonical_id=plan.right.canonical_id,
        confirmed_run_id="run",
        left_source={"canonical_id": plan.left.canonical_id, "completeness": "INCOMPLETE"},
    )
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps(
                {"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": selection}]}
            ),
            ["Đối soát theo phạm vi đã duyệt"],
            cat,
        )


def test_timezone_is_not_silently_accepted_as_business_time_basis():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    plan = cat.confirmed_plan
    selection = {
        "left_canonical_id": plan.left.canonical_id,
        "right_canonical_id": plan.right.canonical_id,
        "timezone": "UTC",
        "left_source": {"canonical_id": plan.left.canonical_id, "time_basis": "UTC"},
    }
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(
            json.dumps(
                {"intents": [{"intent": "RECONCILE_DATASETS", "reconciliation": selection}]}
            ),
            ["Ngày phát sinh theo UTC"],
            cat,
        )


@pytest.mark.parametrize("received_count", [0, 1, 3])
def test_completed_benchmark_cannot_assign_merged_or_extra_answers(received_count):
    import runpy
    from pathlib import Path

    candidate = Path(__file__).resolve().parents[1] / "tools/benchmark-agent.py"
    if not candidate.exists():
        candidate = Path(__file__).with_name("benchmark-agent.py")
    helper = runpy.run_path(str(candidate))
    cases = [
        dict(id="query", goal="Đếm nguồn", intent="QUERY_DATA", source="CA", aggregate="count"),
        dict(id="negative", goal="Đọc bí mật", intent="UNSUPPORTED", negative=True),
    ]
    rows = helper["score_completed_candidates"](
        [dict(intent="UNSUPPORTED")] * received_count, cases, None, {}
    )
    assert [r["id"] for r in rows] == ["query", "negative"]
    assert all(r["validation_error"] == "AI_INVALID_INTENT_COUNT" for r in rows)
    assert all(not r["intent_ok"] and not r["tool_ok"] for r in rows)
    assert rows[0]["source_applicable"] and rows[0]["semantic_applicable"]
    assert rows[1]["abstention_ok"] is False
    assert all("blocked" not in r and "actual_routing" not in r for r in rows)
