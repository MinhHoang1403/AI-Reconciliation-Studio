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
