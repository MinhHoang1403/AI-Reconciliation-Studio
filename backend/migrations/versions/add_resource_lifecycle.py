"""Add reversible lifecycle markers without removing metadata or artifact references."""

import sqlalchemy as sa
from alembic import op

revision = "add_resource_lifecycle"
down_revision = "create_agent_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("projects", "datasets"):
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(
            table, sa.Column("lifecycle_version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("projects", "datasets"):
        if connection.execute(
            sa.text(
                f"SELECT 1 FROM {table} "
                "WHERE archived_at IS NOT NULL OR deleted_at IS NOT NULL LIMIT 1"
            )
        ).first():
            raise RuntimeError("Restore retained resources before removing lifecycle support.")
    for table in ("datasets", "projects"):
        op.drop_column(table, "lifecycle_version")
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "archived_at")
