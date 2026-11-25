"""Lời nhận xét AI của báo cáo một kỳ, lưu trên lần đối soát chuỗi.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recon_chains") as table:
        table.add_column(sa.Column("report_comment", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recon_chains") as table:
        table.drop_column("report_comment")
