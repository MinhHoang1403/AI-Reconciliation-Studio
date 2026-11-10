import json
from uuid import uuid4

import httpx
import pytest
from studio.ai_gateway import (
    GeminiProvider,
    OllamaProvider,
    QwenProvider,
    build_evidence_context,
    route_ai_task,
    validate_ai_output,
)
from studio.contracts import MappingStatus, SchemaProposal, WorkspacePolicy
from studio.document_parser import parse_document
from studio.errors import DomainError


@pytest.mark.parametrize("response_kind", ["valid", "timeout", "incomplete", "remote_tag"])
def test_local_provider_uses_only_installed_model_and_typed_content(config, response_kind):
    config.local_demo_access = True
    config.ollama_url = "http://host.docker.internal:11434"
    requests = []
    reservations = []
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}

    def transport(request):
        requests.append(request)
        assert request.url.host == "host.docker.internal"
        if request.url.path == "/api/tags":
            model = {"name": "qwen3.8:27b", "size": 1000, "digest": "a" * 64}
            if response_kind == "remote_tag":
                model["remote_model"] = "untrusted"
            return httpx.Response(200, json={"models": [model]})
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "qwen3.8:27b"
        assert body["format"] == schema and body["think"] is False
        assert body["options"] == {
            "temperature": 0,
            "num_ctx": config.ollama_context,
            "num_predict": 6000,
            "num_batch": 128,
        }
        assert "x-goog-api-key" not in request.headers
        if response_kind == "timeout":
            raise httpx.ReadTimeout("test", request=request)
        return httpx.Response(
            200,
            json={
                "done": True,
                "done_reason": "length" if response_kind == "incomplete" else "stop",
                "message": {"content": '{"value":"ok"}', "thinking": "ignore this"},
            },
        )

    def reserve():
        reservations.append(True)
        return True

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = OllamaProvider(config, "QWEN_27B", client)
        prompt = [{"role": "user", "content": "test"}]
        if response_kind == "valid":
            result = provider.request_typed(
                prompt, WorkspacePolicy(), reserve, json.loads, response_schema=schema
            )
            assert result == {"value": "ok"}
        else:
            errors = {
                "timeout": "OLLAMA_UNAVAILABLE",
                "incomplete": "AI_INCOMPLETE_OUTPUT",
                "remote_tag": "OLLAMA_MODEL_MISSING",
            }
            with pytest.raises(DomainError, match=errors[response_kind]):
                provider.request_typed(
                    prompt, WorkspacePolicy(), reserve, json.loads, response_schema=schema
                )
        assert provider.usage["cloud_requests"] == 0
        assert len(requests) == (1 if response_kind == "remote_tag" else 2)
        assert len(reservations) == (0 if response_kind == "remote_tag" else 1)
        if response_kind == "timeout":
            assert provider.usage["delivery_unknown"] is True


def model_response(body):
    return {"choices": [{"message": {"content": json.dumps(body)}}], "usage": {"total_tokens": 7}}


def unknown_proposal():
    return {
        "entity_kind": "unknown",
        "grain": "unknown",
        "status": "UNKNOWN",
        "decisions": [],
        "unresolved_questions": ["Confirm grain"],
    }


@pytest.fixture
def qwen_config(config):
    """Mock transport exercises the provider even when the running stack disables Qwen."""
    config.qwen_enabled = True
    config.qwen_base_url = "https://synthetic.test/v1"
    config.qwen_model = "knowledge"
    return config


def test_T09_qwen_invalid_json_retry_bounded(qwen_config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        assert "authorization" not in request.headers
        assert request.url.path == "/prefix/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{broken"}}]})

    qwen_config.qwen_base_url = "https://synthetic.test/prefix/v1/"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="AI_INVALID_JSON"):
            QwenProvider(qwen_config, client).propose(profile, schema)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,expected,count",
    [
        (403, "QWEN_ACCESS_DENIED", 1),
        (429, "QWEN_RATE_LIMITED", 1),
        (500, "QWEN_UNAVAILABLE", 2),
        (400, "QWEN_HTTP_ERROR", 1),
    ],
)
def test_qwen_http_contract(status, expected, count, qwen_config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(status, json={"sensitive": "must not escape"})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match=expected):
            QwenProvider(qwen_config, client).propose(profile, schema)
    assert len(calls) == count


