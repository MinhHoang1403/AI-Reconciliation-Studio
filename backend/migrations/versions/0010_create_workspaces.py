"""Phiên làm việc: mỗi phiên có tệp, kỳ, kết quả, cuộc trò chuyện, nhật ký và bộ nhớ ánh xạ riêng.

Dữ liệu đang có được chuyển nguyên vào một phiên đầu tiên, nên sau khi nâng cấp người dùng
vẫn thấy đúng những gì đã làm. Cột `workspace_id` được thêm ở các bảng gốc (bộ dữ liệu, chuỗi
đối soát, cuộc trò chuyện, nhật ký, bộ nhớ ánh xạ); các bảng khác thuộc phiên qua bảng gốc.

Revision ID: 0010
Revises: 0009
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

FIRST_NAME = "Phiên làm việc 1"
OWNED = ("datasets", "recon_chains", "chat_threads", "audit_log")


def upgrade() -> None:
    workspaces = op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    first = uuid.uuid4()
    op.bulk_insert(workspaces, [{"id": first, "name": FIRST_NAME, "domain": "SALES"}])

    sqlite = op.get_bind().dialect.name == "sqlite"
    for name in OWNED:
        with op.batch_alter_table(name) as table:
            table.add_column(sa.Column("workspace_id", sa.Uuid(), nullable=True))
        op.execute(
            sa.table(name, sa.column("workspace_id", sa.Uuid())).update().values(workspace_id=first)
        )
        # SQLite không đổi được tên ràng buộc chưa đặt tên, nên đặt quy ước tên cho bản sao bảng.
        naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"} if sqlite else None
        with op.batch_alter_table(name, naming_convention=naming) as table:
            table.alter_column("workspace_id", existing_type=sa.Uuid(), nullable=False)
            table.create_foreign_key(
                f"fk_{name}_workspace_id", "workspaces", ["workspace_id"], ["id"],
                ondelete="CASCADE",
            )
            table.create_index(f"ix_{name}_workspace_id", ["workspace_id"])
            if name == "datasets":
                # Trùng tệp chỉ tính trong cùng một phiên.
                table.drop_constraint(
                    "uq_datasets_sha256" if sqlite else "datasets_sha256_key", type_="unique"
                )
                table.create_unique_constraint(
                    "uq_datasets_workspace_id_sha256", ["workspace_id", "sha256"]
                )

    # Bộ nhớ ánh xạ đổi khóa chính thành (phiên, chữ ký): dựng lại bảng, chép dữ liệu cũ vào
    # phiên đầu tiên.
    op.rename_table("mapping_memory", "mapping_memory_old")
    op.create_table(
        "mapping_memory",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("signature", sa.String(64), primary_key=True),
        sa.Column("table_kind", sa.String(32), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO mapping_memory (workspace_id, signature, table_kind, mapping, updated_at) "
            "SELECT :first, signature, table_kind, mapping, updated_at FROM mapping_memory_old"
        ).bindparams(sa.bindparam("first", first, type_=sa.Uuid()))
    )
    op.drop_table("mapping_memory_old")


def downgrade() -> None:
    op.rename_table("mapping_memory", "mapping_memory_new")
    op.create_table(
        "mapping_memory",
        sa.Column("signature", sa.String(64), primary_key=True),
        sa.Column("table_kind", sa.String(32), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.drop_table("mapping_memory_new")
    sqlite = op.get_bind().dialect.name == "sqlite"
    for name in reversed(OWNED):
        with op.batch_alter_table(name) as table:
            if name == "datasets":
                table.drop_constraint("uq_datasets_workspace_id_sha256", type_="unique")
                table.create_unique_constraint(
                    "uq_datasets_sha256" if sqlite else "datasets_sha256_key", ["sha256"]
                )
            table.drop_index(f"ix_{name}_workspace_id")
            table.drop_constraint(f"fk_{name}_workspace_id", type_="foreignkey")
            table.drop_column("workspace_id")
    op.drop_table("workspaces")
