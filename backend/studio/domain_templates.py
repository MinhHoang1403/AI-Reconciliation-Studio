"""Domain schema suggestions reuse SchemaDefinition; they do not infer settlement data.

Currency/sign/coverage are never supplied by a template as an approval. Settlement
and payout suggestions are exposed only when a real canonical source declares that
entity. Existing mapping validation must still approve every required semantic.
"""

from studio.contracts import SchemaDefinition, SchemaField


def domain_templates(workspace_id: str, source_entities: set[str]) -> list[SchemaDefinition]:
    specs = [
        ("order", ["platform", "shop_id", "order_id"], "order", "item_gross", "gross"),
        (
            "order_line",
            ["platform", "shop_id", "order_id", "line_id"],
            "order_line",
            "item_gross",
            "gross",
        ),
        (
            "financial_event",
            ["platform", "shop_id", "event_id", "event_type"],
            "financial_event",
            "UNKNOWN",
            "UNKNOWN",
        ),
    ]
    for entity in ("settlement", "payout"):
        if entity in source_entities:
            specs.append((entity, ["platform", "shop_id", entity + "_id"], entity, entity, entity))
    result = []
    for entity, keys, grain, metric, basis in specs:
        fields = [SchemaField(id=k, name=k, data_type="string") for k in keys]
        fields += [
            SchemaField(id="event_date", name="Ngày sự kiện", data_type="date"),
            SchemaField(id="currency", name="Currency cần xác nhận", data_type="string"),
            SchemaField(
                id="amount",
                name="Số tiền cần xác nhận",
                data_type="decimal",
                semantic_metric=metric,
                amount_basis=basis,
                currency="UNKNOWN",
                unit="UNKNOWN",
            ),
        ]
        result.append(
            SchemaDefinition(
                id="template-" + entity,
                workspace_id=workspace_id,
                name=entity + " — đề xuất cần review",
                revision=1,
                entity_kind=entity,
                grain=grain,
                fields=fields,
                business_key_fields=keys if entity != "order_line" else [],
            )
        )
    return result
