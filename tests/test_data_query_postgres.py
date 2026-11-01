"""Oracle truy vấn trên canonical thật, giữ scope và tiền chính xác."""

from decimal import Decimal

import pytest
from studio.access import Actor
from studio.contracts.data_query import DataQuery
from studio.data_query import execute_query
from studio.database import MembershipRow
from studio.errors import DomainError
from test_postgres import pg  # noqa: F401
from test_reconciliation_postgres import prepare_pair

pytestmark = pytest.mark.integration


def test_query_oracle_paging_decimal_all_matching_and_scope(pg):  # noqa: F811
    _, factory, _ = pg
    pid, plan = prepare_pair(pg)
    actor = Actor("test-owner", "demo", "owner")
    base = dict(project_id=pid, source_kind="CANONICAL", source_id=plan.left.canonical_id)
    with factory() as db:
        page = execute_query(
            db,
            actor,
            DataQuery(
                **base,
                select_fields=["tracking_id", "delivery_charge"],
                sort=[dict(field_id="tracking_id")],
                limit=1,
            ),
        )
        assert page.total_count == page.input_count == 3 and page.truncated
        assert page.rows[0]["tracking_id"] == "000701"
        assert Decimal(page.rows[0]["delivery_charge"]) == Decimal("25.00")
        assert page.rows[0]["source_provenance"][0]["row"] == 2
        summed = execute_query(
            db,
            actor,
            DataQuery(
                **base,
                currency_field="currency",
                aggregations=[dict(op="sum_decimal", field_id="delivery_charge"), dict(op="count")],
                limit=1,
            ),
        )
        assert Decimal(summed.rows[0]["sum_decimal_delivery_charge_0"]) == Decimal("42.75")
        assert summed.rows[0]["count_rows_1"] == 3 and summed.input_count == 3
        assert {r["row"] for r in summed.rows[0]["source_provenance"]} == {2, 3, 4}
        grouped = execute_query(
            db,
            actor,
            DataQuery(
                **base,
                group_by=["currency"],
                currency_field="currency",
                aggregations=[dict(op="sum_decimal", field_id="delivery_charge")],
                sort=[dict(field_id="sum_decimal_delivery_charge_0", descending=True)],
            ),
        )
        assert grouped.total_count == 1 and grouped.rows[0]["currency"] == "VND"
        assert Decimal(grouped.rows[0]["sum_decimal_delivery_charge_0"]) == Decimal("42.75")
        assert len(grouped.rows[0]["source_provenance"]) == 3
        filtered = execute_query(
            db,
            actor,
            DataQuery(
                **base,
                filters=[dict(field_id="delivery_charge", op="gt", value="10.00")],
                select_fields=["tracking_id"],
                sort=[dict(field_id="tracking_id")],
                offset=1,
                limit=1,
            ),
        )
        assert filtered.total_count == 2 and filtered.rows[0]["tracking_id"] == "000702"
        for update in (
            dict(project_id="foreign-project"),
            dict(select_fields=["../secret"]),
            dict(select_fields=["invented_column"]),
        ):
            from pydantic import ValidationError

            with pytest.raises((DomainError, ValidationError)):
                execute_query(db, actor, DataQuery.model_validate(base | update))
        with pytest.raises(DomainError, match="QUERY_CURRENCY_REQUIRED"):
            execute_query(
                db,
                actor,
                DataQuery(
                    **base, aggregations=[dict(op="sum_decimal", field_id="delivery_charge")]
                ),
            )
        db.delete(db.get(MembershipRow, ("demo", actor.id)))
        db.commit()
        with pytest.raises(DomainError, match="RESOURCE_NOT_FOUND"):
            execute_query(db, actor, DataQuery(**base))


def test_query_raw_cannot_sum_unconfirmed_money_and_viewer_is_read_only(pg):  # noqa: F811
    _, factory, _ = pg
    pid, plan = prepare_pair(pg)
    actor = Actor("test-owner", "demo", "viewer")
    with factory() as db:
        from studio.database import CanonicalRow

        row = db.get(CanonicalRow, plan.left.canonical_id)
        q = DataQuery(
            project_id=pid,
            source_kind="RAW_PREVIEW",
            source_id=row.source_table_id,
            select_fields=["c2"],
            filters=[dict(field_id="c2", op="eq", value="000702")],
        )
        result = execute_query(db, actor, q)
        assert result.total_count == 1 and result.rows[0]["c2"] == "000702"
        assert result.verification_status == "RAW_UNVERIFIED"
        from studio.contracts.data_query import QueryAggregation

        q.aggregations = [QueryAggregation(op="sum_decimal", field_id="c4")]
        with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
            execute_query(db, actor, q)


def test_agent_tool_registry_reuses_transactions_and_denies_viewer_write(pg):  # noqa: F811
    from pydantic import TypeAdapter, ValidationError
    from sqlalchemy import func, select
    from studio.agent_tools import AgentAction, NormalizeAction, execute_tool
    from studio.contracts.assistant import AssistantContext
    from studio.database import CanonicalRow, DatasetRow, JobRow, TableRow, VersionRow

    client, factory, _ = pg
    pid, plan = prepare_pair(pg)
    actor = Actor("test-owner", "demo", "owner")
    with factory() as db:
        canonical = db.get(CanonicalRow, plan.left.canonical_id)
        table = db.get(TableRow, canonical.source_table_id)
        version = db.get(VersionRow, table.dataset_version_id)
        dataset = db.get(DatasetRow, version.dataset_id)
        action = NormalizeAction(
            name="run_normalization",
            context=AssistantContext(project_id=pid),
            dataset_id=dataset.id,
            mapping_id=canonical.mapping_id,
        )
        baseline = db.scalar(select(func.count()).select_from(JobRow))
        ref = execute_tool(db, actor, action, "transaction-neutral-agent")
        assert ref.job_id
        db.rollback()
        assert db.scalar(select(func.count()).select_from(JobRow)) == baseline
        db.get(MembershipRow, ("demo", actor.id)).role = "viewer"
        db.commit()
        with pytest.raises(DomainError):
            execute_tool(db, Actor(actor.id, "demo", "viewer"), action, "viewer-denied")
        response = client.post(
            "/api/agent/queries",
            json=dict(
                project_id=pid,
                source_kind="CANONICAL",
                source_id=plan.left.canonical_id,
                select_fields=["tracking_id"],
            ),
        )
        assert response.status_code == 200 and response.json()["total_count"] == 3
    with pytest.raises(ValidationError):
        TypeAdapter(AgentAction).validate_python(dict(name="approve_mapping", actor_id="owner"))
