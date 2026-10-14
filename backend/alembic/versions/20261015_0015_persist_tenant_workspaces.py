"""Persist tenant memberships and workspace metadata."""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "20261015_0015"
down_revision = "20261014_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "tenants" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("workspace_type", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_owner_user_id", "tenants", ["owner_user_id"])
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])
    op.create_table(
        "workspace_records",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("availability", sa.String(30), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspace_records_tenant_id", "workspace_records", ["tenant_id"])
    op.create_table(
        "workspace_guardrails",
        sa.Column("workspace_id", sa.String(100), sa.ForeignKey("workspace_records.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("settings_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "workspace_history_records",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("workspace_id", sa.String(100), sa.ForeignKey("workspace_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_workspace_history_records_workspace_id", "workspace_history_records", ["workspace_id"])

    users = bind.execute(sa.text(
        "SELECT id, workspace_owner_id, institute_owner_id, workspace_role, "
        "workspace_name, institute_name, workspace_type FROM users"
    )).mappings().all()
    by_id = {row["id"]: row for row in users}
    tenant_ids = {row["workspace_owner_id"] or row["institute_owner_id"] or row["id"] for row in users}
    for tenant_id in tenant_ids:
        owner = by_id.get(tenant_id)
        if owner is None:
            continue
        bind.execute(sa.text(
            "INSERT INTO tenants (id, owner_user_id, name, workspace_type, created_at) "
            "VALUES (:id, :owner, :name, :kind, CURRENT_TIMESTAMP)"
        ), {
            "id": tenant_id,
            "owner": tenant_id,
            "name": owner["workspace_name"] or owner["institute_name"] or "Workspace",
            "kind": owner["workspace_type"],
        })
    for user in users:
        tenant_id = user["workspace_owner_id"] or user["institute_owner_id"] or user["id"]
        if tenant_id not in tenant_ids or tenant_id not in by_id:
            continue
        bind.execute(sa.text(
            "INSERT INTO tenant_memberships (id, tenant_id, user_id, role, created_at) "
            "VALUES (:id, :tenant, :user, :role, CURRENT_TIMESTAMP)"
        ), {
            "id": str(uuid.uuid4()),
            "tenant": tenant_id,
            "user": user["id"],
            "role": "owner" if user["id"] == tenant_id else (user["workspace_role"] or "viewer"),
        })


def downgrade() -> None:
    op.drop_table("workspace_history_records")
    op.drop_table("workspace_guardrails")
    op.drop_table("workspace_records")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
