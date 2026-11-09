"""Durable receipts for irreversible deletion and filesystem recovery."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "add_purge_receipts"
down_revision = "add_resource_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purge_receipts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("files", JSONB(), nullable=False),
        sa.Column("counts", JSONB(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_purge_receipts_workspace_id", "purge_receipts", ["workspace_id"])


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM purge_receipts LIMIT 1")).first():
        raise RuntimeError("Preserve purge receipts before removing irreversible deletion support.")
    op.drop_table("purge_receipts")
