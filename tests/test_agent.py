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


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Hãy đối soát ba nguồn doanh thu quý III/2026.", True),
        ("Đề xuất đối soát 3 tệp trong dự án.", True),
        ("Xem kết quả đối soát ba nguồn.", False),
        ("Đừng đối soát ba nguồn.", False),
        ("Chuẩn hóa ba nguồn rồi đối soát và xuất Excel.", False),
    ],
)
def test_three_source_proposals_do_not_take_over_reads_or_export_sequences(goal, expected):
    from studio.agent_intents import requests_three_source_reconciliation

    assert requests_three_source_reconciliation(goal) is expected


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
                200, json={"models": [{"name": "qwen3.8:27b", "size": 10, "digest": "a" * 64}]}
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
            OllamaProvider(config, "QWEN_27B", client)
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
                200, json={"models": [dict(name="qwen3.8:27b", size=10, digest="a" * 64)]}
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
        # A catalogue without an approved current run cannot offer a generated
        # run ID as a planning capability, even if historical run_ids exist.
        run_key = "run" if provider_name == "ollama" else "confirmed_run_id"
        assert schema["$defs"]["ReconciliationSelection"]["properties"][run_key] == {"type": "null"}
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
            OllamaProvider(config, "QWEN_27B", client)
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
    from types import SimpleNamespace

    from reconciliation_cases import catalogue
    from studio.agent_preparation import RuleEdits, interpret_review_reply
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

    def request(prompt, _policy, _reserve, validate, **_options):
        evidence = json.loads(prompt[1]["content"])
        assert evidence["allowed_evidence_ids"] == ["left", "right"]
        assert [source["canonical_id"] for source in evidence["untrusted_source_catalogue"]] == [
            "left",
            "right",
        ]
        assert "fields" in evidence["untrusted_source_catalogue"][0]
        assert evidence["compatible_metrics"][0]["metric_id"] == "item_gross"
        return validate(edits.model_dump_json(exclude_unset=True))

    def interpret():
        return interpret_review_reply(
            SimpleNamespace(request_typed=request),
            review,
            "Kỳ theo giờ UTC.",
            WorkspacePolicy(),
            lambda: True,
            [catalogue(side, []) for side in ("left", "right")],
        )

    if foreign:
        with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
            interpret()
    else:
        result = interpret()
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
                200, json={"models": [{"name": "qwen3.8:27b", "size": 10, "digest": "a" * 64}]}
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
        provider = OllamaProvider(config, "QWEN_27B", client)
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
    ("goal", "inventory", "prepare"),
    [
        ("Dự án này có những tệp nào?", True, False),
        ("Liệt kê toàn bộ nguồn dữ liệu trong dự án", True, False),
        ("Có bao nhiêu nguồn dữ liệu trong dự án?", True, False),
        ("Liệt kê các dòng lỗi của nguồn", False, False),
        ("Hãy kiểm tra và chuẩn hóa cả ba nguồn dữ liệu", False, True),
        ("Chuẩn bị toàn bộ dữ liệu trong dự án giúp tôi", False, True),
        ('Chuẩn bị tệp "Ledger B.xlsx"', False, True),
        ("Chuẩn hóa dữ liệu", False, False),
        ("Đừng chuẩn hóa toàn bộ dữ liệu", False, False),
        ("Chuẩn bị cả ba nguồn rồi chạy đối soát", False, False),
        ("Trước tiên kiểm tra các tệp, sau đó đề xuất ánh xạ.", False, True),
        ("Chuẩn bị dữ liệu để đối soát, nhưng chưa chạy đối soát.", False, True),
        ("Kiểm tra riêng sổ kế toán.", False, False),
        ("Chuẩn bị cả ba nguồn, nhưng hãy chạy đối soát.", False, False),
        ("Chuẩn bị cả ba nguồn để đối soát rồi xuất Excel.", False, False),
        ("Chuẩn bị cả ba nguồn, sau đó tự phê duyệt ánh xạ.", False, False),
        ("Chuẩn bị ba nguồn trong dự án tháng trước.", False, False),
        ("Chuẩn bị tất cả dữ liệu ngoại trừ tệp sao kê.", False, False),
        ("Chưa chuẩn hóa toàn bộ dữ liệu. Hãy đọc ba tệp.", False, False),
        (
            (Path(__file__).parent / "fixtures/assistant-project-preparation-vi.txt")
            .read_text(encoding="utf-8")
            .strip(),
            False,
            True,
        ),
    ],
)
def test_project_source_commands_exclude_row_reads_and_compound_actions(goal, inventory, prepare):
    from studio.agent_intents import requests_source_preparation
    from studio.dataset_status import asks_source_inventory

    assert asks_source_inventory(goal) is inventory
    assert requests_source_preparation(goal) is prepare


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


@pytest.mark.parametrize(
    "goal,compound",
    [
        ("Lọc hai nhóm lệch tiền lớn nhất rồi xuất chúng ra CSV trong cùng yêu cầu này.", True),
        ("Cho tôi xem các nhóm lệch tiền rồi xuất kết quả đó ra CSV.", True),
        ("Tóm tắt kết quả và tải báo cáo Excel.", True),
        ("Mình muốn lọc ba khoản lệch lớn nhất và tải kết quả lọc mới đó ra CSV.", True),
        ("Xuất CSV rồi liệt kê các nhóm thiếu đối ứng.", True),
        ("Trước tiên hãy liệt kê các nhóm lệch tiền, chưa xuất tệp.", False),
        ("Liệt kê các nhóm thiếu đối ứng; đừng xuất CSV.", False),
        ("Mình muốn lọc nhóm thiếu đối ứng, chưa xuất CSV.", False),
        ("Xuất CSV của bảng đang xem và bộ lọc hiện tại.", False),
        ("Xuất bảng vừa hiển thị ra Excel cho mình nhé.", False),
        ("Chuẩn hóa nguồn để đối soát và trình tôi duyệt.", False),
        ('Xem tệp "Lọc và xuất CSV.csv".', False),
    ],
)
def test_read_and_export_sequence_does_not_execute_only_one_clause(goal, compound):
    from studio.agent_intents import resolve_read_export_sequence

    actual = resolve_read_export_sequence(goal)
    assert bool(actual) is compound
    if actual:
        assert actual.intent == "CLARIFY" and actual.questions
        assert actual.query is None and actual.run_id is None


@pytest.mark.parametrize(
    "goal,read_only",
    [
        ("Bản tự chuẩn bị của tệp này có bao nhiêu hàng?", True),
        ("Lọc các chứng từ thiếu đối ứng.", True),
        ("Cho biết số nhóm thiếu đối ứng trong lần chạy hiện tại.", True),
        ("Chỉ liệt kê các mã đơn khi kho bằng HN01.", True),
        ("Tìm các dòng có mã kho đúng bằng HN01.", True),
        ("Chỉ chuẩn hóa dữ liệu của nguồn đang chọn.", False),
        ("Nêu tổng quan kết quả đã xác minh.", True),
        ("Khoản ở vị trí thứ hai trong bảng đó vì sao chưa ghép được?", True),
        ("Chuẩn hóa nguồn rồi đếm số dòng.", False),
        ("Lấy hai tệp để đối soát.", False),
        ("Lập bản đề xuất quy tắc để tôi kiểm tra và duyệt.", False),
    ],
)
def test_explicit_read_capability_never_authorizes_new_preparation_or_planning(goal, read_only):
    from studio.agent_intents import explicit_read_request

    assert explicit_read_request(goal) is read_only


@pytest.mark.parametrize(
    "goal,unselected",
    [
        ("Bản tự chuẩn bị của tệp này có bao nhiêu hàng?", False),
        ("Bản tự chuẩn bị có bao nhiêu hàng trong tệp này?", False),
        ("Bản tự chuẩn bị của tệp chưa chọn có bao nhiêu hàng?", True),
    ],
)
def test_prepared_count_keeps_source_selector_before_or_after_operation(goal, unselected):
    from studio.agent_intents import resolve_layer_listing

    cat = catalogue()
    cat.context.dataset_id = "dataset"
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    result = resolve_layer_listing(goal, cat)
    if unselected:
        assert result.intent == "CLARIFY" and result.query is None
    else:
        assert result.intent == "QUERY_DATA" and result.query.source_kind == "PREPARED"
        assert result.query.source_id == "table" and result.query.aggregations[0].op == "count"


