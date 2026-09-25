"""Create login verification codes.

Revision ID: 20260925_0002
Revises: 20260925_0001
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260925_0002"
down_revision = "20260925_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_codes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_login_codes_user_id", "login_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_login_codes_user_id", table_name="login_codes")
    op.drop_table("login_codes")
