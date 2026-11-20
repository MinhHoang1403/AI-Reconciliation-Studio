"""Thêm phiên bản bộ dữ liệu sạch, sửa ô, quyết định dòng và gợi ý sửa của AI.

Revision ID: 0003
Revises: 0002
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dataset_tables") as table:
        table.add_column(
            sa.Column("clean_status", sa.String(16), nullable=False, server_default="NONE")
        )
        table.add_column(sa.Column("clean_options", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("dataset_tables") as table:
        table.alter_column("clean_status", server_default=None)
        table.alter_column("clean_options", server_default=None)

    op.create_table(
        "clean_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "table_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parquet_path", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_clean_versions_table_id", "clean_versions", ["table_id"])

    # Ba bảng cùng khung: mã, bảng dữ liệu, số dòng gốc, rồi các cột riêng.
    tables: list[tuple[str, list[sa.Column[Any]]]] = [
        (
            "cell_corrections",
            [
                sa.Column("field_key", sa.String(64), nullable=False),
                sa.Column("value", sa.Text(), nullable=False),
                sa.Column("source", sa.String(16), nullable=False),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            ],
        ),
        (
            "row_decisions",
            [
                sa.Column("decision", sa.String(16), nullable=False),
                sa.Column("reason", sa.String(64), nullable=False),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            ],
        ),
        (
            "ai_cell_suggestions",
            [
                sa.Column("field_key", sa.String(64), nullable=False),
                sa.Column("raw_value", sa.Text(), nullable=False),
                sa.Column("suggested_value", sa.Text(), nullable=True),
                sa.Column("confidence", sa.Float(), nullable=False),
                sa.Column("reason", sa.Text(), nullable=False),
            ],
        ),
    ]
    for name, columns in tables:
        unique = ["table_id", "row_ref"] + (["field_key"] if name != "row_decisions" else [])
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "table_id",
                sa.Uuid(),
                sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("row_ref", sa.Integer(), nullable=False),
            *columns,
            sa.UniqueConstraint(*unique),
        )
        op.create_index(f"ix_{name}_table_id", name, ["table_id"])


def downgrade() -> None:
    for name in ("ai_cell_suggestions", "row_decisions", "cell_corrections"):
        op.drop_index(f"ix_{name}_table_id", table_name=name)
        op.drop_table(name)
    op.drop_index("ix_clean_versions_table_id", table_name="clean_versions")
    op.drop_table("clean_versions")
    with op.batch_alter_table("dataset_tables") as table:
        table.drop_column("clean_options")
        table.drop_column("clean_status")
