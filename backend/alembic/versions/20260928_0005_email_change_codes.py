"""Add OTP records for verified email changes."""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0005"
down_revision = "20260925_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_change_codes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_change_codes_user_id", "email_change_codes", ["user_id"])
    op.create_index("ix_email_change_codes_new_email", "email_change_codes", ["new_email"])


def downgrade() -> None:
    op.drop_index("ix_email_change_codes_new_email", table_name="email_change_codes")
    op.drop_index("ix_email_change_codes_user_id", table_name="email_change_codes")
    op.drop_table("email_change_codes")
