"""Owner-authorized reuse of a specific human-approved mapping revision."""

from collections import Counter

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.contracts import CanonicalDataset, DatasetProfile, MappingRevision, SchemaDefinition
from studio.database import (
    ArtifactRow,
    AuditRow,
    CanonicalRow,
    MappingRow,
    MembershipRow,
    SchemaRow,
    TableRow,
    VersionRow,
)
from studio.mapping_verification import preflight_rows
from studio.normalization import NORMALIZATION_REVISION
from studio.repository import project_for_table
from studio.schema_mapping import TransformPlan

REUSE_ENABLED = "ENABLE_MAPPING_REUSE"
REUSE_DISABLED = "DISABLE_MAPPING_REUSE"


def current_reuse_grant(db: Session, mapping: MappingRow) -> AuditRow | None:
    """Return the active grant only while its issuer still owns the workspace."""
    event = db.scalar(
        select(AuditRow)
        .where(
            AuditRow.workspace_id == mapping.workspace_id,
            AuditRow.resource_id == mapping.id,
            AuditRow.action.in_([REUSE_ENABLED, REUSE_DISABLED]),
        )
        .order_by(AuditRow.created_at.desc(), AuditRow.id.desc())
        .limit(1)
    )
    if event is None or event.action != REUSE_ENABLED:
        return None
    member = db.get(MembershipRow, (mapping.workspace_id, event.actor_id))
    return event if member is not None and member.role == "owner" else None


def approved_reference(db: Session, mapping: MappingRow, table: TableRow) -> bool:
    """Only an active human approval with a clean current canonical is a reusable reference."""
    if (
        mapping.status != "APPROVED"
        or not mapping.decision
        or table.active_mapping_id != mapping.id
        or table.parsed_contract["warnings"]
        or not db.scalar(
            select(AuditRow.id)
            .where(
                AuditRow.workspace_id == mapping.workspace_id,
                AuditRow.resource_id == mapping.id,
                AuditRow.action == "APPROVE_MAPPING",
            )
            .limit(1)
        )
    ):
        return False
    canonical = db.scalar(
        select(CanonicalRow).where(
            CanonicalRow.mapping_id == mapping.id,
            CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
            CanonicalRow.stale.is_(False),
        )
    )
    definition = db.get(SchemaRow, mapping.schema_id)
    if definition is None:
        return False
    schema = SchemaDefinition.model_validate(definition.definition)
    approved = MappingRevision.model_validate(mapping.decision)
    source_keys = {
        decision.candidate_target
        for decision in approved.decisions
        if decision.transformation_candidate.op == "cast_string_preserve"
    }
    return (
        canonical is not None
        and CanonicalDataset.model_validate(canonical.contract).quality_status == "READY"
        and not approved.rules
        and bool(schema.business_key_fields)
        and set(schema.business_key_fields) <= source_keys
        and not project_for_table(db, table).business_scope.startswith("UNCONFIRMED:")
    )


def exact_reuse_source(
    db: Session, source: TableRow, target: TableRow, mapping: MappingRow
) -> bool:
    """Strict source identity gate. Headers alone cannot authorize financial reuse."""
    if (
        source.workspace_id != target.workspace_id
        or source.sheet != target.sheet
        or target.parsed_contract["warnings"]
    ):
        return False
    left = project_for_table(db, source)
    right = project_for_table(db, target)
    if (
        left.id != right.id
        or left.business_scope != mapping.business_scope
        or left.business_scope.startswith("UNCONFIRMED:")
    ):
        return False
    versions = [db.get(VersionRow, t.dataset_version_id) for t in (source, target)]
    if any(version is None for version in versions):
        return False
    prior, incoming = versions
    assert prior is not None and incoming is not None
    if (
        prior.parser_revision != incoming.parser_revision
        or prior.parse_config != incoming.parse_config
    ):
        return False
    files = [
        db.get(ArtifactRow, t.parsed_contract["provenance"][0]["file_id"]) for t in (source, target)
    ]
    first, second = files
    return (
        first is not None
        and second is not None
        and bool(first.metadata_json.get("extension"))
        and first.metadata_json.get("extension") == second.metadata_json.get("extension")
        and bool(first.metadata_json.get("filename"))
        and first.metadata_json.get("filename") == second.metadata_json.get("filename")
    )


def _format_facts(profile: DatasetProfile, mapping: MappingRevision) -> dict[str, object]:
    """Compare which formats cover a column, independently of report size."""
    profiles = {column.column_id: column for column in profile.columns}
    facts: dict[str, object] = {}
    for decision in mapping.decisions:
        column = profiles[decision.source_field]
        observations = column.observations
        nonempty = observations.get("nonempty_count")
        operation = decision.transformation_candidate.op
        if operation in {"parse_decimal", "parse_date"}:
            field = "numeric_locales" if operation == "parse_decimal" else "date_formats"
            formats = observations.get(field)
            facts[column.column_id] = (
                sorted(key for key, count in formats.items() if count == nonempty)
                if isinstance(formats, dict) and nonempty
                else []
            )
        currencies = observations.get("currency_counts")
        if isinstance(currencies, dict) and currencies:
            facts[f"currency:{column.column_id}"] = sorted(currencies)
    return facts


def passes_reuse_preflight(
    frame: pl.DataFrame, source: DatasetProfile, target: DatasetProfile, plan: TransformPlan
) -> tuple[bool, Counter[str]]:
    """Check every row, exact formatting evidence and unique preserved business keys."""
    if _format_facts(source, plan.mapping) != _format_facts(target, plan.mapping):
        return False, Counter({"FORMAT_OR_CURRENCY_DRIFT": 1})
    keys = {
        decision.candidate_target: decision.source_field
        for decision in plan.mapping.decisions
        if decision.transformation_candidate.op == "cast_string_preserve"
    }
    key_fields = plan.schema.business_key_fields
    if not key_fields or not set(key_fields) <= keys.keys():
        return False, Counter({"BUSINESS_KEY_REVIEW_REQUIRED": 1})
    raw_keys = frame.select([keys[key] for key in key_fields])
    if raw_keys.n_unique() != frame.height or any(
        raw_keys[column].null_count() or (raw_keys[column] == "").any()
        for column in raw_keys.columns
    ):
        return False, Counter({"BUSINESS_KEY_REVIEW_REQUIRED": 1})
    invalid, errors, _ = preflight_rows(frame, plan)
    return frame.height > 0 and not invalid and not errors, errors
