"""Persist tenant memberships and workspace metadata."""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "20261015_0015"
down_revision = "20261014_0014"
branch_labels = None
depends_on = None


def _has_index(bind, table: str, name: str) -> bool:
    return any(index["name"] == name for index in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    # Check each table separately: a partially created schema (for example a
    # dev database touched by create_all) must still get the missing tables.
    tables = set(sa.inspect(bind).get_table_names())
    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("workspace_type", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if not _has_index(bind, "tenants", "ix_tenants_owner_user_id"):
        op.create_index("ix_tenants_owner_user_id", "tenants", ["owner_user_id"])
    if "tenant_memberships" not in tables:
        op.create_table(
            "tenant_memberships",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        )
    if not _has_index(bind, "tenant_memberships", "ix_tenant_memberships_tenant_id"):
        op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    if not _has_index(bind, "tenant_memberships", "ix_tenant_memberships_user_id"):
        op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])
    if "workspace_records" not in tables:
        op.create_table(
            "workspace_records",
            sa.Column("id", sa.String(100), primary_key=True),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("source_type", sa.String(30), nullable=False),
            sa.Column("source_ref", sa.Text(), nullable=True),
            sa.Column("availability", sa.String(30), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if not _has_index(bind, "workspace_records", "ix_workspace_records_tenant_id"):
        op.create_index("ix_workspace_records_tenant_id", "workspace_records", ["tenant_id"])
    if "workspace_guardrails" not in tables:
        op.create_table(
            "workspace_guardrails",
            sa.Column("workspace_id", sa.String(100), sa.ForeignKey("workspace_records.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("settings_json", sa.Text(), nullable=False),
        )
    if "workspace_history_records" not in tables:
        op.create_table(
            "workspace_history_records",
            sa.Column("id", sa.String(100), primary_key=True),
            sa.Column("workspace_id", sa.String(100), sa.ForeignKey("workspace_records.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
        )
    if not _has_index(bind, "workspace_history_records", "ix_workspace_history_records_workspace_id"):
        op.create_index("ix_workspace_history_records_workspace_id", "workspace_history_records", ["workspace_id"])

    # Backfill is idempotent: only missing tenants and memberships are added.
    users = bind.execute(sa.text(
        "SELECT id, workspace_owner_id, institute_owner_id, workspace_role, "
        "workspace_name, institute_name, workspace_type FROM users"
    )).mappings().all()
    by_id = {row["id"]: row for row in users}
    existing_tenants = set(bind.execute(sa.text("SELECT id FROM tenants")).scalars().all())
    existing_members = set(bind.execute(sa.text("SELECT user_id FROM tenant_memberships")).scalars().all())
    tenant_ids = {row["workspace_owner_id"] or row["institute_owner_id"] or row["id"] for row in users}
    for tenant_id in tenant_ids:
        owner = by_id.get(tenant_id)
        if owner is None or tenant_id in existing_tenants:
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
        if tenant_id not in by_id or user["id"] in existing_members:
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
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (
        "workspace_history_records",
        "workspace_guardrails",
        "workspace_records",
        "tenant_memberships",
        "tenants",
    ):
        if table in tables:
            op.drop_table(table)
