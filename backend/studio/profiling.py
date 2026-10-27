"""F05/F06: deterministic observations and review-only schema candidates [D]."""

import hashlib
import json
import re
import unicodedata

import polars as pl

from studio.contracts import ColumnProfile, DatasetProfile, SchemaDefinition, SourceColumn


def normalized_name(value: str) -> str:
    value = value.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def profile_table(
    frame: pl.DataFrame,
    columns: list[SourceColumn],
    table_id: str,
    workspace_id: str,
    artifact_id: str,
) -> DatasetProfile:
    """F05: exact counts, capped representative values; no inferred monetary locale.

    O(rows × columns), with at most 5 samples per column. Samples stay scoped; AI
    receives redacted structural samples from build_evidence_context instead.
    """
    profiles = []
    key_candidates = []
    for col in columns:
        values = frame[col.id]
        nonnull = values.drop_nulls()
        distinct = nonnull.n_unique()
        nonempty = [str(v) for v in nonnull.to_list() if v != ""]
        candidates = ["string"]
        if nonempty and all(re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", v) for v in nonempty):
            candidates.append("numeric_candidate")
        if nonempty and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", v) for v in nonempty):
            candidates.append("date_candidate")
        identifier = any(re.fullmatch(r"0\d+", v) for v in nonempty) or bool(
            re.search(
                r"(?:^|[^a-z0-9])(?:id|ma|reference|code)(?:$|[^a-z0-9])", normalized_name(col.name)
            )
        )
        if identifier:
            candidates.append("identifier")
        if distinct == frame.height and frame.height > 0 and values.null_count() == 0:
            key_candidates.append([col.id])
        observed = values.unique(maintain_order=True).head(3).to_list()
        if nonempty:
            for edge in (min(nonempty, key=len), max(nonempty, key=len)):
                if edge not in observed:
                    observed.append(edge)
        lengths = [len(v) for v in nonempty]
        profiles.append(
            ColumnProfile(
                column_id=col.id,
                name=col.name,
                null_count=values.null_count(),
                empty_count=(values == "").sum(),
                distinct_count=distinct,
                duplicate_count=len(nonnull) - distinct,
                type_candidates=candidates,
                min_value=min(nonempty) if nonempty else None,
                max_value=max(nonempty) if nonempty else None,
                min_length=min(lengths) if lengths else None,
                max_length=max(lengths) if lengths else None,
                samples=observed[:5],
                evidence_ids=[f"{table_id}:{col.id}"],
                identifier_candidate=identifier,
            )
        )
    return DatasetProfile(
        source_table_id=table_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        row_count=frame.height,
        columns=profiles,
        key_candidates=key_candidates,
    )


ALIASES = {
    "reference_id": {"ma don", "order id", "order_id", "tracking id", "ma van don", "reference"},
    "gross_amount": {"gross amount", "gross", "tong truoc giam"},
    "net_amount": {"net amount", "net"},
    "description": {"description", "mo ta", "ten"},
    "event_date": {"date", "ngay", "created at"},
    "currency": {"currency", "tien te"},
    "shop_id": {"shop", "shop id", "cua hang"},
    "platform": {"platform", "san"},
}


def find_mapping_candidates(
    profile: DatasetProfile, schema: SchemaDefinition
) -> dict[str, list[str]]:
    """F06: bounded alias/type shortlist, never approval or calibrated probability.

    [D] name/instance/constraint approach inspired by Rahm–Bernstein taxonomy.
    O(source fields × target fields); ambiguous Total never means gross/net.
    """
    output = {}
    for source in profile.columns:
        name = normalized_name(source.name).strip()
        compatible = [
            f
            for f in schema.fields
            if not (source.identifier_candidate and f.data_type == "decimal")
        ]
        targets = [
            f.id
            for f in compatible
            if name in ALIASES.get(f.id, set()) or name in {normalized_name(f.name), f.id}
        ]
        output[source.column_id] = targets[:5]
    return output


def source_signature(profile: DatasetProfile) -> str:
    payload = [
        (c.column_id, c.name, c.type_candidates, c.identifier_candidate) for c in profile.columns
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def default_schema(workspace_id: str, schema_id: str) -> SchemaDefinition:
    from studio.contracts import SchemaField

    names = [
        ("reference_id", "Mã tham chiếu", "string"),
        ("description", "Mô tả", "string"),
        ("gross_amount", "Tiền trước giảm trừ", "decimal"),
        ("net_amount", "Tiền sau giảm trừ", "decimal"),
        ("amount", "Số tiền cần định nghĩa", "decimal"),
        ("currency", "Tiền tệ", "string"),
        ("event_date", "Ngày phát sinh", "date"),
        ("shop_id", "Cửa hàng", "string"),
        ("platform", "Nền tảng", "string"),
    ]
    return SchemaDefinition(
        id=schema_id,
        workspace_id=workspace_id,
        name="Dữ liệu giao dịch tổng quát",
        revision=1,
        entity_kind="unknown",
        grain="unknown",
        fields=[
            SchemaField.model_validate({"id": i, "name": n, "data_type": t}) for i, n, t in names
        ],
    )