@pytest.mark.parametrize("action", ["PREPARE_NORMALIZATION", "CONTINUE_REVIEW"])
def test_read_question_cannot_become_a_model_write_action(action):
    from studio.agent_intents import compile_routing

    result = compile_routing(
        json.dumps({"intents": [{"intent": action}]}),
        ["Đếm các hàng trong bản tự chuẩn bị"],
        catalogue(),
    )[0]
    assert result.intent == "CLARIFY" and result.query is None


@pytest.mark.parametrize("local", [False, True])
def test_read_routing_omits_historical_plan_and_has_no_write_capabilities(local):
    from studio.agent_intents import routing_sources

    cat = routing_catalogue()
    cat.verified_run_fields.append("linkage_state")
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "VERIFIED_RUN")

    class Provider:
        usage = {}

        def request_typed(self, prompt, policy, reserve, validator, **kwargs):
            schema = kwargs["response_schema"]
            actions = {
                b["properties"]["intent"]["enum"][0]
                for b in schema["$defs"]["RoutingIntent"]["anyOf"]
            }
            assert not actions & {"PREPARE_NORMALIZATION", "RECONCILE_DATASETS", "CONTINUE_REVIEW"}
            data = json.loads(prompt[1]["content"])
            assert not data.get("confirmed_scope")
            assert {s["source_kind"] for s in data["sources"]} <= {"VERIFIED_RUN", "EXCEPTIONS"}
            return validator(
                json.dumps(
                    {
                        "intents": [
                            {
                                "intent": "QUERY_DATA",
                                "query": {
                                    "source_ref": source["ref"],
                                    "filters": [
                                        {
                                            "field_id": "linkage_state",
                                            "op": "eq",
                                            "value": "UNMATCHED",
                                        }
                                    ],
                                    "aggregations": [{"op": "count"}],
                                    "group_by": [],
                                    "currency_field": None,
                                },
                            }
                        ]
                    }
                )
            )

    provider = Provider()
    provider.local = local
    intent = interpret_requests(
        provider,
        ["Cho biết số nhóm thiếu đối ứng trong lần chạy hiện tại."],
        cat,
        WorkspacePolicy(),
        lambda: True,
    )[0]
    assert intent.intent == "QUERY_DATA" and intent.query.source_id == cat.context.run_id
    assert intent.query.aggregations[0].op == "count"


def test_single_partial_model_query_cannot_drop_the_export_clause():
    from studio.agent_intents import compile_routing, routing_sources

    cat = catalogue()
    cat.context.run_id = "run"
    cat.verified_run_fields = ["group_id", "linkage_state", "comparison_state"]
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "VERIFIED_RUN")
    content = json.dumps(
        {
            "intents": [
                {
                    "intent": "QUERY_DATA",
                    "query": {
                        "source_ref": source["ref"],
                        "filters": [],
                        "aggregations": [],
                        "group_by": [],
                        "currency_field": None,
                    },
                }
            ]
        }
    )
    result = compile_routing(
        content, ["Lọc hai nhóm lệch tiền lớn nhất rồi xuất chúng ra CSV."], cat
    )[0]
    assert result.intent == "CLARIFY" and result.query is None and result.questions

    # The subsequent answer chooses one action. Historical affirmative export
    # must not override the current explicit prohibition on exporting.
    cat.previous_goal = "Lọc nhóm lệch rồi xuất CSV."
    cat.pending_question = "Bạn muốn làm tác vụ nào trước?"
    partial = json.loads(content)
    partial["intents"][0]["query"]["filters"] = [
        {"field_id": "comparison_state", "op": "eq", "value": "AMOUNT_MISMATCH"}
    ]
    result = compile_routing(
        json.dumps(partial), ["Trước tiên hãy liệt kê các nhóm lệch tiền, chưa xuất tệp."], cat
    )[0]
    assert result.intent == "QUERY_DATA" and result.query.filters[0].value == "AMOUNT_MISMATCH"
    from studio.agent_intents import resolve_deferred_export_read

    reply = "Trước tiên hãy liệt kê các nhóm lệch tiền, chưa xuất tệp."
    resolved = resolve_deferred_export_read(reply, cat)
    assert resolved.intent == "QUERY_DATA" and resolved.query.filters[0].value == "AMOUNT_MISMATCH"
    assert (
        resolve_deferred_export_read("Liệt kê nhóm lệch tiền trong tháng 7, chưa xuất tệp", cat)
        is None
    )
    cat.pending_question = None
    assert resolve_deferred_export_read(reply, cat) is None


def test_distinct_actions_for_one_goal_require_sequence_without_executing_a_partial_request():
    from studio.agent_intents import compile_routing

    content = json.dumps(
        {
            "intents": [
                {"intent": "SUMMARIZE_RESULTS", "run_id": "run"},
                {"intent": "EXPORT_RESULT", "run_id": "run", "export_format": "csv"},
            ]
        }
    )
    diagnostics = {}
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        compile_routing(content, ["Tóm tắt kết quả rồi xuất báo cáo CSV"], catalogue(), diagnostics)
    assert diagnostics["routing_error"] == {
        "stage": "multiple_distinct_actions",
        "intent_count": 2,
        "expected_intent_count": 1,
    }
    # A true batch of two goals still has two typed results in order.
    result = compile_routing(content, ["Tóm tắt kết quả", "Xuất báo cáo CSV"], catalogue())
    assert [intent.intent for intent in result] == ["SUMMARIZE_RESULTS", "EXPORT_RESULT"]


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


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("roles", [False, True])
def test_named_pair_wire_cannot_substitute_a_third_canonical(local, missing, roles):
    """Schema inspection only, no provider inference or business approval."""
    from types import SimpleNamespace

    from studio.agent_intents import interpret_requests, routing_sources

    cat = routing_catalogue()
    for i, dataset in enumerate(cat.datasets):
        dataset.name = f"Ledger-{i}.csv"
    third = cat.datasets[0].model_copy(deep=True)
    third.id, third.name = "dataset-third", "Receipts-external.csv"
    third.tables[0].table_id, third.tables[0].canonical_id = "table-third", "canonical-third"
    cat.datasets.append(third)
    for dataset in cat.datasets:
        dataset.tables[0].prepared_artifact_id = "prepared-" + dataset.id
    second_name = "Not-uploaded.xlsx" if missing else cat.datasets[1].name
    goal = f"Lập đề xuất đối soát tệp “{third.name}” với tệp “{second_name}”, chờ tôi duyệt."
    if roles:
        goal = (
            f"Nguồn tham chiếu (role=reference) là tệp “{third.name}”; "
            f"nguồn đối ứng (role=counterpart) là tệp “{second_name}”."
        )

    def inspect(*args, response_schema, **kwargs):
        payload_sources = json.loads(args[0][1]["content"])["sources"]
        for source in payload_sources:
            if local and source["source_kind"] in {"PREPARED", "PREPARED_FINDINGS"}:
                assert "fields" not in source
        variants = response_schema["$defs"]["RoutingIntent"]["anyOf"]
        planning = [
            v for v in variants if v["properties"]["intent"]["enum"] == ["RECONCILE_DATASETS"]
        ]
        if missing:
            assert planning == []
        else:
            assert len(planning) == 1
            allowed = {third.tables[0].canonical_id, cat.datasets[1].tables[0].canonical_id}
            if local:
                allowed = {
                    s["ref"]
                    for s in routing_sources(cat)
                    if s["source_kind"] == "CANONICAL" and s["source_id"] in allowed
                }
            properties = response_schema["$defs"]["ReconciliationSelection"]["properties"]
            for side in ["left", "right"]:
                expected = allowed
                if roles:
                    selected = (
                        third.tables[0].canonical_id
                        if side == "left"
                        else cat.datasets[1].tables[0].canonical_id
                    )
                    expected = {
                        s["ref"] if local else s["source_id"]
                        for s in routing_sources(cat)
                        if s["source_kind"] == "CANONICAL" and s["source_id"] == selected
                    }
                assert (
                    set(properties[side if local else side + "_canonical_id"]["enum"]) == expected
                )
        return []

    interpret_requests(
        SimpleNamespace(local=local, usage={}, request_typed=inspect),
        [goal],
        cat,
        WorkspacePolicy(),
        lambda: True,
    )


