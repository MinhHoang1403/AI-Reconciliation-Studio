"""Lựa chọn của người dùng có thêm loại: ghép (MATCH) hoặc gỡ ghép (UNMATCH).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recon_choices") as table:
        table.add_column(
            sa.Column("action", sa.String(16), nullable=False, server_default="MATCH")
        )


def downgrade() -> None:
    with op.batch_alter_table("recon_choices") as table:
        table.drop_column("action")
