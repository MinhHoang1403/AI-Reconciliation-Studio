"""Synthetic labelled sources, independent from matching and verification implementations."""

import csv
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from studio.contracts import ArtifactRef, CanonicalDataset, SchemaDefinition, SchemaField
from studio.contracts.reconciliation import CanonicalRecord, ReconciliationPlan, SourceCatalogue

FIXTURES = Path(__file__).parent / "fixtures"


def records(filename):
    result = []
    with (FIXTURES / filename).open(encoding="utf-8", newline="") as stream:
        for i, row in enumerate(csv.DictReader(stream), 1):
            invalid = False
            for field in ("gross_amount", "delivery_charge"):
                if field in row:
                    try:
                        row[field] = Decimal(row[field]) if row[field] else None
                    except InvalidOperation:
                        row[field], invalid = None, True
            row["event_date"] = datetime.fromisoformat(row["event_date"]).replace(tzinfo=UTC)
            result.append(
                CanonicalRecord(
                    id=f"{filename}-{i}",
                    payload=row,
                    invalid=invalid,
                    quality_flags=["INVALID_DECIMAL"] if invalid else [],
                    provenance=[
                        dict(
                            file_id=filename,
                            source_table_id=filename,
                            source_row_id=f"{filename}:{i}",
                            sheet="CSV",
                            row=i + 1,
                        )
                    ],
                )
            )
    return result


def catalogue(source_id, rows, *, grain="order", metric="item_gross", amount="gross_amount"):
    fields = (
        [
            SchemaField(
                id=k,
                name=k,
                data_type=("date" if k == "event_date" else "decimal" if k == amount else "string"),
                **(
                    dict(semantic_metric=metric, amount_basis="gross", currency="VND", unit="VND")
                    if k == amount
                    else {}
                ),
            )
            for k in rows[0].payload
        ]
        if rows
        else [
            SchemaField(id="order_id", name="ID", data_type="string"),
            SchemaField(id="event_date", name="Date", data_type="date"),
            SchemaField(
                id=amount,
                name="Amount",
                data_type="decimal",
                semantic_metric=metric,
                amount_basis="gross",
                currency="VND",
                unit="VND",
            ),
            SchemaField(id="currency", name="Currency", data_type="string"),
        ]
    )
    ref = ArtifactRef(
        id=source_id,
        workspace_id="demo",
        dataset_version_id=source_id,
        kind="canonical",
        sha256="a" * 64,
        revision="normalization-1",
        quality="READY",
    )
    canonical = CanonicalDataset(
        id=source_id,
        workspace_id="demo",
        dataset_version_id=source_id,
        source_table_id=source_id,
        schema_id=source_id,
        schema_revision=1,
        grain=grain,
        entity_kind="order" if grain in {"order", "order_line"} else "delivery",
        mapping_revision_id=source_id,
        normalization_revision="normalization-1",
        row_count=len(rows),
        valid_count=sum(not r.invalid for r in rows),
        invalid_count=sum(r.invalid for r in rows),
        quality_status="READY",
        artifact=ref,
        error_artifact=ref.model_copy(update={"kind": "errors", "id": source_id + "-errors"}),
    )
    return SourceCatalogue(
        project_id="project",
        name=source_id,
        canonical=canonical,
        schema_definition=SchemaDefinition(
            id=source_id,
            workspace_id="demo",
            name=source_id,
            revision=1,
            entity_kind=canonical.entity_kind,
            grain=grain,
            fields=fields,
        ),
        identifier_fields=["order_id", "shop_id", "tracking_id"],
    )


def plan(
    left="internal",
    right="shopee",
    *,
    cardinality="ONE_TO_ONE",
    platform="Shopee",
    amount="gross_amount",
    metric="item_gross",
    keys=None,
    entity="order",
):
    slot = dict(
        date_field="event_date",
        time_basis="event_date",
        currency_field="currency",
        coverage_start="2026-10-01",
        coverage_end="2026-11-01",
        completeness="CONFIRMED",
        snapshot_at="2026-11-02T00:00:00Z",
    )
    return ReconciliationPlan.model_validate(
        dict(
            name="Synthetic reconciliation",
            entity_kind=entity,
            left=dict(
                canonical_id=left,
                role="reference",
                filters={"platform": platform} if platform else {},
                **slot,
            ),
            right=dict(canonical_id=right, role="counterpart", **slot),
            join_keys=[
                dict(left=k, right=k) for k in (keys or ["platform", "shop_id", "order_id"])
            ],
            comparison_metrics=[
                dict(
                    left=amount,
                    right=amount,
                    metric_id=metric,
                    currency="VND",
                    unit="VND",
                    amount_basis="gross",
                    sign_convention="SOURCE_SIGNED",
                )
            ],
            comparison_grain="order" if entity == "order" else "delivery",
            cardinality=cardinality,
            aggregation="NONE" if cardinality == "ONE_TO_ONE" else "SUM_SIGNED",
            period_start="2026-10-01",
            period_end="2026-10-31",
            timezone="UTC",
            effective_from="2026-10-01",
            evidence_ids=[left, right],
        )
    )
