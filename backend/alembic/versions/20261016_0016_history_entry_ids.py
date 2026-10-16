"""Give workspace history rows a surrogate UUID key.

History entry ids only have to be unique within one workspace, so the old
table-wide primary key on the payload id could collide across workspaces.

Revision ID: 20261016_0016
Revises: 20261015_0015
"""

import uuid

from alembic import op
import sqlalchemy as sa


revision = "20261016_0016"
down_revision = "20261015_0015"
branch_labels = None
depends_on = None

INDEX = "ix_workspace_history_records_workspace_id"


def _create(name: str, *, with_entry_id: bool) -> None:
    columns = [
        sa.Column("id", sa.String(36 if with_entry_id else 100), primary_key=True),
        sa.Column("workspace_id", sa.String(100), sa.ForeignKey("workspace_records.id", ondelete="CASCADE"), nullable=False),
    ]
    if with_entry_id:
        columns.append(sa.Column("entry_id", sa.String(100), nullable=False))
    columns += [
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    ]
    args = [sa.UniqueConstraint("workspace_id", "entry_id", name="uq_workspace_history_entry")] if with_entry_id else []
    op.create_table(name, *columns, *args)


def _rows(bind):
    return bind.execute(sa.text(
        "SELECT * FROM workspace_history_records ORDER BY workspace_id, position"
    )).mappings().all()


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("workspace_history_records")}
    if "entry_id" in columns:
        return
    rows = _rows(bind)
    _create("workspace_history_records_new", with_entry_id=True)
    for row in rows:
        bind.execute(sa.text(
            "INSERT INTO workspace_history_records_new (id, workspace_id, entry_id, position, payload_json) "
            "VALUES (:id, :workspace_id, :entry_id, :position, :payload_json)"
        ), {**row, "id": str(uuid.uuid4()), "entry_id": row["id"]})
    op.drop_table("workspace_history_records")
    op.rename_table("workspace_history_records_new", "workspace_history_records")
    op.create_index(INDEX, "workspace_history_records", ["workspace_id"])


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("workspace_history_records")}
    if "entry_id" not in columns:
        return
    rows = _rows(bind)
    _create("workspace_history_records_old", with_entry_id=False)
    used: set[str] = set()
    for row in rows:
        # The old schema needs table-wide unique ids; fall back to the
        # surrogate id when two workspaces share an entry id.
        legacy_id = row["entry_id"] if row["entry_id"] not in used else row["id"]
        used.add(legacy_id)
        bind.execute(sa.text(
            "INSERT INTO workspace_history_records_old (id, workspace_id, position, payload_json) "
            "VALUES (:id, :workspace_id, :position, :payload_json)"
        ), {"id": legacy_id, "workspace_id": row["workspace_id"], "position": row["position"], "payload_json": row["payload_json"]})
    op.drop_table("workspace_history_records")
    op.rename_table("workspace_history_records_old", "workspace_history_records")
    op.create_index(INDEX, "workspace_history_records", ["workspace_id"])
