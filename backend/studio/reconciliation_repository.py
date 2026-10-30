"""Scoped canonical catalogue and checksum-verified Parquet projections.

DuckDB is an in-memory reader, never a second source of metadata or arbitrary SQL
surface. Only backend-owned artifact paths and fixed parameterized queries enter it.
"""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.config import settings
from studio.contracts import CanonicalDataset, DatasetProfile, SchemaDefinition
from studio.contracts.reconciliation import (
    CanonicalRecord,
    MatchGroup,
    MatchResult,
    MetricSnapshot,
    ReconciliationRun,
    RunArtifactRef,
    SourceCatalogue,
)
from studio.database import (
    ArtifactRow,
    CanonicalRow,
    DatasetRow,
    MappingRow,
    RunRow,
    SchemaRow,
    TableRow,
    VersionRow,
)
from studio.errors import DomainError
from studio.repository import get_scoped, mapping_contract, schema_fingerprint
from studio.storage import checksum, storage_path, write_parquet


def catalogue_for_project(db: Session, actor: Actor, project_id: str) -> list[SourceCatalogue]:
    rows = db.scalars(
        select(CanonicalRow)
        .join(TableRow, CanonicalRow.source_table_id == TableRow.id)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .join(DatasetRow, VersionRow.dataset_id == DatasetRow.id)
        .where(CanonicalRow.workspace_id == actor.workspace_id, DatasetRow.project_id == project_id)
        .order_by(CanonicalRow.id)
        .limit(200)
    )
    result = []
    for row in rows:
        canonical = CanonicalDataset.model_validate(row.contract).model_copy(
            update={"stale": row.stale}
        )
        table = db.get(TableRow, row.source_table_id)
        mapping = db.get(MappingRow, row.mapping_id)
        schema = db.get(SchemaRow, canonical.schema_id)
        if table is None or mapping is None or schema is None:
            raise DomainError("SOURCE_METADATA_INCONSISTENT", "Thiếu metadata canonical.")
        version = db.get(VersionRow, table.dataset_version_id)
        assert version is not None
        dataset = db.get(DatasetRow, version.dataset_id)
        assert dataset is not None
        definition = SchemaDefinition.model_validate(schema.definition)
        profile = DatasetProfile.model_validate(table.profile)
        approved = mapping_contract(mapping)
        identifier_columns = {p.column_id for p in profile.columns if p.identifier_candidate}
        rigid = set(definition.business_key_fields)
        rigid.update(
            str(d.candidate_target)
            for d in approved.decisions
            if d.source_field in identifier_columns and d.candidate_target
        )
        if table.active_mapping_id != mapping.id or mapping.status != "APPROVED":
            canonical.stale = True
        result.append(
            SourceCatalogue(
                project_id=project_id,
                name=dataset.name,
                canonical=canonical,
                schema_definition=definition,
                identifier_fields=sorted(rigid),
                profile=profile,
                mapping=approved,
            )
        )
    return result


def selected_catalogue(
    db: Session, actor: Actor, project_id: str, ids: list[str]
) -> list[SourceCatalogue]:
    indexed = {c.canonical.id: c for c in catalogue_for_project(db, actor, project_id)}
    if len(ids) != 2 or ids[0] == ids[1] or any(i not in indexed for i in ids):
        raise DomainError("SOURCE_SCOPE_INVALID", "Chọn hai canonical thuộc đúng project.", 422)
    return [indexed[i] for i in ids]


def _connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        config={
            "threads": 1,
            "memory_limit": "96MB",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
        }
    )


def load_canonical_records(
    db: Session, actor: Actor, canonical: CanonicalDataset, record_ids: list[str] | None = None
) -> list[CanonicalRecord]:
    """Read exact typed records, preserving every member location and Decimal value."""
    artifact = get_scoped(db, ArtifactRow, canonical.artifact.id, actor)
    if (
        artifact.kind != "canonical"
        or artifact.sha256 != canonical.artifact.sha256
        or artifact.dataset_version_id != canonical.dataset_version_id
    ):
        raise DomainError("ARTIFACT_REF_INVALID", "Canonical artifact không khớp tham chiếu.")
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256:
        raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Checksum canonical không hợp lệ.")
    if canonical.row_count > 100000:
        raise DomainError("RECONCILIATION_ROW_LIMIT", "Nguồn vượt giới hạn canonical.")
    sql = (
        "SELECT canonical_record_id, record_payload, invalid, quality_flags, source_provenance "
        "FROM read_parquet(?)"
    )
    args: list[Any] = [str(path)]
    if record_ids is not None:
        if len(record_ids) > 100:
            raise DomainError("EVIDENCE_PAGE_LIMIT", "Mỗi lần đọc tối đa 100 bản ghi bằng chứng.")
        sql += " WHERE canonical_record_id IN (SELECT unnest(?))"
        args.append(record_ids)
    records = []
    with _connection() as connection:
        cursor = connection.execute(sql, args)
        while batch := cursor.fetchmany(512):
            for record_id, payload, invalid, flags, lineage in batch:
                records.append(
                    CanonicalRecord(
                        id=record_id,
                        payload=payload,
                        invalid=invalid,
                        quality_flags=flags,
                        provenance=lineage,
                    )
                )
            if len(records) > 100000:
                raise DomainError("RECONCILIATION_ROW_LIMIT", "Artifact vượt giới hạn bản ghi.")
    if record_ids is None and (
        len(records) != canonical.row_count
        or sum(r.invalid for r in records) != canonical.invalid_count
    ):
        raise DomainError("CANONICAL_COUNT_MISMATCH", "Số dòng canonical khác hợp đồng đã công bố.")
    if len({r.id for r in records}) != len(records):
        raise DomainError("DUPLICATE_RECORD_ID", "Canonical có ID trùng.")
    return records


