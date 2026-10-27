"""Create scoped metadata, approvals, durable queue and audit tables.

DDL is a snapshot, independent of future ORM changes. Destructive downgrade is blocked.
"""

import sqlalchemy as sa
from alembic import op

revision = "create_data_foundation"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE workspaces (
	id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	policy JSONB NOT NULL,
	PRIMARY KEY (id)
)""",
    """CREATE TABLE audit_events (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	actor_id VARCHAR(64) NOT NULL,
	action VARCHAR(80) NOT NULL,
	resource_id VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)""",
    """CREATE TABLE memberships (
	workspace_id VARCHAR(64) NOT NULL,
	actor_id VARCHAR(64) NOT NULL,
	role VARCHAR(20) NOT NULL,
	PRIMARY KEY (workspace_id, actor_id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)""",
    """CREATE TABLE projects (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	name VARCHAR(200) NOT NULL,
	business_scope VARCHAR(200) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)""",
    """CREATE INDEX ix_projects_workspace_id ON projects (workspace_id)""",
    """CREATE TABLE schema_definitions (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	definition JSONB NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)""",
    """CREATE INDEX ix_schema_definitions_workspace_id ON schema_definitions (workspace_id)""",
    """CREATE TABLE sessions (
	token_hash VARCHAR(64) NOT NULL,
	actor_id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)""",
    """CREATE TABLE datasets (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	owner_id VARCHAR(64) NOT NULL,
	name VARCHAR(255) NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	parse_signature VARCHAR(64) NOT NULL,
	status VARCHAR(40) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (project_id, sha256, parse_signature),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
)""",
    """CREATE INDEX ix_datasets_workspace_id ON datasets (workspace_id)""",
    """CREATE TABLE jobs (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	kind VARCHAR(30) NOT NULL,
	status VARCHAR(40) NOT NULL,
	idempotency_key VARCHAR(200) NOT NULL,
	payload JSONB NOT NULL,
	attempts INTEGER NOT NULL,
	claim_token VARCHAR(64),
	lease_until TIMESTAMP WITH TIME ZONE,
	available_at TIMESTAMP WITH TIME ZONE NOT NULL,
	error_code VARCHAR(80),
	result JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, idempotency_key),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(project_id) REFERENCES projects (id)
)""",
    """CREATE INDEX ix_jobs_status ON jobs (status)""",
    """CREATE INDEX ix_jobs_workspace_id ON jobs (workspace_id)""",
    """CREATE TABLE ai_traces (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	job_id VARCHAR(64) NOT NULL,
	provider VARCHAR(30) NOT NULL,
	task_id VARCHAR(50) NOT NULL,
	prompt_revision VARCHAR(30) NOT NULL,
	usage JSONB NOT NULL,
	latency_ms INTEGER NOT NULL,
	outcome VARCHAR(80) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
)""",
    """CREATE TABLE dataset_versions (
	id VARCHAR(64) NOT NULL,
	dataset_id VARCHAR(64) NOT NULL,
	revision INTEGER NOT NULL,
	parser_revision VARCHAR(60) NOT NULL,
	parse_config JSONB NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (dataset_id, revision),
	FOREIGN KEY(dataset_id) REFERENCES datasets (id)
)""",
    """CREATE TABLE job_attempts (
	id VARCHAR(64) NOT NULL,
	job_id VARCHAR(64) NOT NULL,
	number INTEGER NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	status VARCHAR(40) NOT NULL,
	error_code VARCHAR(80),
	PRIMARY KEY (id),
	UNIQUE (job_id, number),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
)""",
    """CREATE TABLE artifacts (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	dataset_version_id VARCHAR(64) NOT NULL,
	kind VARCHAR(20) NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	revision VARCHAR(100) NOT NULL,
	quality VARCHAR(60) NOT NULL,
	storage_key VARCHAR(500) NOT NULL,
	metadata_json JSONB NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(dataset_version_id) REFERENCES dataset_versions (id),
	UNIQUE (storage_key)
)""",
    """CREATE INDEX ix_artifacts_workspace_id ON artifacts (workspace_id)""",
    """CREATE TABLE source_tables (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	dataset_version_id VARCHAR(64) NOT NULL,
	artifact_id VARCHAR(64) NOT NULL,
	sheet VARCHAR(255) NOT NULL,
	row_count INTEGER NOT NULL,
	parsed_contract JSONB NOT NULL,
	profile JSONB NOT NULL,
	active_mapping_id VARCHAR(64),
	PRIMARY KEY (id),
	UNIQUE (dataset_version_id, sheet),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(dataset_version_id) REFERENCES dataset_versions (id),
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id)
)""",
    """CREATE INDEX ix_source_tables_workspace_id ON source_tables (workspace_id)""",
    """CREATE TABLE mapping_revisions (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	source_table_id VARCHAR(64) NOT NULL,
	schema_id VARCHAR(64) NOT NULL,
	revision INTEGER NOT NULL,
	status VARCHAR(40) NOT NULL,
	signature VARCHAR(64) NOT NULL,
	business_scope VARCHAR(200) NOT NULL,
	proposal JSONB NOT NULL,
	decision JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source_table_id, revision),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(source_table_id) REFERENCES source_tables (id),
	FOREIGN KEY(schema_id) REFERENCES schema_definitions (id)
)""",
    """CREATE INDEX ix_mapping_revisions_signature ON mapping_revisions (signature)""",
    """CREATE INDEX ix_mapping_revisions_workspace_id ON mapping_revisions (workspace_id)""",
    """CREATE TABLE canonical_datasets (
	id VARCHAR(64) NOT NULL,
	workspace_id VARCHAR(64) NOT NULL,
	source_table_id VARCHAR(64) NOT NULL,
	mapping_id VARCHAR(64) NOT NULL,
	normalization_revision VARCHAR(60) NOT NULL,
	contract JSONB NOT NULL,
	stale BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (mapping_id, normalization_revision),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
	FOREIGN KEY(source_table_id) REFERENCES source_tables (id),
	FOREIGN KEY(mapping_id) REFERENCES mapping_revisions (id)
)""",
    """CREATE INDEX ix_canonical_datasets_workspace_id ON canonical_datasets (workspace_id)""",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade disabled; restore a verified scoped backup instead")
