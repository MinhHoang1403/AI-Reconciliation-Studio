"""Hội thoại riêng theo actor/project; additive, không đổi dữ liệu/runs đã có."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "create_conversations"
down_revision = "create_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("workspace_id", "project_id", "actor_id"):
        op.create_index(f"ix_conversations_{column}", "conversations", [column])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(64), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("answer", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "role"),
    )
    for column in ("conversation_id", "job_id"):
        op.create_index(f"ix_conversation_messages_{column}", "conversation_messages", [column])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM conversations")):
        raise RuntimeError("Refuse to drop persisted conversations; use compatible code rollback.")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