@pytest.mark.parametrize("wrong", ["source_order", "role"])
def test_explicit_filename_roles_are_checked_after_model_decoding(wrong):
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    cat.datasets[0].name, cat.datasets[1].name = "Reference.csv", "Counterpart.csv"
    request = PlanningRequest.from_plan(cat.confirmed_plan)
    goal = (
        "Nguồn tham chiếu là tệp “Reference.csv”; nguồn đối ứng là tệp “Counterpart.csv”. "
        "Hai nguồn đầy đủ. Dữ kiện đã xác nhận: " + request.model_dump_json()
    )

    def payload():
        return json.dumps(
            dict(
                intents=[
                    dict(
                        intent="RECONCILE_DATASETS",
                        planning_request=request.model_dump(mode="json"),
                    )
                ]
            )
        )

    assert validate_intents(payload(), [goal], cat)[0].intent == "RECONCILE_DATASETS"
    if wrong == "source_order":
        request.left.canonical_id, request.right.canonical_id = (
            request.right.canonical_id,
            request.left.canonical_id,
        )
    else:
        request.left.role, request.right.role = "counterpart", "reference"
    result = validate_intents(payload(), [goal], cat)[0]
    assert result.intent == "CLARIFY" and result.planning_request is None


@pytest.mark.parametrize(
    "goal,expected",
    [
        (
            "Nguồn đối ứng là tệp “B.csv”; nguồn tham chiếu là tệp “A.csv”.",
            {"left": "a.csv", "right": "b.csv"},
        ),
        (
            "Reference source file A.csv; counterpart source file B.csv",
            {"left": "a.csv", "right": "b.csv"},
        ),
        ("Nguồn trái là file A.csv; nguồn phải là file B.csv", {"left": "a.csv", "right": "b.csv"}),
        ("Đối soát “B.csv” với “A.csv”", {}),
        ("Không phải nguồn tham chiếu là tệp “A.csv”", {}),
        ("Chưa chọn nguồn tham chiếu là tệp “A.csv”", {}),
        ("Nguồn tham chiếu hoặc nguồn đối ứng là tệp “A.csv”", {}),
        ("Nguồn tham chiếu là tệp “A.csv”; nguồn tham chiếu là tệp “B.csv”", {}),
    ],
)
def test_filename_role_binding_does_not_infer_order_or_negated_roles(goal, expected):
    from studio.agent_intents import explicit_filename_roles

    assert explicit_filename_roles(goal) == expected


@pytest.mark.parametrize("fact", ["timezone", "coverage_start", "snapshot_at", "completeness"])
def test_new_source_cannot_inherit_confirmation_from_another_runs_source(fact):
    """A same-valued fact in a different canonical scope is not user confirmation."""
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    cat.confirmed_plan.left.coverage_start = cat.confirmed_plan.left.coverage_start.replace(
        day=28, month=9
    )
    cat.confirmed_plan.left.snapshot_at = cat.confirmed_plan.left.snapshot_at.replace(day=3)
    cat.confirmed_plan.right.completeness = "INCOMPLETE"
    request = PlanningRequest.from_plan(cat.confirmed_plan)
    cat.datasets[0].tables[0].canonical_id = "another-canonical-revision"
    request.left.canonical_id = "another-canonical-revision"
    # All facts except the one under test are explicitly supplied. The omitted
    # fact exactly equals the historical plan, exposing the scope confusion.
    payload = request.model_dump(mode="json", exclude={"intent"})
    if fact == "timezone":
        payload.pop(fact)
    else:
        payload["left"].pop(fact)
    goal = "Đề xuất quy tắc mới cho hai nguồn này, dữ kiện tôi xác nhận: " + json.dumps(payload)
    # The explicit technical value is confirmation; do not need the natural
    # language completeness synonym for fields unrelated to this probe.
    if fact != "completeness":
        goal += " Nguồn trái và phải đầy đủ."
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate_intents(
            json.dumps(
                {
                    "intents": [
                        {
                            "intent": "RECONCILE_DATASETS",
                            "planning_request": request.model_dump(mode="json"),
                        }
                    ]
                }
            ),
            [goal],
            cat,
        )


@pytest.mark.parametrize(
    "variant", ["both", "missing-left", "incomplete-left", "negated", "duplicate", "foreign"]
)
def test_explicit_structured_source_completeness_is_scoped_and_never_inherited(variant):
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    request = PlanningRequest.from_plan(cat.confirmed_plan)
    cat.confirmed_plan = None
    facts = {side: getattr(request, side).model_dump(mode="json") for side in ("left", "right")}
    if variant == "missing-left":
        facts["left"].pop("completeness")
    elif variant == "incomplete-left":
        facts["left"]["completeness"] = "INCOMPLETE"
    elif variant == "foreign":
        facts["left"]["canonical_id"] = "another-canonical"
    left = json.dumps(facts["left"])
    if variant == "duplicate":
        left = left[:-1] + ', "completeness": "CONFIRMED"}'
    prefix = "Không dùng " if variant == "negated" else ""
    goal = "Đề xuất đối soát. " + json.dumps(
        request.model_dump(mode="json", exclude={"left", "right"})
    )
    goal += f". {prefix}Facts nguồn trái: {left}; Facts nguồn phải: {json.dumps(facts['right'])}."
    content = json.dumps(
        {
            "intents": [
                {
                    "intent": "RECONCILE_DATASETS",
                    "planning_request": request.model_dump(mode="json"),
                }
            ]
        }
    )
    if variant == "both":
        actual = validate_intents(content, [goal], cat)[0]
        assert actual.planning_request.left.completeness == "CONFIRMED"
        assert actual.planning_request.right.completeness == "CONFIRMED"
    else:
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            validate_intents(content, [goal], cat)


@pytest.mark.parametrize("selector", ["tệp Missing.xlsx", "“Missing.xlsx”", '"Receipts.xlsx"'])
def test_planner_cannot_substitute_approved_sources_for_explicitly_requested_file(selector):
    """An approved scope never authorizes ignoring a new explicit file selector."""
    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    cat.datasets[0].name = "Ledger.csv"
    cat.datasets[1].name = "Other.xlsx"
    if "Receipts" in selector:
        extra = cat.datasets[1].model_copy(deep=True)
        extra.id, extra.name = "another-dataset", "Receipts.xlsx"
        extra.tables[0].table_id, extra.tables[0].canonical_id = (
            "another-table",
            "another-canonical",
        )
        cat.datasets.append(extra)
    request = PlanningRequest.from_plan(cat.confirmed_plan)
    result = validate_intents(
        json.dumps(
            {
                "intents": [
                    {
                        "intent": "RECONCILE_DATASETS",
                        "planning_request": request.model_dump(mode="json"),
                    }
                ]
            }
        ),
        [f"Đối soát “Ledger.csv” với {selector} theo kỳ và các điều kiện đã duyệt."],
        cat,
    )[0]
    assert result.intent == "CLARIFY" and result.questions
    assert result.planning_request is None and result.query is None


def test_explicit_planner_filenames_preserve_approved_pair_across_case_and_unicode():
    import unicodedata

    from studio.contracts.reconciliation import PlanningRequest

    cat = routing_catalogue()
    cat.datasets[0].name, cat.datasets[1].name = "Sổ chứng từ.csv", "Biên nhận.xlsx"
    request = PlanningRequest.from_plan(cat.confirmed_plan)
    left_name = unicodedata.normalize("NFD", cat.datasets[0].name).upper()
    result = validate_intents(
        json.dumps(
            {
                "intents": [
                    {
                        "intent": "RECONCILE_DATASETS",
                        "planning_request": request.model_dump(mode="json"),
                    }
                ]
            }
        ),
        [f"Đối soát “{left_name}” với tệp “Biên nhận.xlsx” theo phạm vi đã duyệt."],
        cat,
    )[0]
    assert result.intent == "RECONCILE_DATASETS"
    assert result.planning_request == request


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


def test_exact_value_request_cannot_be_widened_to_substring_search():
    from studio.agent_intents import compile_routing

    cat = routing_catalogue()
    cat.context.dataset_id = cat.datasets[0].id
    query = dict(
        source_ref="canonical-1",
        select_fields=["order_id"],
        filters=[dict(field_id="shop_id", op="contains", value="HN01")],
        aggregations=[],
        group_by=[],
        currency_field=None,
    )

    def route():
        return compile_routing(
            json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=query)])),
            ["Tìm mã đơn có shop_id đúng bằng HN01."],
            cat,
        )[0]

    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        route()
    query["filters"][0]["op"] = "eq"
    assert route().query.filters[0].value == "HN01"


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


