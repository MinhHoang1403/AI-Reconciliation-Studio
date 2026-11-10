"""Retain redacted provider reservations after the workspace is deleted."""

import sqlalchemy as sa
from alembic import op

revision = "retain_purged_reservations"
down_revision = "index_purge_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("audit_events", "workspace_id", existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    # The prior schema cannot represent detached reservations. Keep the ledger intact.
    op.alter_column("audit_events", "workspace_id", existing_type=sa.String(64), nullable=False)