def write_match_artifact(root: Path, key: str, result: MatchResult) -> str:
    frame = pl.DataFrame(
        [
            {
                "group_id": g.id,
                "linkage_state": g.linkage_state,
                "comparison_state": g.comparison_state,
                "group_json": g.model_dump_json(),
            }
            for g in result.groups
        ],
        schema={
            "group_id": pl.String,
            "linkage_state": pl.String,
            "comparison_state": pl.String,
            "group_json": pl.String,
        },
    )
    return write_parquet(root, key, frame)


def result_path(run: RunRow) -> Path:
    if run.result_key is None or run.result_sha256 is None:
        raise DomainError("RUN_RESULT_NOT_READY", "Kết quả chưa sẵn sàng.", 409)
    path = storage_path(settings.storage_root, run.result_key)
    if checksum(path) != run.result_sha256:
        raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Checksum kết quả không hợp lệ.")
    return path


def match_page(
    run: RunRow, offset: int, limit: int, search: str = "", linkage: str = "", comparison: str = ""
) -> tuple[list[MatchGroup], int]:
    path = result_path(run)
    where = (
        "WHERE (? = '' OR linkage_state = ?) AND (? = '' OR comparison_state = ?) "
        "AND (? = '' OR contains(lower(group_json), lower(?)))"
    )
    params = [str(path), linkage, linkage, comparison, comparison, search, search]
    with _connection() as connection:
        count = connection.execute(
            f"SELECT count(*) FROM read_parquet(?) {where}", params
        ).fetchone()
        rows = connection.execute(
            f"SELECT group_json FROM read_parquet(?) {where} ORDER BY group_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [MatchGroup.model_validate_json(row[0]) for row in rows], int(count[0]) if count else 0


def match_groups_by_ids(run: RunRow, group_ids: list[str]) -> list[MatchGroup]:
    """Read a bounded case page in one query; IDs are parameters, never SQL fragments."""
    if not group_ids:
        return []
    if len(group_ids) > 100:
        raise ValueError("A case page cannot exceed 100 groups")
    with _connection() as connection:
        rows = connection.execute(
            "SELECT group_json FROM read_parquet(?) WHERE group_id IN (SELECT unnest(?))",
            [str(result_path(run)), group_ids],
        ).fetchall()
    return [MatchGroup.model_validate_json(row[0]) for row in rows]


def all_match_groups(run: RunRow) -> Iterator[MatchGroup]:
    with _connection() as connection:
        cursor = connection.execute(
            "SELECT group_json FROM read_parquet(?) ORDER BY group_id", [str(result_path(run))]
        )
        while rows := cursor.fetchmany(128):
            for row in rows:
                yield MatchGroup.model_validate_json(row[0])


def run_contract(row: RunRow) -> ReconciliationRun:
    ref = (
        RunArtifactRef(
            id=row.id + ":matches",
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            run_id=row.id,
            sha256=row.result_sha256,
            revision=row.engine_revision,
        )
        if row.result_sha256
        else None
    )
    return ReconciliationRun.model_validate(
        dict(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            contract_id=row.contract_id,
            status=row.status,
            engine_revision=row.engine_revision,
            source_refs=row.source_refs,
            checks=row.checks,
            result_ref=ref,
            metric_snapshot=MetricSnapshot.model_validate(row.metric_snapshot)
            if row.metric_snapshot is not None
            else None,
        )
    )


def template_signatures(catalogue: list[SourceCatalogue]) -> dict[str, Any]:
    """Stable semantic/transform signatures, with old mapping refs retained separately."""
    result = {}
    for side, cat in zip(("left", "right"), catalogue, strict=True):
        transforms = (
            [
                {
                    "source": d.source_field,
                    "target": d.candidate_target,
                    "transform": d.transformation_candidate.model_dump(mode="json"),
                }
                for d in cat.mapping.decisions
            ]
            if cat.mapping
            else []
        )
        result[side] = {
            "schema": schema_fingerprint(cat.schema_definition),
            "transforms": hashlib.sha256(
                json.dumps(transforms, sort_keys=True).encode()
            ).hexdigest(),
            "mapping_id": cat.canonical.mapping_revision_id,
            "entity": cat.canonical.entity_kind,
        }
    return result
