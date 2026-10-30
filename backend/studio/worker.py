"""Single-concurrency durable PostgreSQL queue with leases, fencing and atomic publication."""

import logging
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx
import polars as pl
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from studio.ai_gateway import PROMPT_REVISION, GeminiProvider, QwenProvider, manual_proposal
from studio.config import settings
from studio.contracts import (
    CanonicalDataset,
    DatasetProfile,
    EvidenceRef,
    FileArtifact,
    MappingStatus,
    ParsedTableArtifact,
    SchemaDefinition,
    SchemaProposal,
    WorkspacePolicy,
)
from studio.database import (
    ArtifactRow,
    AttemptRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    SchemaRow,
    SessionFactory,
    TableRow,
    TraceRow,
    VersionRow,
    WorkspaceRow,
    identifier,
    now,
)
from studio.document_parser import (
    DOCUMENT_PARSER_REVISION,
    DocumentArtifact,
    parse_document,
    verify_parser_account,
)
from studio.errors import DomainError
from studio.normalization import NORMALIZATION_REVISION, apply_transform_plan
from studio.parsing import FileInspection, ParseConfig, parse_to_artifacts, verify_parse
from studio.profiling import default_schema, profile_table, source_signature
from studio.repository import (
    artifact_ref,
    create_mapping,
    enqueue_job,
    mapping_contract,
    project_for_table,
    reserve_document_request,
    reserve_gemini_request,
)
from studio.schema_mapping import compile_transform_plan, validate_mapping
from studio.storage import checksum, storage_path, write_parquet

logger = logging.getLogger("studio.worker")


