"""Remove login recovery codes.

Revision ID: 20261008_0012
Revises: 20261007_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0012"
down_revision = "20261007_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recovery_codes" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("recovery_codes")}
    if "ix_recovery_codes_user_id" in indexes:
        op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")


def downgrade() -> None:
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])
