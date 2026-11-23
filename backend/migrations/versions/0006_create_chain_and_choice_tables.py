"""Chuỗi đối soát ba bên, lựa chọn cho ca mơ hồ, dòng chờ tiền về mang sang kỳ sau.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recon_chains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("table_ids", sa.JSON(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "recon_choices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "left_table_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "right_table_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("left_refs", sa.JSON(), nullable=False),
        sa.Column("right_refs", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_recon_choices_left_table_id", "recon_choices", ["left_table_id"])
    op.create_index("ix_recon_choices_right_table_id", "recon_choices", ["right_table_id"])
    with op.batch_alter_table("recon_runs") as table:
        table.add_column(sa.Column("chain_id", sa.Uuid(), nullable=True))
        table.add_column(sa.Column("carried", sa.JSON(), nullable=True))
        table.create_foreign_key(
            "fk_recon_runs_chain_id", "recon_chains", ["chain_id"], ["id"], ondelete="CASCADE"
        )
        table.create_index("ix_recon_runs_chain_id", ["chain_id"])
    with op.batch_alter_table("match_results") as table:
        table.add_column(sa.Column("carried_left", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("match_results") as table:
        table.drop_column("carried_left")
    with op.batch_alter_table("recon_runs") as table:
        table.drop_index("ix_recon_runs_chain_id")
        table.drop_constraint("fk_recon_runs_chain_id", type_="foreignkey")
        table.drop_column("carried")
        table.drop_column("chain_id")
    op.drop_index("ix_recon_choices_right_table_id", table_name="recon_choices")
    op.drop_index("ix_recon_choices_left_table_id", table_name="recon_choices")
    op.drop_table("recon_choices")
    op.drop_table("recon_chains")