def claim_job(db: Session) -> tuple[str, str] | None:
    """Claim atomically via SKIP LOCKED; exhausted expired leases are failed, never loop forever."""
    current = now()
    eligible = or_(
        and_(JobRow.status.in_(["QUEUED", "RETRYABLE_FAILURE"]), JobRow.available_at <= current),
        and_(JobRow.status == "RUNNING", JobRow.lease_until < current),
    )
    job = db.scalar(
        select(JobRow)
        .where(eligible)
        .order_by(JobRow.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        db.rollback()
        return None
    if job.status == "RUNNING":
        previous = db.scalar(
            select(AttemptRow).where(AttemptRow.job_id == job.id, AttemptRow.number == job.attempts)
        )
        if previous:
            previous.status, previous.error_code, previous.finished_at = (
                "FAILED",
                "LEASE_EXPIRED",
                current,
            )
    if job.attempts >= 3:
        job.status, job.error_code = "FAILED", "JOB_RETRY_EXHAUSTED"
        job.claim_token = None
        db.commit()
        return None
    job.status, job.attempts = "RUNNING", job.attempts + 1
    job.claim_token = identifier()
    job.lease_until = current + timedelta(seconds=settings.worker_lease_seconds)
    db.add(AttemptRow(job_id=job.id, number=job.attempts))
    db.commit()
    return job.id, job.claim_token


def _fence(db: Session, job_id: str, token: str) -> JobRow:
    job = db.scalar(select(JobRow).where(JobRow.id == job_id).with_for_update())
    if (
        job is None
        or job.status != "RUNNING"
        or job.claim_token != token
        or job.lease_until is None
        or job.lease_until <= now()
    ):
        raise DomainError("JOB_LEASE_LOST", "Job mất quyền xuất bản; không công bố artifact.")
    return job


def _finish(db: Session, job: JobRow, result: dict[str, Any]) -> None:
    job.status, job.result, job.lease_until = "SUCCEEDED", result, None
    attempt = db.scalar(
        select(AttemptRow).where(AttemptRow.job_id == job.id, AttemptRow.number == job.attempts)
    )
    assert attempt is not None
    attempt.status, attempt.finished_at = "SUCCEEDED", now()


def _parse(job_id: str, token: str) -> None:
    with SessionFactory() as db:
        job = db.get(JobRow, job_id)
        assert job is not None
        dataset = db.get(DatasetRow, job.payload["dataset_id"])
        version = db.get(VersionRow, job.payload["version_id"])
        raw = db.get(ArtifactRow, job.payload["file_id"])
        assert dataset is not None and version is not None and raw is not None
        inspection = FileInspection.model_validate(raw.metadata_json)
        frames = parse_to_artifacts(
            storage_path(settings.storage_root, raw.storage_key),
            inspection,
            ParseConfig.model_validate(version.parse_config),
            settings,
        )
        pending = []
        for parsed in frames:
            quality = verify_parse(parsed, settings)
            table_id = str(uuid5(NAMESPACE_URL, f"{version.id}:{parsed.sheet}"))
            ids = [
                str(uuid5(NAMESPACE_URL, f"{raw.id}:{parsed.sheet}:{r}"))
                for r in parsed.frame["_source_row"].to_list()
            ]
            frame = parsed.frame.with_columns(pl.Series("_source_row_id", ids, dtype=pl.String))
            artifact_id = identifier()
            key = f"{job.workspace_id}/{version.id}/parsed/{artifact_id}.parquet"
            sha256 = write_parquet(settings.storage_root, key, frame)
            artifact = ArtifactRow(
                id=artifact_id,
                workspace_id=job.workspace_id,
                dataset_version_id=version.id,
                kind="parsed",
                sha256=sha256,
                revision=version.parser_revision,
                quality=quality,
                storage_key=key,
                metadata_json={"cell_metadata": parsed.cell_metadata, "preamble": parsed.preamble},
            )
            profile = profile_table(frame, parsed.columns, table_id, job.workspace_id, artifact_id)
            evidence = [
                EvidenceRef(
                    id=f"{table_id}:{c.id}",
                    workspace_id=job.workspace_id,
                    file_id=raw.id,
                    source_table_id=table_id,
                    sheet=parsed.sheet,
                    row=parsed.header_row,
                    column=c.id,
                )
                for c in parsed.columns
            ]
            contract = ParsedTableArtifact(
                source_table_id=table_id,
                artifact=artifact_ref(artifact),
                row_count=frame.height,
                columns=parsed.columns,
                sheet=parsed.sheet,
                header_row=parsed.header_row,
                provenance=evidence,
                warnings=parsed.warnings,
                parser_revision=version.parser_revision,
            )
            table = TableRow(
                id=table_id,
                workspace_id=job.workspace_id,
                dataset_version_id=version.id,
                artifact_id=artifact_id,
                sheet=parsed.sheet,
                row_count=frame.height,
                parsed_contract=contract.model_dump(mode="json"),
                profile=profile.model_dump(mode="json"),
            )
            pending.append((artifact, table, profile))
        db.rollback()
        job = _fence(db, job_id, token)
        for artifact, table, profile in pending:
            db.add(artifact)
            db.flush()
            db.add(table)
            db.flush()
            schema = default_schema(job.workspace_id, identifier())
            fallback = manual_proposal(profile, schema)
            create_mapping(db, table, fallback.model_dump(mode="json"), schema)
            if job.payload.get("request_ai_mapping", True):
                enqueue_job(
                    db,
                    job.workspace_id,
                    job.project_id,
                    "mapping",
                    f"mapping:auto:{table.id}:{PROMPT_REVISION}",
                    {"table_id": table.id},
                )
        dataset = db.get(DatasetRow, job.payload["dataset_id"])
        assert dataset is not None
        dataset.status = "NEEDS_MAPPING_REVIEW"
        _finish(db, job, {"table_ids": [t.id for _, t, _ in pending]})
        db.commit()


def _mapping(job_id: str, token: str) -> None:
    provider_name = settings.mapping_ai_provider
    provider = GeminiProvider(settings) if provider_name == "GEMINI" else QwenProvider(settings)
    started = time.monotonic()
    error: DomainError | None = None
    cached = False
    try:
        with SessionFactory() as db:
            job = db.get(JobRow, job_id)
            assert job is not None
            table = db.get(TableRow, job.payload["table_id"])
            assert table is not None
            profile = DatasetProfile.model_validate(table.profile)
            workspace = db.get(WorkspaceRow, job.workspace_id)
            assert workspace is not None
            policy = WorkspacePolicy.model_validate(workspace.policy)
            workspace_id = job.workspace_id
            schema = default_schema(job.workspace_id, identifier())
            # Strict source signature + workspace + business scope; reuse still requires review.
            template = db.scalar(
                select(MappingRow)
                .where(
                    MappingRow.workspace_id == job.workspace_id,
                    MappingRow.signature == source_signature(profile),
                    MappingRow.business_scope == project_for_table(db, table).business_scope,
                    MappingRow.status == "APPROVED",
                )
                .order_by(MappingRow.created_at.desc())
                .limit(1)
            )
            if template and template.decision:
                template_schema = db.get(SchemaRow, template.schema_id)
                assert template_schema is not None
                schema = SchemaDefinition.model_validate(template_schema.definition)
                old = mapping_contract(template)
                decisions = [d.model_copy(deep=True) for d in old.decisions]
                for decision in decisions:
                    decision.decision = MappingStatus.PROPOSED
                    decision.evidence_ids = [f"{table.id}:{decision.source_field}"]
                proposal = SchemaProposal(
                    entity_kind=schema.entity_kind,
                    grain=schema.grain,
                    status="PROPOSED",
                    decisions=decisions,
                    unresolved_questions=["Xác nhận mẫu đã duyệt vẫn đúng với nguồn mới."],
                )
                proposal = validate_mapping(proposal, profile, schema)
                cached = True
            else:
                db.rollback()  # do not hold a PostgreSQL transaction while waiting for AI
                if isinstance(provider, GeminiProvider):

                    def reserve() -> bool:
                        with SessionFactory() as budget_db:
                            _fence(budget_db, job_id, token)
                            allowed = reserve_gemini_request(
                                budget_db, workspace_id, job_id, settings
                            )
                            budget_db.commit()  # durable even if HTTP fails or worker crashes
                            return allowed

                    proposal = provider.propose(profile, schema, policy, reserve)
                else:
                    proposal = provider.propose(profile, schema)
            db.rollback()
            job = _fence(db, job_id, token)
            table = db.get(TableRow, job.payload["table_id"])
            assert table is not None
            db.refresh(table, with_for_update=True)
            mapping = create_mapping(db, table, proposal.model_dump(mode="json"), schema)
            _finish(
                db,
                job,
                {
                    "mapping_id": mapping.id,
                    "cache_hit": cached,
                    "source": "APPROVED_TEMPLATE" if cached else provider_name,
                },
            )
            db.add(
                TraceRow(
                    workspace_id=job.workspace_id,
                    job_id=job.id,
                    provider="CACHE" if cached else provider_name,
                    task_id="propose_mapping",
                    prompt_revision=PROMPT_REVISION,
                    usage=provider.usage,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome="VALIDATED_PROPOSAL",
                )
            )
            db.commit()
    except DomainError as exc:
        error = exc
    finally:
        provider.close()
    if error:
        with SessionFactory() as db:
            job = _fence(db, job_id, token)
            db.add(
                TraceRow(
                    workspace_id=job.workspace_id,
                    job_id=job.id,
                    provider=provider_name,
                    task_id="propose_mapping",
                    prompt_revision=PROMPT_REVISION,
                    usage=provider.usage,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome=error.code,
                )
            )
            db.commit()
        raise error


def _document(job_id: str, token: str) -> None:
    """Bounded document route: one durable create reservation, resumable GET, unverified artifact.

    A crash after a reservation but before storing the remote ID blocks resubmission.
    No conversion into canonical records or automatic approval occurs here.
    """
    with SessionFactory() as db:
        job = db.get(JobRow, job_id)
        assert job is not None
        workspace = db.get(WorkspaceRow, job.workspace_id)
        raw = db.get(ArtifactRow, job.payload["file_id"])
        dataset = db.get(DatasetRow, job.payload["dataset_id"])
        assert workspace is not None and raw is not None and dataset is not None
        policy = WorkspacePolicy.model_validate(workspace.policy)
        workspace_id, version_id = job.workspace_id, job.payload["version_id"]
        raw_id, raw_key = raw.id, raw.storage_key
        inspection = FileInspection.model_validate(raw.metadata_json)
        source_file = FileArtifact(
            id=raw.id,
            workspace_id=workspace_id,
            owner_id=dataset.owner_id,
            sha256=raw.sha256,
            filename=inspection.filename,
            media_type=inspection.media_type,
            size=inspection.size,
        )
        remote_id = (job.result or {}).get("provider_job_id")
        if not settings.allow_cloud_parsing or not policy.allow_cloud_parsing:
            raise DomainError("CLOUD_PARSING_DISABLED", "Parser cloud chưa được cấp phép.")
        if not settings.llama_cloud_api_key.get_secret_value():
            raise DomainError("LLAMAPARSE_KEY_MISSING", "Chưa cấu hình khóa LlamaParse.")
        if not remote_id and (
            settings.cloud_parser_request_budget <= 0
            or policy.parser_request_budget <= 0
            or settings.cloud_parser_credit_budget < 6
        ):
            raise DomainError("PARSER_BUDGET_EXHAUSTED", "Hết allowance parser cloud.")

    def reserve() -> bool:
        with SessionFactory() as db:
            _fence(db, job_id, token)
            allowed = reserve_document_request(db, workspace_id, raw_id, settings)
            db.commit()
            return allowed

    def remember(provider_job_id: str) -> None:
        with SessionFactory() as db:
            job = _fence(db, job_id, token)
            job.result = {"provider_job_id": provider_job_id}
            db.commit()

    started = time.monotonic()
    with httpx.Client(timeout=settings.ai_timeout_seconds, follow_redirects=False) as client:
        if not remote_id:
            verify_parser_account(client, settings)
        extraction = parse_document(
            storage_path(settings.storage_root, raw_key),
            settings,
            policy,
            client,
            reserve,
            max_polls=60,
            resume_job_id=remote_id,
            on_job_created=remember,
            filename=inspection.filename,
        )
    artifact_id = identifier()
    key = f"{workspace_id}/{version_id}/document/{artifact_id}.json"
    path = storage_path(settings.storage_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(extraction.model_dump_json())
    with SessionFactory() as db:
        job = _fence(db, job_id, token)
        row = ArtifactRow(
            id=artifact_id,
            workspace_id=workspace_id,
            dataset_version_id=version_id,
            kind="document",
            sha256=checksum(path),
            revision=DOCUMENT_PARSER_REVISION,
            quality="UNVERIFIED_EXTRACTION",
            storage_key=key,
            metadata_json={"source_file": source_file.model_dump(mode="json")},
        )
        db.add(row)
        db.flush()
        DocumentArtifact(artifact=artifact_ref(row), source_file=source_file, extraction=extraction)
        dataset = db.get(DatasetRow, job.payload["dataset_id"])
        assert dataset is not None
        dataset.status = "PARSED"
        _finish(
            db,
            job,
            {"document_artifact_id": artifact_id, "provider_job_id": extraction.provider_job_id},
        )
        db.add(
            TraceRow(
                workspace_id=workspace_id,
                job_id=job_id,
                provider="LLAMAPARSE",
                task_id="parse_document",
                prompt_revision="parse-cost-effective-1",
                usage={
                    "parser_credits": extraction.usage.get("credits"),
                    "parse_jobs_created": int(remote_id is None),
                    "pages_returned": len(extraction.pages),
                    "tier": "cost_effective",
                },
                latency_ms=int((time.monotonic() - started) * 1000),
                outcome="UNVERIFIED_EXTRACTION",
            )
        )
        db.commit()


def _normalize(job_id: str, token: str) -> None:
    with SessionFactory() as db:
        job = db.get(JobRow, job_id)
        assert job is not None
        table = db.get(TableRow, job.payload["table_id"])
        mapping = db.get(MappingRow, job.payload["mapping_id"])
        assert table is not None and mapping is not None
        db.refresh(table, with_for_update=True)
        if table.active_mapping_id != mapping.id or mapping.status != "APPROVED":
            raise DomainError("STALE_MAPPING", "Revision mapping đã được thay thế.")
        existing = db.scalar(
            select(CanonicalRow).where(
                CanonicalRow.mapping_id == mapping.id,
                CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
            )
        )
        if existing:
            job = _fence(db, job_id, token)
            _finish(db, job, {"canonical_id": existing.id, "reused": True})
            db.commit()
            return
        schema_row = db.get(SchemaRow, mapping.schema_id)
        parsed_row = db.get(ArtifactRow, table.artifact_id)
        assert schema_row is not None and parsed_row is not None
        schema = SchemaDefinition.model_validate(schema_row.definition)
        profile = DatasetProfile.model_validate(table.profile)
        plan = compile_transform_plan(mapping_contract(mapping), schema, profile)
        parsed = ParsedTableArtifact.model_validate(table.parsed_contract)
        path = storage_path(settings.storage_root, parsed_row.storage_key)
        if checksum(path) != parsed_row.sha256:
            raise DomainError("PARSED_CHECKSUM_MISMATCH", "Artifact parsed bị thay đổi.")
        frame = pl.read_parquet(path)
        version = db.get(VersionRow, table.dataset_version_id)
        assert version is not None
        version_id, dataset_id = version.id, version.dataset_id
        table_id, sheet, mapping_id = table.id, table.sheet, mapping.id
        db.rollback()
        result = apply_transform_plan(
            frame, plan, version_id, table_id, parsed.provenance[0].file_id, sheet
        )
        outputs = []
        for kind, output in (("canonical", result.canonical), ("errors", result.errors)):
            artifact_id = identifier()
            key = f"{job.workspace_id}/{version_id}/{kind}/{artifact_id}.parquet"
            sha256 = write_parquet(settings.storage_root, key, output)
            outputs.append(
                ArtifactRow(
                    id=artifact_id,
                    workspace_id=job.workspace_id,
                    dataset_version_id=version_id,
                    kind=kind,
                    sha256=sha256,
                    revision=NORMALIZATION_REVISION,
                    quality=result.quality_status,
                    storage_key=key,
                    metadata_json={"mapping_id": mapping_id},
                )
            )
        job = _fence(db, job_id, token)
        table = db.get(TableRow, table_id)
        assert table is not None
        db.refresh(table, with_for_update=True)
        if table.active_mapping_id != mapping_id:
            raise DomainError(
                "STALE_MAPPING", "Mapping đã đổi trong lúc xử lý; chưa công bố kết quả."
            )
        # A second worker with a different idempotency key may have completed during IO.
        existing = db.scalar(
            select(CanonicalRow).where(
                CanonicalRow.mapping_id == mapping_id,
                CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
            )
        )
        if existing:
            _finish(db, job, {"canonical_id": existing.id, "reused": True})
            db.commit()
            return
        db.add_all(outputs)
        db.flush()
        canonical_id = identifier()
        contract = CanonicalDataset(
            id=canonical_id,
            workspace_id=job.workspace_id,
            dataset_version_id=version_id,
            source_table_id=table_id,
            schema_id=schema.id,
            schema_revision=schema.revision,
            grain=schema.grain,
            entity_kind=schema.entity_kind,
            mapping_revision_id=mapping_id,
            normalization_revision=NORMALIZATION_REVISION,
            row_count=result.row_count,
            valid_count=result.valid_count,
            invalid_count=result.invalid_count,
            quality_status=result.quality_status,
            artifact=artifact_ref(outputs[0]),
            error_artifact=artifact_ref(outputs[1]),
        )
        db.add(
            CanonicalRow(
                id=canonical_id,
                workspace_id=job.workspace_id,
                source_table_id=table_id,
                mapping_id=mapping_id,
                normalization_revision=NORMALIZATION_REVISION,
                contract=contract.model_dump(mode="json"),
            )
        )
        db.flush()
        dataset = db.get(DatasetRow, dataset_id)
        assert dataset is not None
        tables = list(
            db.scalars(
                select(TableRow)
                .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
                .where(VersionRow.dataset_id == dataset_id)
            )
        )
        active = list(
            db.scalars(
                select(CanonicalRow).where(
                    CanonicalRow.source_table_id.in_([t.id for t in tables]),
                    CanonicalRow.stale.is_(False),
                )
            )
        )
        if len(active) == len(tables):
            dataset.status = (
                "PARTIAL"
                if any(c.contract["quality_status"] != "READY" for c in active)
                else "READY"
            )
        else:
            dataset.status = "PARTIAL"
        _finish(db, job, {"canonical_id": canonical_id, "quality_status": result.quality_status})
        db.commit()


def process_job(job_id: str, token: str) -> None:
    from studio.assistant_jobs import execute_assistant
    from studio.reconciliation_exports import execute_export
    from studio.reconciliation_jobs import execute_planning, execute_reconciliation

    try:
        with SessionFactory() as db:
            job = db.get(JobRow, job_id)
            assert job is not None
            kind = job.kind
        handlers: dict[str, Callable[[str, str], None]] = {
            "assistant": lambda job_id, token: execute_assistant(
                job_id, token, SessionFactory, _fence, _finish
            ),
            "parse": _parse,
            "mapping": _mapping,
            "normalize": _normalize,
            "document_parse": _document,
            "export": lambda job_id, token: execute_export(
                job_id, token, SessionFactory, _fence, _finish
            ),
            "reconciliation_plan": lambda job_id, token: execute_planning(
                job_id, token, SessionFactory, _fence, _finish
            ),
            "reconcile": lambda job_id, token: execute_reconciliation(
                job_id, token, SessionFactory, _fence, _finish
            ),
        }
        if kind not in handlers:
            raise DomainError("UNKNOWN_JOB_KIND", "Loại job chưa được hỗ trợ.")
        handlers[kind](job_id, token)
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "WORKER_INTERNAL_ERROR"
        logger.error("job=%s code=%s type=%s", job_id, code, type(exc).__name__)
        with SessionFactory() as db:
            try:
                job = _fence(db, job_id, token)
            except DomainError:
                return
            blocked = code.startswith(
                ("QWEN_", "GEMINI_", "AI_", "CLOUD_", "PARSER_", "LLAMAPARSE_")
            ) or code in {
                "INVALID_EVIDENCE",
                "INVALID_SOURCE_FIELD",
                "INVALID_TARGET_FIELD",
            }
            transient = code == "WORKER_INTERNAL_ERROR" and job.attempts < 3
            job.status = "BLOCKED" if blocked else "RETRYABLE_FAILURE" if transient else "FAILED"
            job.error_code, job.lease_until = code, None
            job.available_at = now() + timedelta(seconds=5 * job.attempts)
            attempt = db.scalar(
                select(AttemptRow).where(
                    AttemptRow.job_id == job.id, AttemptRow.number == job.attempts
                )
            )
            assert attempt is not None
            attempt.status, attempt.error_code, attempt.finished_at = job.status, code, now()
            if kind == "parse" and job.status == "FAILED":
                dataset = db.get(DatasetRow, job.payload["dataset_id"])
                if dataset:
                    dataset.status = "FAILED"
            if kind == "reconcile" and job.status in {"FAILED", "BLOCKED"}:
                from studio.database import RunRow

                run = db.get(RunRow, job.payload["run_id"])
                if run is not None and run.metric_snapshot is None:
                    run.status = "BLOCKED"
            db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    heartbeat = Path("/tmp/studio-worker-heartbeat")
    while True:
        heartbeat.touch()
        with SessionFactory() as db:
            claimed = claim_job(db)
        if claimed:
            process_job(*claimed)
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
