"""Add password-proven login challenges.

Revision ID: 20261006_0010
Revises: 20260930_0009
"""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0010"
down_revision = "20260930_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "login_challenges" not in inspector.get_table_names():
        op.create_table(
            "login_challenges",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("resend_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = {index["name"] for index in inspector.get_indexes("login_challenges")}
    if "ix_login_challenges_user_id" not in existing_indexes:
        op.create_index("ix_login_challenges_user_id", "login_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_login_challenges_user_id", table_name="login_challenges")
    op.drop_table("login_challenges")
