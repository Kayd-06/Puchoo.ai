"""Add a persisted profile image to user accounts.

Revision ID: 20261014_0014
Revises: 20261009_0013
"""

from alembic import op
import sqlalchemy as sa


revision = "20261014_0014"
down_revision = "20261009_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "image_url" not in columns:
        op.add_column("users", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "image_url" in columns:
        op.drop_column("users", "image_url")
