from pathlib import Path

import polars as pl
import pytest
from studio.config import Settings
from studio.contracts import (
    DatasetProfile,
    MappingDecision,
    MappingRevision,
    SchemaDefinition,
    SchemaField,
    SourceColumn,
)
from studio.database import now
from studio.profiling import profile_table, source_signature


@pytest.fixture
def config(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, storage_root=tmp_path, max_rows=100)


@pytest.fixture
def frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "c1": ["000123", "000124", "000125", "000126"],
            "c2": ["1.234,50", "invalid", None, "0"],
            "_source_row": [2, 3, 4, 5],
            "_source_row_id": ["r1", "r2", "r3", "r4"],
        }
    )


@pytest.fixture
def profile(frame: pl.DataFrame) -> DatasetProfile:
    return profile_table(
        frame,
        [
            SourceColumn(id="c1", name="Mã đơn", source_index=1),
            SourceColumn(id="c2", name="Total", source_index=2),
        ],
        "table",
        "workspace",
        "parsed",
    )


@pytest.fixture
def schema() -> SchemaDefinition:
    return SchemaDefinition(
        id="schema",
        workspace_id="workspace",
        name="Synthetic order rows",
        revision=1,
        entity_kind="order",
        grain="one source order row",
        business_key_fields=["reference_id"],
        fields=[
            SchemaField(id="reference_id", name="Mã đơn", data_type="string", required=True),
            SchemaField(
                id="amount",
                name="Gross amount",
                data_type="decimal",
                required=True,
                semantic_metric="synthetic_gross",
                amount_basis="gross",
                currency="VND",
                unit="VND",
            ),
        ],
    )


@pytest.fixture
def mapping(profile: DatasetProfile, schema: SchemaDefinition) -> MappingRevision:
    return MappingRevision(
        id="mapping",
        workspace_id="workspace",
        source_table_id="table",
        source_signature=source_signature(profile),
        schema_id=schema.id,
        schema_revision=1,
        business_scope="synthetic",
        revision=1,
        status="APPROVED",
        approved_by="owner",
        approved_at=now(),
        decisions=[
            MappingDecision(
                source_field="c1",
                candidate_target="reference_id",
                decision="APPROVED",
                evidence_ids=["table:c1"],
                grain_assumption=schema.grain,
                transformation_candidate={"op": "cast_string_preserve"},
            ),
            MappingDecision(
                source_field="c2",
                candidate_target="amount",
                decision="APPROVED",
                evidence_ids=["table:c2"],
                grain_assumption=schema.grain,
                transformation_candidate={"op": "parse_decimal", "locale": "vi-VN"},
            ),
        ],
    )