def test_qwen_timeout_bounded(qwen_config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic")

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="QWEN_UNAVAILABLE"):
            QwenProvider(qwen_config, client).propose(profile, schema)
    assert len(calls) == 1  # Read timeout: delivery is unknown, so never resend blindly.


@pytest.mark.parametrize(
    "task", ["classify_dataset", "infer_grain", "propose_mapping", "suggest_transformation"]
)
def test_qwen_unknown_and_tasks(task, qwen_config, profile, schema):
    def transport(request):
        assert json.loads(request.content)["model"] == "knowledge"
        return httpx.Response(200, json=model_response(unknown_proposal()))

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = QwenProvider(qwen_config, client).propose(profile, schema, task)
    assert result.status == "UNKNOWN"


def test_T37_evidence_and_untrusted_injection(profile, schema, mapping):
    decision = mapping.decisions[0].model_copy(
        update={"decision": MappingStatus.PROPOSED, "evidence_ids": ["other-project:secret"]}
    )
    proposal = SchemaProposal(
        entity_kind="order", grain="order", status="PROPOSED", decisions=[decision]
    )
    with pytest.raises(DomainError, match="INVALID_EVIDENCE"):
        validate_ai_output(proposal.model_dump_json(), profile, schema)
    context = build_evidence_context(profile, schema)
    assert "000123" not in json.dumps(context)
    assert len(context["untrusted_data"]["columns"][0]["shape_samples"]) <= 3


def test_AI_cannot_self_approve(profile, schema, mapping):
    proposal = SchemaProposal(
        entity_kind="order", grain="order", status="PROPOSED", decisions=mapping.decisions
    )
    with pytest.raises(DomainError, match="AI_CANNOT_APPROVE"):
        validate_ai_output(proposal.model_dump_json(), profile, schema)


def test_gemini_mapping_response_schema_restricts_status_without_bypassing_validation(
    config, profile, schema, mapping
):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.external_ai_request_budget = 1
    config.gemini_api_key = SecretStr("synthetic-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1
    )
    proposal = SchemaProposal(
        entity_kind="order", grain="order", status="PROPOSED", decisions=mapping.decisions
    )

    def transport(request):
        grammar = json.loads(request.content)["generationConfig"]["responseJsonSchema"]
        assert set(grammar["$defs"]["MappingStatus"]["enum"]) == {
            "PROPOSED",
            "UNKNOWN",
            "AMBIGUOUS",
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": proposal.model_dump_json()}]}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="AI_CANNOT_APPROVE"):
            GeminiProvider(config, client).propose(profile, schema, policy, lambda: True)


def test_gemini_source_names_never_repaired_into_ids(config, profile, schema):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.external_ai_request_budget = 2
    config.gemini_api_key = SecretStr("synthetic-test-key")
    calls = []

    def transport(request):
        calls.append(request)
        prompt = json.loads(request.content)["systemInstruction"]["parts"][0]["text"]
        assert "source_field MUST be the exact columns[].id" in prompt
        body = unknown_proposal()
        body["decisions"] = [
            {
                "source_field": "Mã đơn",
                "candidate_target": "reference_id",
                "decision": "PROPOSED",
                "evidence_ids": ["table:c1"],
                "grain_assumption": "unknown",
                "transformation_candidate": {"op": "cast_string_preserve"},
            }
        ]
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]}
        )

    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=2
    )
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="INVALID_SOURCE_FIELD"):
            GeminiProvider(config, client).propose(profile, schema, policy, lambda: True)
    assert len(calls) == 1  # semantic failure is not retried, guessed or silently repaired


