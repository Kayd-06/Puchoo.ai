"""Add tenant ownership and role-bearing workspace invitations.

Existing institute accounts retain access: their legacy owner id is copied into
the new tenant owner column and existing owners become workspace owners.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0006"
down_revision = "20260928_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("workspace_name", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("workspace_owner_id", sa.String(length=36), nullable=True))
    op.add_column("users", sa.Column("workspace_role", sa.String(length=20), nullable=False, server_default="owner"))
    op.create_index("ix_users_workspace_owner_id", "users", ["workspace_owner_id"])
    op.add_column("institute_invites", sa.Column("workspace_type", sa.String(length=20), nullable=False, server_default="institution"))
    op.add_column("institute_invites", sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"))

    op.execute("UPDATE users SET workspace_name = institute_name WHERE workspace_name IS NULL")
    op.execute("UPDATE users SET workspace_owner_id = institute_owner_id WHERE institute_owner_id IS NOT NULL")
    op.execute("UPDATE users SET workspace_type = 'institution' WHERE workspace_type = 'institute'")
    op.execute("UPDATE users SET workspace_role = 'viewer' WHERE workspace_owner_id IS NOT NULL")


def downgrade() -> None:
    op.drop_column("institute_invites", "role")
    op.drop_column("institute_invites", "workspace_type")
    op.drop_index("ix_users_workspace_owner_id", table_name="users")
    op.drop_column("users", "workspace_role")
    op.drop_column("users", "workspace_owner_id")
    op.drop_column("users", "workspace_name")
