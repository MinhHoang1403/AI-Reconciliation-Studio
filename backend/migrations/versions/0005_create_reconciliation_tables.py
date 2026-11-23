"""Thêm lần đối soát, kết quả đối soát (kèm trạng thái ngoại lệ) và nhật ký kiểm toán.

Revision ID: 0005
Revises: 0004
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _fk(name: str, target: str, nullable: bool) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable)


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "recon_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("left_table_id", "dataset_tables.id", False),
        _fk("right_table_id", "dataset_tables.id", False),
        _fk("left_version_id", "clean_versions.id", True),
        _fk("right_version_id", "clean_versions.id", True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("verification", sa.JSON(), nullable=True),
        _created_at(),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recon_runs_left_table_id", "recon_runs", ["left_table_id"])
    op.create_index("ix_recon_runs_right_table_id", "recon_runs", ["right_table_id"])

    op.create_table(
        "match_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("run_id", "recon_runs.id", False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("left_refs", sa.JSON(), nullable=False),
        sa.Column("right_refs", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("amount_left", sa.Numeric(20, 2), nullable=True),
        sa.Column("amount_right", sa.Numeric(20, 2), nullable=True),
        sa.Column("exception_status", sa.String(16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_match_results_run_id", "match_results", ["run_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _created_at(),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False),
        sa.Column("object_label", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_match_results_run_id", table_name="match_results")
    op.drop_table("match_results")
    op.drop_index("ix_recon_runs_right_table_id", table_name="recon_runs")
    op.drop_index("ix_recon_runs_left_table_id", table_name="recon_runs")
    op.drop_table("recon_runs")