@pytest.mark.parametrize("foreign_field", [False, True])
def test_routing_gemini_mock_sends_bounded_schema_once_and_binds_native_source(foreign_field):
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
        query = schema["$defs"]["RoutingQuery"]["properties"]
        assert query["source_ref"]["enum"] == [s["ref"] for s in routing_sources(cat)]
        assert "case_id" in query["select_fields"]["items"]["enum"]
        assert query["null_policy"]["enum"] == ["PRESERVE"]
        assert query["result_scope"]["enum"] == ["ALL_MATCHING"]
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
                        select_fields=["case_id"] if foreign_field else [],
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
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1
    )

    def ask():
        return interpret_requests(
            provider, ["Đếm dữ liệu nguồn"], cat, policy, lambda: reserved.append(True) or True
        )

    try:
        if foreign_field:
            with pytest.raises(DomainError, match="AI_INVALID_FIELD"):
                ask()
        else:
            result = ask()
            assert result[0].query.source_id == cat.confirmed_plan.left.canonical_id
            assert result[0].query.project_id == cat.context.project_id
    finally:
        provider.close()
    assert len(received) == len(reserved) == 1


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


@pytest.mark.parametrize("negation", ["chưa", "chưa được", "không được", "không được phép"])
@pytest.mark.parametrize("action", ["tự phê duyệt", "bỏ qua tiền tệ", "xóa dữ liệu gốc"])
def test_authority_guards_respect_preverbal_negation_and_later_affirmative_request(
    negation, action
):
    from studio.agent_intents import (
        approval_bypass_requested,
        currency_bypass_requested,
        data_mutation_requested,
    )

    guard = {
        "tự phê duyệt": approval_bypass_requested,
        "bỏ qua tiền tệ": currency_bypass_requested,
        "xóa dữ liệu gốc": data_mutation_requested,
    }[action]
    assert not guard(f"Lập đề xuất để tôi kiểm tra; {negation} {action}.")
    assert guard(f"Lúc đầu {negation} {action}, nhưng sau đó hãy {action}.")


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


@pytest.mark.parametrize(
    "goal,fmt",
    [
        ("Gửi tôi tệp CSV chứa đúng phần bảng vừa hiển thị.", "csv"),
        ("Mình muốn lưu các dòng trên thành một bảng Excel.", "xlsx"),
        ("Xin xuất những nhóm vừa xem sang tệp CSV", "csv"),
        ("Lưu đúng các dòng vừa liệt kê thành tệp CSV.", "csv"),
        ("Xuất bảng đang xem sang Excel cho mình nhé", "xlsx"),
        ("Xuất bảng đang xem sang CSV giúp tôi với", "csv"),
    ],
)
def test_displayed_export_composes_reference_and_format_on_same_run(goal, fmt):
    from studio.agent_intents import resolve_displayed_export
    from studio.contracts.data_query import DataQuery

    cat = routing_catalogue()
    cat.previous_query = DataQuery(
        project_id="project", source_kind="VERIFIED_RUN", source_id="run"
    )
    result = resolve_displayed_export(goal, cat)
    assert (
        result.intent == "EXPORT_RESULT" and result.export_format == fmt and result.run_id == "run"
    )
    assert (
        resolve_displayed_export(f"{goal.rstrip('.')} chỉ lấy phần sai tiền", cat).intent
        == "CLARIFY"
    )
    cat.previous_query.source_id = "other-run"
    assert resolve_displayed_export(goal, cat).intent == "CLARIFY"


def test_model_cannot_replace_displayed_export_with_a_full_run_export():
    cat = routing_catalogue()
    intent = AgentIntent(intent="EXPORT_RESULT", run_id="run", export_format="csv")
    content = json.dumps(dict(intents=[intent.model_dump(mode="json")]))
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate_intents(content, ["Bạn có thể tạo file CSV giữ đúng các dòng trên không?"], cat)
    assert validate_intents(content, ["Tải báo cáo CSV của kết quả đang xem"], cat)[0] == intent


@pytest.mark.parametrize("scope", ["FULL_RUN", "DISPLAYED_QUERY"])
def test_export_storage_uses_existing_query_fields_for_rollback_compatibility(scope):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from studio.agent_workflows import save
    from studio.contracts.agent import ClarificationOption, ReviewRequest, WorkflowState
    from studio.contracts.data_query import DataQuery

    query = DataQuery(
        project_id="project", source_kind="VERIFIED_RUN", source_id="run", offset=2, limit=1
    )
    intent = AgentIntent(intent="EXPORT_RESULT", run_id="run", export_scope=scope)
    state = WorkflowState(
        intent=intent,
        export_query=query if scope == "DISPLAYED_QUERY" else None,
        reviews=[
            ReviewRequest(
                id="review",
                kind="CLARIFICATION",
                question="Xuất bảng nào?",
                reason="Phạm vi",
                resource_id="run",
                fingerprint="a" * 64,
                nonce="b" * 32,
                expires_at=datetime.now(UTC),
                expected_effects=[],
                reply_intent=intent.model_copy(deep=True),
                options=[
                    ClarificationOption(
                        id="option", label="Xuất bảng", intent=intent.model_copy(deep=True)
                    )
                ],
            )
        ],
    )
    row = SimpleNamespace()
    save(row, state)
    assert '"export_scope"' not in json.dumps(row.detail)
    saved_intents = [
        row.detail["intent"],
        row.detail["reviews"][0]["reply_intent"],
        row.detail["reviews"][0]["options"][0]["intent"],
    ]
    for saved in saved_intents:
        assert saved["query"] == (
            query.model_dump(mode="json") if scope == "DISPLAYED_QUERY" else None
        )
    restored = WorkflowState.model_validate(row.detail)
    assert restored.intent.export_scope == scope
    assert restored.reviews[0].reply_intent.export_scope == scope
    assert restored.reviews[0].options[0].intent.export_scope == scope


@pytest.mark.parametrize("scope", ["DISPLAYED_QUERY", "FULL_RUN"])
def test_routing_export_scope_binds_only_the_selected_verified_query(scope):
    from studio.agent_intents import compile_routing, export_query_for_intent
    from studio.contracts.data_query import DataQuery, QueryFilter, QuerySort

    cat = routing_catalogue()
    cat.previous_query = DataQuery(
        project_id="project",
        source_kind="VERIFIED_RUN",
        source_id="run",
        filters=[QueryFilter(field_id="linkage_status", op="eq", value="UNMATCHED")],
        sort=[QuerySort(field_id="group_id", descending=True)],
        offset=1,
        limit=2,
    )
    body = json.dumps(
        dict(
            intents=[
                dict(
                    intent="EXPORT_RESULT",
                    run_id=None,
                    export_format="csv",
                    export_scope=scope,
                )
            ]
        )
    )
    goal = (
        "Bạn tạo CSV giữ nguyên những dòng trên giúp tôi được không?"
        if scope == "DISPLAYED_QUERY"
        else "Xuất báo cáo toàn bộ run"
    )
    result = compile_routing(body, [goal], cat)[0]
    assert result.export_scope == scope
    query = export_query_for_intent(result, cat)
    if scope == "DISPLAYED_QUERY":
        assert result.run_id == "run" and query == cat.previous_query
        assert query is not cat.previous_query
        query.offset = 0
        assert cat.previous_query.offset == 1
    else:
        assert query is None


