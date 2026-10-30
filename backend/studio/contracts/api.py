"""Public REST envelopes; flexible table cells are bounded JSON values, not provider output."""

from typing import Any, Literal

from pydantic import Field, JsonValue

from studio.contracts import (
    ArtifactRef,
    CanonicalDataset,
    Contract,
    Dataset,
    JobStatus,
    MappingRevision,
    MappingStatus,
    ParsedTableArtifact,
    Project,
    SchemaDefinition,
    SchemaProposal,
)


class ProjectList(Contract):
    items: list[Project]
    total: int


class DatasetView(Dataset):
    created_at: str


class DatasetList(Contract):
    items: list[DatasetView]
    total: int


class UploadItem(DatasetView):
    reused: bool
    job_id: str | None = None


class UploadResponse(Contract):
    items: list[UploadItem]


class TableView(Contract):
    id: str
    sheet: str
    row_count: int
    active_mapping_id: str | None
    parsed: ParsedTableArtifact


class TableList(Contract):
    items: list[TableView]


class MappingView(Contract):
    id: str
    revision: int
    status: MappingStatus
    proposal: SchemaProposal
    decision: MappingRevision | None
    schema_definition: SchemaDefinition = Field(alias="schema")


class MappingList(Contract):
    items: list[MappingView]


class ArtifactList(Contract):
    items: list[ArtifactRef]
    canonical_datasets: list[CanonicalDataset]


class PreviewResponse(Contract):
    items: list[dict[str, JsonValue]]
    total: int
    columns: list[str]
    offset: int
    limit: int
    view: str


class JobView(Contract):
    id: str
    kind: str
    status: JobStatus
    attempts: int
    error_code: str | None
    result: dict[str, Any] | None


class JobList(Contract):
    items: list[JobView]


class JobAccepted(Contract):
    job_id: str
    status: JobStatus


class PreparationAction(Contract):
    kind: Literal["UPLOAD", "WAIT", "REVIEW_MAPPING", "NORMALIZE", "REVIEW_DATA", "RECONCILE"]
    dataset_id: str | None = None
    table_id: str | None = None
    canonical_id: str | None = None


class ProjectSummary(Contract):
    dataset_count: int
    table_count: int
    mapping_review_count: int
    ready_canonical_count: int
    active_job_count: int
    partial_canonical_count: int = 0
    stale_canonical_count: int = 0
    failed_canonical_count: int = 0
    preparation_action: PreparationAction | None = None
    latest_verified_run_id: str | None = None