def test_gemini_structured_schema_diagnostics_redact_values_and_ignore_thoughts(config):
    from pydantic import BaseModel, SecretStr, ValidationError

    class Output(BaseModel):
        status: str

    config.allow_external_ai = True
    config.external_ai_request_budget = 1
    config.gemini_api_key = SecretStr("synthetic-test-key")
    schema = Output.model_json_schema()
    calls = []

    def transport(request):
        calls.append(request)
        assert json.loads(request.content)["generationConfig"]["responseJsonSchema"] == schema
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"thought": True, "text": "PRIVATE THOUGHT"},
                                {"text": '{"status":'},
                                {"text": '["PRIVATE INPUT"]}'},
                            ]
                        },
                    }
                ]
            },
        )

    def validate(content):
        try:
            return Output.model_validate_json(content)
        except ValidationError as exc:
            raise DomainError("AI_INVALID_JSON", "Sai hợp đồng.") from exc

    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1
    )
    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(transport)))
    try:
        with pytest.raises(DomainError, match="AI_INVALID_JSON"):
            provider.request_typed(
                [dict(content="test"), dict(content="synthetic")],
                policy,
                lambda: True,
                validate,
                max_attempts=1,
                response_schema=schema,
            )
        assert len(calls) == 1
        assert provider.usage["validation_errors"] == [dict(type="string_type", loc=["status"])]
        assert len(provider.usage["response_sha256"]) == 64
        assert "PRIVATE" not in json.dumps(provider.usage)
    finally:
        provider.close()


def test_T11_unknown_transform_rejected(profile, schema):
    proposal = unknown_proposal()
    proposal["decisions"] = [
        {
            "source_field": "c1",
            "candidate_target": "reference_id",
            "decision": "PROPOSED",
            "evidence_ids": ["table:c1"],
            "grain_assumption": "unknown",
            "transformation_candidate": {"op": "exec", "code": "1+1"},
        }
    ]
    with pytest.raises(DomainError, match="AI_INVALID_JSON"):
        validate_ai_output(json.dumps(proposal), profile, schema)


def test_T36_cloud_disabled_zero_http(config, profile, schema, tmp_path):
    def forbidden(request):
        pytest.fail("cloud request while disabled")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(DomainError, match="CLOUD_AI_DISABLED"):
            GeminiProvider(config, client).propose(profile, schema, WorkspacePolicy(), lambda: True)
        with pytest.raises(DomainError, match="CLOUD_PARSING_DISABLED"):
            parse_document(tmp_path / "no-file", config, WorkspacePolicy(), client, lambda: True)
    assert route_ai_task(WorkspacePolicy(), qwen_enabled=False) == "REVIEW"


def test_global_zero_budgets_block_even_when_workspace_allows_cloud(
    config, profile, schema, tmp_path
):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.allow_cloud_parsing = True
    config.external_ai_request_budget = 0
    config.cloud_parser_request_budget = 0
    config.gemini_api_key = SecretStr("synthetic-test-key")
    config.llama_cloud_api_key = SecretStr("synthetic-test-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED",
        allow_external_ai=True,
        external_request_budget=2,
        allow_cloud_parsing=True,
        parser_request_budget=1,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Zero global budget must stop before reserving or sending HTTP")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(DomainError, match="CLOUD_BUDGET_EXHAUSTED"):
            GeminiProvider(config, client).propose(profile, schema, policy, forbidden)
        with pytest.raises(DomainError, match="PARSER_BUDGET_EXHAUSTED"):
            parse_document(tmp_path / "not-opened.pdf", config, policy, client, forbidden)


@pytest.mark.parametrize("kind", ["missing_key", "budget", "success", "invalid", "http"])
def test_gemini_contract(kind, config, profile, schema):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.external_ai_request_budget = 2
    config.gemini_api_key = SecretStr("" if kind == "missing_key" else "synthetic-test-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=2
    )
    calls = []

    def transport(request):
        calls.append(request)
        assert "synthetic-test-key" == request.headers["x-goog-api-key"]
        if kind == "http":
            return httpx.Response(403, json={})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "invalid"
                                    if kind == "invalid"
                                    else json.dumps(unknown_proposal())
                                }
                            ]
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        provider = GeminiProvider(config, client)
        if kind == "success":
            assert provider.propose(profile, schema, policy, lambda: True).status == "UNKNOWN"
        else:
            with pytest.raises(DomainError):
                provider.propose(profile, schema, policy, lambda: kind != "budget")
    assert len(calls) == (0 if kind in {"missing_key", "budget"} else 1)