@pytest.mark.parametrize(
    "changed", ["missing", "project", "run", "unverified", "not_accessible", "explicit_other_run"]
)
def test_displayed_export_rejects_missing_stale_or_foreign_query(changed):
    from studio.agent_intents import compile_routing
    from studio.contracts.data_query import DataQuery

    cat = routing_catalogue()
    cat.previous_query = DataQuery(
        project_id="project", source_kind="VERIFIED_RUN", source_id="run"
    )
    if changed == "missing":
        cat.previous_query = None
    elif changed == "project":
        cat.previous_query.project_id = "other-project"
    elif changed == "run":
        cat.previous_query.source_id = "other-run"
    elif changed == "unverified":
        cat.previous_query.source_kind = "CANONICAL"
    elif changed == "not_accessible":
        cat.run_ids = []
    expected = "AI_INVALID_SOURCE" if changed == "not_accessible" else "QUERY_SEMANTICS_REQUIRED"
    with pytest.raises(DomainError, match=expected):
        compile_routing(
            json.dumps(
                dict(
                    intents=[
                        dict(
                            intent="EXPORT_RESULT",
                            run_id="other-run" if changed == "explicit_other_run" else None,
                            export_format="csv",
                            export_scope="DISPLAYED_QUERY",
                        )
                    ]
                )
            ),
            ["Xuất nguyên bảng CSV"],
            cat,
        )


def test_typed_full_run_export_cannot_ignore_explicit_displayed_reference():
    from studio.agent_intents import compile_routing
    from studio.contracts.data_query import DataQuery

    cat = routing_catalogue()
    cat.previous_query = DataQuery(
        project_id="project", source_kind="VERIFIED_RUN", source_id="run"
    )
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        compile_routing(
            json.dumps(
                dict(
                    intents=[
                        dict(
                            intent="EXPORT_RESULT",
                            run_id="run",
                            export_format="csv",
                            export_scope="FULL_RUN",
                        )
                    ]
                )
            ),
            ["Tạo file giữ đúng các dòng trên"],
            cat,
        )


@pytest.mark.parametrize(
    "goal",
    [
        "Tìm các khoản thiếu đối ứng riêng tháng 9 năm 2026",
        "Đếm các nhóm chênh lệch của tháng 12",
        "Trong các giao dịch sai tiền, chỉ lấy trường hợp đã xử lý xong",
        "Liệt kê nhóm lệch tiền đang giải quyết",
        "Trong các nhóm lệch tiền, chỉ lấy trường hợp đã được xử lý xong",
        "Hiển thị các khoản đã xử lý nhưng vẫn thiếu đối ứng",
    ],
)
def test_group_read_needing_different_period_or_exception_grain_clarifies(goal):
    from studio.agent_intents import resolve_native_read

    result = resolve_native_read(goal, routing_catalogue())
    assert result.intent == "CLARIFY" and result.query is None and result.questions


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


@pytest.mark.parametrize(
    "response_kind",
    ["clarify", "facts", "foreign-slot", "foreign-ref", "same-source", "legacy-names"],
)
def test_local_reconciliation_router_keeps_explicit_source_fact_slots(response_kind):
    from studio.agent_intents import routing_sources
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
    refs = [s["ref"] for s in routing_sources(cat) if s["source_kind"] == "CANONICAL"]
    wire = dict(
        left=refs[0],
        right=refs[1],
        run=None,
        start=selection["period_start"],
        end=selection["period_end"],
        tz=selection["timezone"],
        since=selection["effective_from"],
        until=None,
    )
    for key, side in (("a", "left"), ("b", "right")):
        source = getattr(plan, side)
        wire[key] = dict(
            role=source.role,
            date=source.date_field,
            basis=source.time_basis,
            ccy=source.currency_field,
            where=source.filters,
            **{"from": str(source.coverage_start), "to": str(source.coverage_end)},
            complete=source.completeness,
            asof=source.snapshot_at.isoformat(),
            due=None,
        )

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3.8:27b", "size": 1, "digest": "a" * 64}]}
            )
        payload = json.loads(request.content)
        definitions = payload["format"]["$defs"]
        assert {"a", "b"} <= set(definitions["ReconciliationSelection"]["required"])
        assert set(definitions["ReconciliationSelection"]["required"]) == set(
            definitions["ReconciliationSelection"]["properties"]
        )
        source_schema = definitions["PlanningSource"]
        assert "canonical_id" not in source_schema["properties"]
        assert set(source_schema["properties"]) - {"due"} == set(source_schema["required"])
        instructions = payload["messages"][0]["content"]
        assert "role=reference" in instructions and "role=counterpart" in instructions
        assert "belongs in filters" in instructions
        assert definitions["ReconciliationSelection"]["properties"]["left"]["enum"] == refs
        intent = {"intent": "RECONCILE_DATASETS", "reconciliation": wire}
        if response_kind == "clarify":
            intent = {"intent": "CLARIFY", "questions": ["Chọn hai nguồn?"]}
        elif response_kind == "foreign-slot":
            wire["a"]["canonical_id"] = "foreign"
        elif response_kind == "foreign-ref":
            wire["left"] = plan.left.canonical_id  # A UUID/ID is not a local capability ref.
        elif response_kind == "same-source":
            wire["right"] = wire["left"]
        elif response_kind == "legacy-names":
            intent["reconciliation"] = selection
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
        "QWEN_27B",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        if response_kind in {"foreign-slot", "foreign-ref", "same-source", "legacy-names"}:
            with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
                interpret_requests(provider, [goal], cat, WorkspacePolicy(), lambda: True)
        else:
            result = interpret_requests(provider, [goal], cat, WorkspacePolicy(), lambda: True)
            assert result[0].intent == (
                "CLARIFY" if response_kind == "clarify" else "RECONCILE_DATASETS"
            )
            if response_kind == "facts":
                from studio.contracts.reconciliation import PlanningRequest

                assert result[0].planning_request.allow_partial is None
                assert result[0].planning_request.model_dump(
                    exclude={"intent", "allow_partial"}
                ) == PlanningRequest.from_plan(plan).model_dump(exclude={"intent", "allow_partial"})
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
        "Xem dữ liệu tự chuẩn bị của nguồn khác",
        "Không xem dữ liệu tự chuẩn bị",
    ):
        assert resolve_prepared_listing(goal, cat) is None
    assert resolve_prepared_listing("Tổng tiền của bản tự chuẩn bị", cat).intent == "CLARIFY"
    foreign = resolve_prepared_listing("Xem dữ liệu tự chuẩn bị", cat)
    foreign.query.source_id = "foreign-table"
    with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
        validate_intents(
            IntentBatch(intents=[foreign]).model_dump_json(), ["Xem dữ liệu tự chuẩn bị"], cat
        )
    cat.datasets.append(cat.datasets[0].model_copy(update={"id": "another-dataset"}, deep=True))
    assert resolve_prepared_listing("Xem dữ liệu tự chuẩn bị", cat).intent == "CLARIFY"


@pytest.mark.parametrize("kind", ["PREPARED", "PREPARED_FINDINGS"])
def test_typed_prepared_paraphrases_bind_only_selected_source_and_safe_operations(kind):
    from studio.agent_intents import compile_routing, routing_sources

    cat = catalogue()
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    cat.context.dataset_id = cat.datasets[0].id
    sources = routing_sources(cat)
    selected = next(source for source in sources if source["source_kind"] == kind)
    assert selected["source_id"] == "table" and selected["allowed_operations"] == [
        "preview",
        "count",
    ]
    query = dict(
        source_ref=selected["ref"],
        select_fields=[],
        filters=[],
        aggregations=[],
        group_by=[],
        sort=[],
        limit=20,
        offset=0,
        currency_field=None,
        metric_id=None,
    )
    body = json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=query)]))
    goal = (
        "Cho mình kiểm tra những hàng có ngày bị ghi sai trong nguồn đang chọn"
        if kind == "PREPARED_FINDINGS"
        else "Cho mình kiểm tra những hàng trong nguồn đang chọn"
    )
    result = compile_routing(body, [goal], cat)[0]
    assert result.query.source_kind == kind and result.query.source_id == "table"
    if kind == "PREPARED_FINDINGS":
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            compile_routing(body, ["Cho mình xem toàn bộ bảng"], cat)
    for goal in ("Tính tổng tiền của nguồn này", "Không xem nguồn này", "Xem nguồn khác"):
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            compile_routing(body, [goal], cat)
    query["aggregations"] = [dict(op="sum_decimal", field_id="amount")]
    with pytest.raises(DomainError):
        compile_routing(
            json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=query)])),
            ["Cho mình kiểm tra những hàng trong nguồn đang chọn"],
            cat,
        )
    other = cat.datasets[0].model_copy(update={"id": "another", "name": "Other source"}, deep=True)
    other.tables[0].table_id = "other-table"
    cat.datasets.append(other)
    cat.context.dataset_id = None
    query["aggregations"] = []
    with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
        compile_routing(
            json.dumps(dict(intents=[dict(intent="QUERY_DATA", query=query)])),
            ["Cho mình kiểm tra những hàng"],
            cat,
        )


