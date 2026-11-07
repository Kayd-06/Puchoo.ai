"""Durable memory suppression and relational-authority marker (F11/F12)."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_0017"
down_revision = "20261016_0016"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "persistence_markers" not in tables:
        op.create_table("persistence_markers", sa.Column("key", sa.String(80), primary_key=True))
    if "memory_generations" not in tables:
        op.create_table("memory_generations", sa.Column("tenant_id", sa.String(36), primary_key=True),
                        sa.Column("workspace_id", sa.String(100), primary_key=True),
                        sa.Column("generation", sa.Integer(), nullable=False))
    if "memory_deletions" not in tables:
        op.create_table("memory_deletions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("workspace_id", sa.String(100), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("record_id", sa.String(120), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("memory_deletions")}
    if "ix_memory_deletion_scope" not in indexes:
        op.create_index("ix_memory_deletion_scope", "memory_deletions", ["tenant_id", "workspace_id", "record_id", "generation"])
    if "ix_memory_deletion_due" not in indexes:
        op.create_index("ix_memory_deletion_due", "memory_deletions", ["completed", "next_attempt_at"])
    # Existing tenant state is authoritative, even if every workspace was deleted.
    authoritative = bind.execute(sa.text("SELECT COUNT(*) FROM tenants")).scalar()
    if authoritative and not bind.execute(sa.text("SELECT COUNT(*) FROM persistence_markers WHERE key='relational-authority-v1'")).scalar():
        bind.execute(sa.text("INSERT INTO persistence_markers (key) VALUES ('relational-authority-v1')"))


def downgrade():
    # Restoring the old code would remove deletion suppression. See deployment warning.
    op.drop_table("memory_deletions")
    op.drop_table("memory_generations")
    op.drop_table("persistence_markers")