@pytest.mark.parametrize("status, delay", [(503, 2), (429, 35)])
def test_gemini_retries_known_http_rejection_after_provider_delay(
    status, delay, config, profile, schema, monkeypatch
):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.external_ai_request_budget = 2
    config.gemini_api_key = SecretStr("synthetic-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=2
    )
    waits, reservations = [], []
    monkeypatch.setattr("studio.ai_gateway.time.sleep", waits.append)
    monkeypatch.setattr("studio.ai_gateway.random.uniform", lambda *_: 0.1)
    responses = iter(
        [
            httpx.Response(status, headers={"Retry-After": str(delay)}),
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps(unknown_proposal())}]}}
                    ]
                },
            ),
        ]
    )
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(responses))) as client:
        provider = GeminiProvider(config, client)
        result = provider.propose(
            profile, schema, policy, lambda: reservations.append(True) or True
        )
    assert result.status == "UNKNOWN"
    assert waits == [delay + 0.1] and reservations == [True, True]
    assert [attempt["http_status"] for attempt in provider.usage["attempts"]] == [status, 200]


@pytest.mark.parametrize("kind", ["success", "missing_key", "failed", "timeout", "invalid", "http"])
def test_llamaparse_contract(kind, config, tmp_path):
    from pydantic import SecretStr

    config.allow_cloud_parsing = True
    config.cloud_parser_request_budget = 1
    config.llama_cloud_api_key = SecretStr("" if kind == "missing_key" else "synthetic-test-key")
    policy = WorkspacePolicy(allow_cloud_parsing=True, parser_request_budget=1)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"%PDF-1.7 synthetic adapter fixture")
    job_id = "pjb-" + uuid4().hex
    calls = []

    def transport(request):
        calls.append(request)
        if kind == "http":
            return httpx.Response(500, json={})
        if request.method == "POST":
            assert request.url.path.endswith("/parse/upload")
            assert b'"tier": "cost_effective"' in request.content
            assert b'"page_ranges": {"max_pages": 2}' in request.content
            return httpx.Response(200, json={"id": job_id, "status": "PENDING"})
        status = "RUNNING" if kind == "timeout" else "FAILED" if kind == "failed" else "COMPLETED"
        return httpx.Response(
            200,
            json={
                "job": {"id": job_id, "status": status},
                "markdown": {
                    "pages": []
                    if kind == "invalid"
                    else [{"page_number": 1, "markdown": "synthetic"}]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        if kind == "success":
            result = parse_document(
                path, config, policy, client, lambda: True, max_polls=2, sleep=lambda _: None
            )
            assert result.verification_status == "UNVERIFIED_EXTRACTION"
            assert result.pages[0].page_number == 1
        else:
            with pytest.raises(DomainError):
                parse_document(
                    path, config, policy, client, lambda: True, max_polls=2, sleep=lambda _: None
                )
    assert len(calls) == (
        0 if kind == "missing_key" else 3 if kind == "timeout" else 1 if kind == "http" else 2
    )


def test_llamaparse_resume_never_submits_or_reserves_again(config, tmp_path):
    from pydantic import SecretStr

    config.allow_cloud_parsing = True
    config.cloud_parser_request_budget = 0
    config.llama_cloud_api_key = SecretStr("synthetic-test-key")
    policy = WorkspacePolicy(allow_cloud_parsing=True, parser_request_budget=0)
    job_id = "pjb-synthetic-accepted-job"
    calls = []

    def transport(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path.endswith(job_id)
        return httpx.Response(
            200,
            json={
                "job": {"status": "COMPLETED"},
                "markdown": {"pages": [{"page_number": 1, "markdown": "000123"}]},
            },
        )

    def forbidden():
        pytest.fail("Polling an accepted job must not reserve or submit another parse")

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = parse_document(
            tmp_path / "not-opened.pdf", config, policy, client, forbidden, resume_job_id=job_id
        )
    assert len(calls) == 1 and result.verification_status == "UNVERIFIED_EXTRACTION"


def test_default_gemini_never_bypasses_cloud_policy(config):
    assert config.mapping_ai_provider == "GEMINI"
    assert route_ai_task(WorkspacePolicy()) == "REVIEW"
    assert (
        route_ai_task(
            WorkspacePolicy(mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=1)
        )
        == "GEMINI"
    )


def test_gemini_schema_error_keeps_only_safe_status_not_provider_message(config):
    from pydantic import SecretStr

    config.allow_external_ai = True
    config.external_ai_request_budget = 2
    config.gemini_api_key = SecretStr("synthetic-key-only")
    secret_message = "Synthetic-private-marker schema has too many states or branching"

    def handler(request):
        return httpx.Response(
            400, json={"error": {"status": "INVALID_ARGUMENT", "message": secret_message}}
        )

    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=2
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(config, client)
        with pytest.raises(DomainError, match="GEMINI_HTTP_ERROR"):
            provider.request_typed(
                [dict(role="system", content="synthetic"), dict(role="user", content="synthetic")],
                policy,
                lambda: True,
                lambda x: x,
                max_attempts=1,
            )
    assert provider.usage["http_status"] == 400
    assert provider.usage["provider_error_status"] == "INVALID_ARGUMENT"
    assert provider.usage["schema_complexity_rejected"] is True
    assert "Synthetic-private-marker" not in json.dumps(provider.usage)


@pytest.mark.parametrize("value", [None, "unlimited", "UNLIMITED"])
def test_explicit_unlimited_configuration_is_local_only(value):
    from pydantic import ValidationError
    from studio.config import Settings, remaining_requests, request_limit_reached

    config = Settings(
        _env_file=None,
        local_demo_access=True,
        external_ai_request_budget=value,
        agent_request_budget=value,
        planner_request_budget=value,
        assistant_request_budget=value,
    )
    assert config.external_ai_request_budget is None
    assert config.agent_request_budget is None
    assert not request_limit_reached(211, None)
    assert request_limit_reached(211, 210)
    assert remaining_requests((None, 211), (None, 184)) is None
    assert remaining_requests((None, 211), (2, 1)) == 1
    with pytest.raises(ValidationError):
        Settings(_env_file=None, local_demo_access=False, external_ai_request_budget=value)


@pytest.mark.parametrize("error", [None, 403, 429, "timeout", "cloud-off", "missing-key"])
def test_unlimited_keeps_provider_permissions_receipts_and_bounded_delivery(
    config, error, monkeypatch
):
    from pydantic import SecretStr
    from studio.ai_gateway import GeminiProvider

    config.local_demo_access = True
    config.allow_external_ai = error != "cloud-off"
    config.external_ai_request_budget = None
    config.gemini_api_key = SecretStr("" if error == "missing-key" else "synthetic-key")
    policy = WorkspacePolicy(
        mode="CLOUD_ALLOWED", allow_external_ai=True, external_request_budget=None
    )
    calls = []
    reservations = []
    monkeypatch.setattr("studio.ai_gateway.time.sleep", lambda _: None)

    def reserve():
        reservations.append(True)
        return True

    def transport(request):
        calls.append(request)
        if error == "timeout":
            raise httpx.ReadTimeout("synthetic unknown delivery", request=request)
        if isinstance(error, int):
            return httpx.Response(
                error,
                json={
                    "error": {
                        "status": "PERMISSION_DENIED" if error == 403 else "RESOURCE_EXHAUSTED"
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 9,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 12,
                },
            },
        )

    provider = GeminiProvider(config, httpx.Client(transport=httpx.MockTransport(transport)))
    try:
        if error is None:
            assert (
                provider.request_typed(
                    [{"content": "test"}, {"content": "synthetic"}],
                    policy,
                    reserve,
                    json.loads,
                    max_attempts=2,
                )
                == {}
            )
            assert provider.usage["tokens"]["totalTokenCount"] == 12
            assert provider.usage["attempts"][0]["tokens"]["totalTokenCount"] == 12
            assert provider.usage["attempts"][0]["latency_ms"] >= 0
        else:
            with pytest.raises(DomainError):
                provider.request_typed(
                    [{"content": "test"}, {"content": "synthetic"}],
                    policy,
                    reserve,
                    json.loads,
                    max_attempts=2,
                )
        expected = 0 if error in {"cloud-off", "missing-key"} else 2 if error == 429 else 1
        assert len(calls) == len(reservations) == expected
    finally:
        provider.close()
