"""Chặn trùng số phiên bản bộ sạch; ghi ô gốc của mỗi lần sửa ô.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("clean_versions") as table:
        table.create_unique_constraint(
            "uq_clean_versions_table_id_version", ["table_id", "version"]
        )
    with op.batch_alter_table("cell_corrections") as table:
        table.add_column(sa.Column("source_column", sa.String(255), nullable=True))
        table.add_column(sa.Column("original_value", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("cell_corrections") as table:
        table.drop_column("original_value")
        table.drop_column("source_column")
    with op.batch_alter_table("clean_versions") as table:
        table.drop_constraint("uq_clean_versions_table_id_version", type_="unique")
