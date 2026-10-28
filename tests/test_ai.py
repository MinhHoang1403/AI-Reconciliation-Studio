import json
from uuid import uuid4

import httpx
import pytest
from studio.ai_gateway import (
    GeminiProvider,
    QwenProvider,
    build_evidence_context,
    route_ai_task,
    validate_ai_output,
)
from studio.contracts import MappingStatus, SchemaProposal, WorkspacePolicy
from studio.document_parser import parse_document
from studio.errors import DomainError


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


def test_T09_qwen_invalid_json_retry_bounded(config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        assert "authorization" not in request.headers
        assert request.url.path == "/prefix/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{broken"}}]})

    config.qwen_base_url = "https://synthetic.test/prefix/v1/"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="AI_INVALID_JSON"):
            QwenProvider(config, client).propose(profile, schema)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,expected,count",
    [(403, "QWEN_ACCESS_DENIED", 1), (500, "QWEN_UNAVAILABLE", 2), (400, "QWEN_HTTP_ERROR", 1)],
)
def test_qwen_http_contract(status, expected, count, config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(status, json={"sensitive": "must not escape"})

    config.qwen_base_url = "https://synthetic.test/v1"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match=expected):
            QwenProvider(config, client).propose(profile, schema)
    assert len(calls) == count


def test_qwen_timeout_bounded(config, profile, schema):
    calls = []

    def transport(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic")

    config.qwen_base_url = "https://synthetic.test/v1"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(DomainError, match="QWEN_UNAVAILABLE"):
            QwenProvider(config, client).propose(profile, schema)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "task", ["classify_dataset", "infer_grain", "propose_mapping", "suggest_transformation"]
)
def test_qwen_unknown_and_tasks(task, config, profile, schema):
    def transport(request):
        assert json.loads(request.content)["model"] == "knowledge"
        return httpx.Response(200, json=model_response(unknown_proposal()))

    config.qwen_base_url = "https://synthetic.test/v1"
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = QwenProvider(config, client).propose(profile, schema, task)
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
    assert len(calls) == (0 if kind in {"missing_key", "budget"} else 2 if kind == "invalid" else 1)


@pytest.mark.parametrize("kind", ["success", "missing_key", "failed", "timeout", "invalid", "http"])
def test_llamaparse_contract(kind, config, tmp_path):
    from pydantic import SecretStr

    config.allow_cloud_parsing = True
    config.cloud_parser_request_budget = 1
    config.llama_cloud_api_key = SecretStr("" if kind == "missing_key" else "synthetic-test-key")
    policy = WorkspacePolicy(allow_cloud_parsing=True, parser_request_budget=1)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"%PDF-1.7 synthetic adapter fixture")
    job_id = str(uuid4())
    calls = []

    def transport(request):
        calls.append(request)
        if kind == "http":
            return httpx.Response(500, json={})
        if request.method == "POST":
            assert request.url.path.endswith("/parse/upload")
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
