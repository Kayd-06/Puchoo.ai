"""Store generated SQL until the user approves it.

Revision ID: 20261009_0013
Revises: 20261008_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20261009_0013"
down_revision = "20261008_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pending_queries" not in inspector.get_table_names():
        op.create_table(
            "pending_queries",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=64), nullable=False),
            sa.Column("sql", sa.Text(), nullable=False),
            sa.Column("sql_hash", sa.String(length=64), nullable=False),
            sa.Column("limit_clamped", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("context_json", sa.Text(), nullable=False),
            sa.Column("parent_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = {index["name"] for index in inspector.get_indexes("pending_queries")}

    for name, columns in (
        ("ix_pending_queries_user_id", ["user_id"]),
        ("ix_pending_queries_workspace_id", ["workspace_id"]),
        ("ix_pending_queries_expires_at", ["expires_at"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "pending_queries", columns)


def downgrade() -> None:
    op.drop_index("ix_pending_queries_expires_at", table_name="pending_queries")
    op.drop_index("ix_pending_queries_workspace_id", table_name="pending_queries")
    op.drop_index("ix_pending_queries_user_id", table_name="pending_queries")
    op.drop_table("pending_queries")