@pytest.mark.parametrize(
    "goal,count,missing,accepted",
    [
        ("Cho xem dữ liệu gốc", True, False, False),
        ("Đếm số dòng dữ liệu gốc", True, False, True),
        ("Cho xem dữ liệu gốc", False, True, False),
        ("Xem các dòng thiếu mã", False, True, True),
    ],
)
def test_model_cannot_add_a_count_or_null_filter_to_a_plain_read(goal, count, missing, accepted):
    from studio.contracts.agent import IntentBatch, SourceColumn
    from studio.contracts.data_query import DataQuery, QueryAggregation, QueryFilter

    cat = catalogue()
    cat.datasets[0].tables[0].columns = [
        SourceColumn(
            id="code", name="Code", type_candidates=["string"], null_count=1, distinct_count=2
        )
    ]
    intent = AgentIntent(
        intent="QUERY_DATA",
        query=DataQuery(
            project_id="p",
            source_kind="RAW_PREVIEW",
            source_id="table",
            aggregations=[QueryAggregation(op="count")] if count else [],
            filters=[QueryFilter(field_id="code", op="is_null")] if missing else [],
        ),
    )
    body = IntentBatch(intents=[intent]).model_dump_json()
    if accepted:
        assert validate_intents(body, [goal], cat)[0] == intent
    else:
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            validate_intents(body, [goal], cat)


def test_provider_query_grammar_binds_field_enums_to_each_source():
    from studio.agent_intents import routing_sources
    from studio.contracts.agent import SourceColumn

    cat = catalogue()
    cat.datasets[0].tables[0].columns = [
        SourceColumn(
            id="code", name="Code", type_candidates=["string"], null_count=0, distinct_count=3
        )
    ]
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    captured = {}
    other = cat.datasets[0].model_copy(update={"id": "other-dataset"}, deep=True)
    other.tables[0].table_id = "other-table"
    other.tables[0].prepared_artifact_id = None
    other.tables[0].canonical_id = None
    other.tables[0].schema_definition = None
    cat.datasets.append(other)

    class Capture:
        local = True
        usage = {}

        def request_typed(self, *args, **kwargs):
            captured.update(kwargs["response_schema"])
            return []

    interpret_requests(Capture(), ["Đọc dữ liệu tổng hợp"], cat, WorkspacePolicy(), lambda: True)
    sources = routing_sources(cat)
    variants = captured["$defs"]["RoutingQuery"]["anyOf"]
    raw_refs = [source["ref"] for source in sources if source["source_kind"] == "RAW_PREVIEW"]
    assert len(raw_refs) == 2
    assert any(query["properties"]["source_ref"]["enum"] == raw_refs for query in variants)
    for source in sources:
        query = next(v for v in variants if source["ref"] in v["properties"]["source_ref"]["enum"])
        props = query["properties"]
        assert source["ref"] in props["source_ref"]["enum"]
        if source["source_kind"] in {"PREPARED", "PREPARED_FINDINGS"}:
            assert props["filters"]["maxItems"] == props["select_fields"]["maxItems"] == 0
            assert props["aggregations"]["maxItems"] == 0
        else:
            allowed = sorted(field["id"] for field in source["fields"])

            def enum_values(node):
                return captured["$defs"][node["$ref"].rsplit("/", 1)[1]]["enum"]

            assert enum_values(props["select_fields"]["items"]) == allowed == ["code"]
            assert enum_values(props["filters"]["items"]["properties"]["field_id"]) == allowed
            assert enum_values(props["sort"]["items"]["properties"]["field_id"]) == allowed
            assert (
                enum_values(props["aggregations"]["items"]["properties"]["field_id"]["anyOf"][0])
                == allowed
            )
    interpret_requests(
        Capture(), ["Số hàng sau chuẩn bị là bao nhiêu?"], cat, WorkspacePolicy(), lambda: True
    )
    for source in sources:
        query = next(
            v
            for v in captured["$defs"]["RoutingQuery"]["anyOf"]
            if source["ref"] in v["properties"]["source_ref"]["enum"]
        )
        if source["source_kind"] in {"PREPARED", "PREPARED_FINDINGS"}:
            assert query["properties"]["aggregations"]["maxItems"] == 1


@pytest.mark.parametrize(
    "goal",
    [
        "Hãy kiểm tra giúp mình: trong tệp này, những hàng nào chứa ngày bị ghi sai?",
        "Cho tôi các bản ghi có lỗi ở định dạng ngày tháng",
        "List rows with incorrect dates in this source",
        "Ngày không tồn tại nằm ở bản ghi nào?",
        "Đếm các dòng có ngày không hợp lệ",
    ],
)
def test_date_quality_predicate_cannot_be_replaced_by_an_unfiltered_raw_preview(goal):
    from studio.contracts.agent import IntentBatch
    from studio.contracts.data_query import DataQuery

    cat = catalogue()
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    intent = AgentIntent(
        intent="QUERY_DATA",
        query=DataQuery(project_id="p", source_kind="RAW_PREVIEW", source_id="table"),
    )
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        validate_intents(IntentBatch(intents=[intent]).model_dump_json(), [goal], cat)


def test_date_quality_guard_excludes_quoted_filenames_and_negated_condition():
    from studio.agent_intents import invalid_date_condition_requested

    assert not invalid_date_condition_requested("Mở dữ liệu gốc của tệp “Lỗi ngày tháng.csv”")
    assert not invalid_date_condition_requested("Không lọc ngày sai, xem toàn bộ bảng")


@pytest.mark.parametrize(
    "goals,expected",
    [
        (["Tệp gốc đang mở có bao nhiêu bản ghi?"], {"RAW_PREVIEW"}),
        (["Nhìn phần nguyên bản nhé"], {"RAW_PREVIEW"}),
        (["Xem dữ liệu tự chuẩn bị"], {"PREPARED"}),
        (["Đếm các dòng lỗi ngày trong bảng gốc"], {"PREPARED_FINDINGS"}),
        (["Không dùng bản gốc, xem bản đã chuẩn hóa"], set()),
        (["Đọc bản gốc rồi xem bản đã chuẩn hóa"], set()),
        (["Tệp gốc có bao nhiêu hàng?", "Khám phá các cột"], set()),
    ],
)
def test_explicit_layers_bound_capabilities_without_choosing_sources(goals, expected):
    from studio.agent_intents import explicit_read_layers

    assert explicit_read_layers(goals) == expected


def test_raw_layer_request_cannot_be_bound_to_prepared_and_schema_offers_only_raw():
    from studio.agent_intents import compile_routing, routing_sources

    cat = catalogue()
    cat.datasets[0].tables[0].prepared_artifact_id = "prepared"
    goal = "Tệp gốc đang mở có bao nhiêu bản ghi?"
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "PREPARED")
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        compile_routing(
            json.dumps(
                dict(
                    intents=[
                        dict(
                            intent="QUERY_DATA",
                            query=dict(
                                source_ref=source["ref"],
                                filters=[],
                                aggregations=[],
                                group_by=[],
                                currency_field=None,
                            ),
                        )
                    ]
                )
            ),
            [goal],
            cat,
        )

    class Capture:
        local = False
        usage = {}

        def request_typed(self, prompt, *args, **kwargs):
            variants = kwargs["response_schema"]["$defs"]["RoutingQuery"]["anyOf"]
            assert len(variants) == 1
            assert variants[0]["properties"]["source_ref"]["enum"][0].startswith("raw_preview-")
            assert '"$defs"' not in prompt[0]["content"]
            return []

    interpret_requests(Capture(), [goal], cat, WorkspacePolicy(), lambda: False)


