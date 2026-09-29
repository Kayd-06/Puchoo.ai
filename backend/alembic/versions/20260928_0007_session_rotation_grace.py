"""Allow a brief overlap while a rotated browser session cookie propagates."""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0007"
down_revision = "20260928_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("previous_token_hash", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("previous_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sessions_previous_token_hash", "sessions", ["previous_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_sessions_previous_token_hash", table_name="sessions")
    op.drop_column("sessions", "previous_token_expires_at")
    op.drop_column("sessions", "previous_token_hash")
