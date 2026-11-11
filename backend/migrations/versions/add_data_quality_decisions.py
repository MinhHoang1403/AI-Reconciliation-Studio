"""Keep source adjustments and canonical quality revisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "add_data_quality_decisions"
down_revision = "retain_purged_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("source_tables", "canonical_datasets"):
        op.add_column(
            table, sa.Column("quality_revision", sa.Integer, nullable=False, server_default="0")
        )
    op.drop_constraint(
        "canonical_datasets_mapping_id_normalization_revision_key",
        "canonical_datasets",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_canonical_mapping_algorithm_quality",
        "canonical_datasets",
        ["mapping_id", "normalization_revision", "quality_revision"],
    )
    op.create_table(
        "data_quality_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "source_table_id",
            sa.String(64),
            sa.ForeignKey("source_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(200), nullable=False),
        sa.Column("request", JSONB, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("job_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_table_id", "revision"),
        sa.UniqueConstraint("source_table_id", "actor_id", "request_key"),
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM data_quality_decisions)
             OR EXISTS (SELECT 1 FROM canonical_datasets WHERE quality_revision <> 0) THEN
            RAISE EXCEPTION 'Data quality history requires a compatible release';
          END IF;
        END $$;
    """)
    op.drop_table("data_quality_decisions")
    op.drop_constraint(
        "uq_canonical_mapping_algorithm_quality", "canonical_datasets", type_="unique"
    )
    op.create_unique_constraint(
        "canonical_datasets_mapping_id_normalization_revision_key",
        "canonical_datasets",
        ["mapping_id", "normalization_revision"],
    )
    op.drop_column("canonical_datasets", "quality_revision")
    op.drop_column("source_tables", "quality_revision")
