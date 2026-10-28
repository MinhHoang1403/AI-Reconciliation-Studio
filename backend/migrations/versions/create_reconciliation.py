"""Add scoped approved rules, immutable runs and review/export metadata.

DDL is an explicit snapshot. No historical columns, canonical identifiers or
artifact bytes change; downgrade refuses to remove persisted reconciliation data.
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "create_reconciliation"
down_revision = "create_data_foundation"
branch_labels = None
depends_on = None


def scoped() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
    ]


def timestamp() -> sa.Column[Any]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "reconciliation_plans",
        *scoped(),
        sa.Column("proposal", JSONB, nullable=False),
        sa.Column("origin", sa.String(30), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        timestamp(),
    )
    op.create_table(
        "reconciliation_contracts",
        *scoped(),
        sa.Column(
            "plan_id",
            sa.String(64),
            sa.ForeignKey("reconciliation_plans.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("source_signatures", JSONB, nullable=False),
        timestamp(),
    )
    op.create_table(
        "reconciliation_runs",
        *scoped(),
        sa.Column(
            "contract_id",
            sa.String(64),
            sa.ForeignKey("reconciliation_contracts.id"),
            nullable=False,
        ),
        sa.Column("input_signature", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("engine_revision", sa.String(80), nullable=False),
        sa.Column("source_refs", JSONB, nullable=False),
        sa.Column("checks", JSONB, nullable=False),
        sa.Column("result_metadata", JSONB, nullable=False),
        sa.Column("metric_snapshot", JSONB, nullable=True),
        sa.Column("result_key", sa.String(500), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=True),
        timestamp(),
        sa.UniqueConstraint("project_id", "input_signature"),
    )
    op.create_table(
        "exception_cases",
        *scoped(),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("reconciliation_runs.id"), nullable=False),
        sa.Column("match_group_id", sa.String(64), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("workflow_state", sa.String(40), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "match_group_id", "type"),
    )
    op.create_table(
        "run_exports",
        *scoped(),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("reconciliation_runs.id"), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("revision", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.UniqueConstraint("run_id", "format", "revision"),
    )
    for table in (
        "reconciliation_plans",
        "reconciliation_contracts",
        "reconciliation_runs",
        "exception_cases",
        "run_exports",
    ):
        for field in ("workspace_id", "project_id"):
            op.create_index(f"ix_{table}_{field}", table, [field])
    op.create_index("ix_exception_cases_run_id", "exception_cases", ["run_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; preserve historical runs and approvals")
