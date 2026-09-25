"""Add institute membership ownership and rotatable invite codes."""

from alembic import op
import sqlalchemy as sa

revision = "20260925_0004"
down_revision = "20260925_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("institute_owner_id", sa.String(length=36), nullable=True))
    op.create_index("ix_users_institute_owner_id", "users", ["institute_owner_id"])
    op.create_table(
        "institute_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_institute_invites_owner_user_id", "institute_invites", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_institute_invites_owner_user_id", table_name="institute_invites")
    op.drop_table("institute_invites")
    op.drop_index("ix_users_institute_owner_id", table_name="users")
    op.drop_column("users", "institute_owner_id")
