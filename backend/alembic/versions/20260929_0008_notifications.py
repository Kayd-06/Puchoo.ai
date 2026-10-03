"""Persist account notifications for live in-product delivery."""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0008"
down_revision = "20260928_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" not in inspector.get_table_names():
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("body", sa.String(length=500), nullable=False),
            sa.Column("resource_id", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        existing_indexes: set[str] = set()
    else:
        # Development instances may have been initialized from ORM metadata
        # before this Alembic revision is introduced. Do not fail their upgrade.
        existing_indexes = {index["name"] for index in inspector.get_indexes("notifications")}

    for name, columns in (
        ("ix_notifications_user_id", ["user_id"]),
        ("ix_notifications_created_at", ["created_at"]),
        ("ix_notifications_read_at", ["read_at"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "notifications", columns)


def downgrade() -> None:
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
