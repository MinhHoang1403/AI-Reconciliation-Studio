"""Index scoped purge lookups and bind receipt retries to the original confirmation."""

import sqlalchemy as sa
from alembic import op

revision = "index_purge_scope"
down_revision = "add_purge_receipts"
branch_labels = None
depends_on = None

SCOPE_INDEXES = (
    ("sessions", "workspace_id"),
    ("artifacts", "dataset_version_id"),
    ("source_tables", "artifact_id"),
    ("mapping_revisions", "schema_id"),
    ("canonical_datasets", "source_table_id"),
    ("jobs", "project_id"),
    ("audit_events", "workspace_id"),
    ("audit_events", "resource_id"),
    ("ai_traces", "job_id"),
    ("run_exports", "storage_key"),
)


def upgrade() -> None:
    for table, column in SCOPE_INDEXES:
        op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_purge_receipts_pending",
        "purge_receipts",
        ["created_at"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )
    op.add_column("purge_receipts", sa.Column("confirmation_hash", sa.String(64)))


def downgrade() -> None:
    op.drop_column("purge_receipts", "confirmation_hash")
    op.drop_index("ix_purge_receipts_pending", table_name="purge_receipts")
    for table, column in reversed(SCOPE_INDEXES):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
