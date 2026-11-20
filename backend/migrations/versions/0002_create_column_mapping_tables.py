"""Thêm ánh xạ cột, bộ nhớ ánh xạ và nhật ký gọi AI.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dataset_tables") as table:
        table.add_column(sa.Column("table_kind", sa.String(32), nullable=True))
        table.add_column(sa.Column("mapping_status", sa.String(16), nullable=False,
                                   server_default="NONE"))
        table.add_column(sa.Column("mapping_ai_state", sa.String(16), nullable=True))
        table.add_column(sa.Column("mapping_ai_message", sa.Text(), nullable=True))
    with op.batch_alter_table("dataset_tables") as table:
        table.alter_column("mapping_status", server_default=None)

    op.create_table(
        "column_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("table_id", sa.Uuid(), sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("field_key", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("candidates", sa.JSON(), nullable=False),
    )
    op.create_index("ix_column_mappings_table_id", "column_mappings", ["table_id"])
    op.create_table(
        "mapping_memory",
        sa.Column("signature", sa.String(64), primary_key=True),
        sa.Column("table_kind", sa.String(32), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_calls")
    op.drop_table("mapping_memory")
    op.drop_index("ix_column_mappings_table_id", table_name="column_mappings")
    op.drop_table("column_mappings")
    with op.batch_alter_table("dataset_tables") as table:
        table.drop_column("mapping_ai_message")
        table.drop_column("mapping_ai_state")
        table.drop_column("mapping_status")
        table.drop_column("table_kind")
