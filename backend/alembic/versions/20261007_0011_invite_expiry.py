"""Expire role-based workspace invite codes."""

from alembic import op
import sqlalchemy as sa


revision = "20261007_0011"
down_revision = "20261006_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institute_invites", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("institute_invites", "expires_at")
