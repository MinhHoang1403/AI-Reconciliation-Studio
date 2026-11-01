"""Workflow/review JSONB hữu hạn; tái sử dụng queue, không đổi dữ liệu lịch sử."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "create_agent_workflows"
down_revision = "create_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_workflows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.String(64), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column(
            "parent_job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False, unique=True
        ),
        sa.Column("waiting_job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("goal", sa.String(2000), nullable=False),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("detail", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "workspace_id",
        "project_id",
        "conversation_id",
        "actor_id",
        "waiting_job_id",
        "state",
    ):
        op.create_index(f"ix_agent_workflows_{column}", "agent_workflows", [column])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM agent_workflows")):
        raise RuntimeError("Refuse to drop persisted workflows or review decisions.")
    op.drop_table("agent_workflows")