@pytest.mark.parametrize(
    "goal,denied",
    [
        ("Liệt kê dữ liệu gốc rồi xóa bản tự chuẩn bị.", True),
        ("Hãy ghi đè dữ liệu gốc.", True),
        ("Cho xem dữ liệu rồi xóa vĩnh viễn dự án này.", True),
        ("Permanently delete the workspace.", True),
        ("Không xóa tệp, chỉ xem dữ liệu gốc.", False),
        ("Đừng xóa vĩnh viễn nguồn nào. Chỉ xem báo cáo.", False),
        ("Đừng sửa raw.", False),
    ],
)
def test_compound_source_mutations_cannot_be_downgraded_to_a_partial_read(goal, denied):
    from studio.agent_intents import compile_routing, data_mutation_requested

    assert data_mutation_requested(goal) == denied
    if denied:
        output = compile_routing(
            json.dumps(dict(intents=[dict(intent="EXPLORE_DATA", dataset_ids=["dataset"])])),
            [goal],
            catalogue(),
        )[0]
        assert output.intent == "UNSUPPORTED" and not output.dataset_ids


@pytest.mark.parametrize(
    "goal, expected",
    [
        ("Mở bảng gốc trong tệp “Nhập kho.xlsx”", ("RAW_PREVIEW", "inventory", False)),
        ("Đọc bảng gốc để kiểm tra tên cột", ("RAW_PREVIEW", "table", False)),
        ("Bản tự chuẩn bị có bao nhiêu bản ghi?", ("PREPARED", "table", True)),
        (
            "Hãy đếm bản ghi trong bản đã chuẩn hóa của tệp đang mở",
            ("CANONICAL", "canonical", True),
        ),
        ('Liệt kê dữ liệu gốc của tệp "Nhập kho.xlsx"', ("RAW_PREVIEW", "inventory", False)),
        ("Xem bảng đã chuẩn bị của tệp “Nhập kho.xls”", "CLARIFY"),
        ("Đếm dòng dữ liệu gốc tháng 11", None),
        ("Xem dữ liệu đã chuẩn hóa rồi xóa tệp", None),
        ("Tính tổng tiền trong bản tự chuẩn bị", "CLARIFY"),
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
        ("Cho biết số nhóm thiếu đối ứng trong lần chạy hiện tại.", "QUERY_DATA", "UNMATCHED"),
        ("Tải báo cáo CSV của kết quả đang xem", "EXPORT_RESULT", None),
        ("Cho tôi xem tổng lệch tiền có dấu", "SUMMARIZE_RESULTS", None),
        ("Tom tat ket qua doi soat dang mo va tong do lech tuyet doi.", "SUMMARIZE_RESULTS", None),
        ("Tong quan ket qua nay va cac chi so chenh lech giup toi.", "SUMMARIZE_RESULTS", None),
        ("Tổng quan kết quả này riêng tháng 10", None, None),
        ("Xuất báo cáo Excel chỉ các giao dịch lệch", None, None),
        ("Đếm nhóm thiếu đối ứng tháng trước", None, None),
        ("Hiển thị những nhóm UNMATCHED ở run tháng trước", None, None),
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


@pytest.mark.parametrize(
    "status,field",
    [
        ("UNMATCHED", "linkage_state"),
        ("AMOUNT_MISMATCH", "comparison_state"),
        ("EQUAL", "comparison_state"),
    ],
)
def test_native_run_read_recognizes_explicit_verified_statuses(status, field):
    from studio.agent_intents import resolve_run_read

    cat = catalogue()
    cat.context.run_id = "run"
    cat.verified_run_fields = ["linkage_state", "comparison_state"]
    goal = f"Hiển thị những nhóm {status} ở run đang mở."
    result = resolve_run_read(goal, cat)
    assert result.intent == "QUERY_DATA" and result.query.source_id == "run"
    assert [(f.field_id, f.op, f.value) for f in result.query.filters] == [(field, "eq", status)]
    assert not result.query.aggregations
    cat.context.run_id = "foreign"
    assert resolve_run_read(goal, cat).intent == "CLARIFY"


@pytest.mark.parametrize(
    "goal,present_side,zero_count_side,expected_status",
    [
        (
            "Có giao dịch nào chỉ xuất hiện ở kế toán không, và đang ở trạng thái nào?",
            "left",
            "right",
            ("in", ["UNMATCHED", "PENDING"]),
        ),
        (
            "Liệt kê giao dịch chỉ xuất hiện ở hóa đơn và đã xác nhận thiếu đối ứng.",
            "right",
            "left",
            ("eq", "UNMATCHED"),
        ),
        (
            "Liệt kê giao dịch chỉ thấy trong hóa đơn.",
            "right",
            "right",
            ("eq", "UNMATCHED"),
        ),
    ],
)
def test_one_sided_observation_keeps_pending_on_the_bound_run(
    goal, present_side, zero_count_side, expected_status
):
    from studio.agent_intents import compile_routing, routing_sources

    cat = routing_catalogue()
    cat.verified_run_fields = ["linkage_state", "left_member_count", "right_member_count"]
    source = next(s for s in routing_sources(cat) if s["source_kind"] == "VERIFIED_RUN")
    membership = [
        {"field_id": f"{present_side}_member_count", "op": "gt", "value": "0"},
        {"field_id": f"{zero_count_side}_member_count", "op": "eq", "value": "0"},
    ]
    body = {
        "intents": [
            {
                "intent": "QUERY_DATA",
                "query": {
                    "source_ref": source["ref"],
                    "filters": [{"field_id": "linkage_state", "op": "eq", "value": "UNMATCHED"}]
                    + membership,
                    "aggregations": [],
                    "group_by": [],
                    "currency_field": None,
                },
            }
        ]
    }
    intent = compile_routing(json.dumps(body), [goal], cat)[0]
    assert intent.query.source_id == cat.context.run_id
    status, *members = intent.query.filters
    assert (status.op, status.value) == expected_status
    assert [member.model_dump() for member in members] == membership


def test_native_unequal_amount_read_respects_approved_tolerance_and_rounding():
    from decimal import Decimal

    from studio.agent_intents import resolve_run_read

    cat = routing_catalogue()
    goal = "Lọc danh sách những cặp đã liên kết mà khoản tiền hai bên không bằng nhau."
    cat.verified_run_fields = ["linkage_state", "comparison_state"]
    metric = cat.confirmed_plan.comparison_metrics[0]
    metric.absolute_tolerance = Decimal("0")
    metric.relative_tolerance = None
    metric.rounding_scale = None
    result = resolve_run_read(goal, cat)
    assert result.query.source_id == cat.context.run_id
    assert result.query.filters[0].value == "AMOUNT_MISMATCH"
    assert result.query.aggregations == []
    metric.rounding_scale = 0
    assert resolve_run_read(goal, cat) is None
    metric.rounding_scale = None
    metric.absolute_tolerance = Decimal("0.01")
    assert resolve_run_read(goal, cat) is None


@pytest.mark.parametrize("noun", ["dòng", "hàng", "bản ghi"])
def test_counting_normalized_rows_cannot_read_a_different_layer(noun):
    from studio.agent_intents import explicit_read_layers, resolve_layer_listing

    cat = catalogue()
    goal = f"Đếm số {noun} đã chuẩn hóa của nguồn đang mở."
    assert explicit_read_layers([goal]) == {"CANONICAL"}
    intent = resolve_layer_listing(goal, cat)
    assert intent is not None and intent.query is not None
    assert intent.query.source_kind == "CANONICAL"
    assert intent.query.source_id == "canonical"
    assert [aggregation.op for aggregation in intent.query.aggregations] == ["count"]


def test_unquoted_named_read_never_substitutes_another_source():
    from studio.agent_intents import read_query_sources, resolve_native_read, routing_sources

    cat = catalogue()
    cat.datasets[0].name = "Sổ kho tháng 11.xlsx"
    goal = "Cho tôi xem dữ liệu gốc của tệp Sổ kho tháng 10.xlsx."
    assert read_query_sources(goal, cat, routing_sources(cat)) == []
    intent = resolve_native_read(goal, cat)
    assert intent is not None and intent.intent == "CLARIFY" and intent.query is None


def test_current_run_preface_preserves_read_only_intent():
    from studio.agent_intents import explicit_read_request, resolve_native_read

    cat = catalogue()
    cat.context.run_id = "run"
    cat.verified_run_fields = ["comparison_state", "absolute_variance"]
    goal = "Trong lần chạy đang xem hãy liệt kê 2 nhóm sai tiền lớn nhất."
    assert explicit_read_request(goal)
    intent = resolve_native_read(goal, cat)
    assert intent is not None and intent.query is not None
    assert intent.query.source_id == "run" and intent.query.limit == 2


@pytest.mark.parametrize(
    "fixture_file,total",
    [
        ("agent-read-holdout.json", 32),
        ("agent-vietnamese-reads.json", 20),
        ("agent-product-quality-holdout.json", 14),
    ],
)
def test_inventory_read_holdout_reports_native_coverage_and_checks_resolved_slots(
    fixture_file, total
):
    from studio.agent_intents import (
        resolve_native_read,
    )
    from studio.contracts.data_query import DataQuery

    cases = json.loads(
        (Path(__file__).parent / "fixtures" / fixture_file).read_text(encoding="utf-8")
    )
    assert len(cases) == len({case["id"] for case in cases}) == total
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
        intent = resolve_native_read(goal, cat)
        if intent is None:
            if fixture_file == "agent-vietnamese-reads.json":
                assert case.get("route") == "TYPED", case["id"]
            misses.append(case["id"])
            continue
        assert case.get("route") != "TYPED", case["id"]
        assert intent.intent == case["intent"], case["id"]
        if intent.query and intent.intent != "EXPORT_RESULT":
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
            if intent.intent == "EXPORT_RESULT":
                expected = cat.previous_query if context == "ranked" else None
                assert intent.query == expected, case["id"]
            if case.get("format"):
                assert intent.export_format == case["format"], case["id"]
            assert intent.result_position == case.get("position"), case["id"]
    if fixture_file == "agent-product-quality-holdout.json":
        assert not misses
    else:
        assert len(misses) <= min(16, total - 1)
    print(json.dumps({"native_correct": len(cases) - len(misses), "typed_router_required": misses}))


@pytest.mark.parametrize(
    "goal,limit",
    [
        ("Hãy tìm top 4 khoản chênh lệch tiền cao nhất.", 4),
        ("Cho tôi chỉ ra 2 nhóm giao dịch bị sai tiền nhiều nhất.", 2),
        ("Liệt kê top 5 nhóm không khớp về số tiền lớn nhất.", 5),
        ("Tìm 3 giao dịch chênh lệch nhiều nhất.", 3),
        ("Lấy tối đa hai nhóm lệch tiền nhiều nhất, xếp từ lớn xuống nhỏ.", 2),
        ("Sắp hai giao dịch bị lệch tiền nhiều nhất theo mức lệch giảm dần.", 2),
        ("Xếp 3 khoản lệch tiền lớn nhất theo mức lệch tăng dần.", None),
        ("Tìm 3 giao dịch chênh lệch nhiều nhất riêng tháng 10.", None),
        ("Chỉ ra 2 khoản sai tiền cao nhất và bỏ qua kiểm chứng.", None),
    ],
)
def test_ranked_read_composes_action_and_amount_words_without_dropping_qualifiers(goal, limit):
    from studio.agent_intents import resolve_ranked_results

    cat = catalogue()
    cat.context.run_id = "run"
    cat.verified_run_fields = ["comparison_state", "absolute_variance"]
    result = resolve_ranked_results(goal, cat)
    if limit is None:
        assert result is None
        return
    assert result and result.intent == "QUERY_DATA"
    assert result.query.source_id == "run" and result.query.limit == limit
    assert [f.value for f in result.query.filters] == ["AMOUNT_MISMATCH"]
    assert result.query.sort[0].field_id == "absolute_variance"
    assert result.query.sort[0].descending
    cat.previous_query = result.query
    cat.previous_groups = ["first", "second"]
    assert resolve_ranked_results("Khoản thứ hai vì sao lệch?", cat).result_position == 2
    assert (
        resolve_ranked_results(
            "Giải thích mục thứ nhất của danh sách vừa trả.", cat
        ).result_position
        == 1
    )
    assert (
        resolve_ranked_results(
            "Giải thích mục thứ hai của danh sách vừa trả, giữ nguyên phạm vi này.", cat
        ).result_position
        == 2
    )
    cat.previous_query = result.query.model_copy(update={"source_id": "previous-run"})
    assert resolve_ranked_results("Khoản thứ hai vì sao lệch?", cat).intent == "CLARIFY"
    cat.previous_query = result.query.model_copy(update={"project_id": "another-project"})
    assert resolve_ranked_results("Khoản thứ hai vì sao lệch?", cat).intent == "CLARIFY"


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


def test_legacy_native_export_restores_the_pinned_page_instead_of_whole_run():
    from studio.contracts.agent import WorkflowState
    from studio.contracts.data_query import DataQuery

    query = DataQuery(project_id="project", source_kind="VERIFIED_RUN", source_id="run", limit=1)
    state = WorkflowState.model_validate(
        dict(
            intent=dict(intent="EXPORT_RESULT", run_id="run"),
            export_query=query.model_dump(mode="json"),
        )
    )
    assert state.intent.export_scope == "DISPLAYED_QUERY" and state.intent.query == query


@pytest.mark.parametrize("mismatched", [False, True])
def test_export_storage_rejects_an_unpinned_or_different_query(mismatched):
    from types import SimpleNamespace

    from studio.agent_workflows import save
    from studio.contracts.agent import WorkflowState
    from studio.contracts.data_query import DataQuery

    query = DataQuery(project_id="project", source_kind="VERIFIED_RUN", source_id="run", limit=1)
    state = WorkflowState(
        intent=AgentIntent(
            intent="EXPORT_RESULT", run_id="run", export_scope="DISPLAYED_QUERY", query=query
        )
    )
    if mismatched:
        state.export_query = query.model_copy(update={"offset": 1})
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        save(SimpleNamespace(), state)


@pytest.mark.parametrize(
    "goal, expected",
    [
        ("Hãy kiểm tra và chuẩn hóa ba nguồn. Sau đó đối soát hai cặp và xuất Excel.", True),
        ("Chuẩn hóa ba bảng rồi đối soát từng cặp, sau đó tải báo cáo XLSX.", True),
        (
            "Hãy tự nhận diện các cột, chuẩn bị dữ liệu và tìm những điểm bất thường. "
            "Khi xong, giúp mình đối soát doanh thu với kế toán, rồi kế toán với hóa đơn. "
            "Cuối cùng tổng hợp các chênh lệch quan trọng và xuất Excel để mình kiểm tra.",
            True,
        ),
        ("Chuẩn bị các nguồn. Giúp mình đối soát. Cuối cùng xuất Excel.", True),
        (
            "Hãy kiểm tra hai nguồn tôi đã tải, đề xuất ánh xạ, chuẩn hóa, "
            "đối soát theo mã giao dịch, tìm những khoản lệch và xuất Excel.",
            True,
        ),
        ("Xuất Excel kết quả đối soát đã chuẩn hóa.", False),
        ("Không chuẩn hóa ba bảng. Đối soát hai cặp và xuất Excel.", False),
        ("Đừng chuẩn bị dữ liệu. Giúp mình đối soát và xuất Excel.", False),
        ("Chuẩn bị dữ liệu đã tải. Không đối soát. Cuối cùng xuất Excel.", False),
    ],
)
def test_compound_routing_requires_each_operation_to_be_requested(goal, expected):
    from studio.agent_intents import requests_reconciliation_sequence

    assert requests_reconciliation_sequence(goal) is expected


def test_compound_routing_accepts_one_pair_and_enforces_scoped_sources():
    from types import SimpleNamespace

    from studio.agent_intents import interpret_reconciliation_sequence

    catalogue = routing_catalogue()
    pair = {"left_dataset_id": "dataset-0", "right_dataset_id": "dataset-1"}
    goal = "Chuẩn hóa hai nguồn, đối soát và xuất Excel."

    def request(_prompt, _policy, _reserve, validate, *, response_schema, max_attempts):
        grammar = response_schema["$defs"]["ReconciliationSequence"]["properties"]["pairs"]
        assert grammar["minItems"] == grammar["maxItems"] == max_attempts == 1
        return validate(json.dumps({"sequence": {"pairs": [pair]}, "question": None}))

    provider = SimpleNamespace(request_typed=request)
    policy = WorkspacePolicy()
    result = interpret_reconciliation_sequence(provider, goal, [], catalogue, policy, lambda: True)
    assert result.sequence.pairs[0].model_dump() == pair
    pair["right_dataset_id"] = "different-project"
    with pytest.raises(DomainError, match="AI_INVALID_SOURCE"):
        interpret_reconciliation_sequence(provider, goal, [], catalogue, policy, lambda: True)
