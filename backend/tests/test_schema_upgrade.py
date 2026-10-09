"""Database startup upgrades versioned schemas before serving requests."""

import pytest
from sqlalchemy import inspect, text

from backend import database


@pytest.fixture(autouse=True)
def restore_database_configuration():
    """Keep migration tests from leaking their temporary engine to other tests."""

    original_url = database.engine.url.render_as_string(hide_password=False)
    try:
        yield
    finally:
        database.configure_database(original_url)


def test_init_db_upgrades_stale_invite_schema_and_removes_recovery_codes(tmp_path):
    database.configure_database("sqlite:///" + (tmp_path / "stale.db").as_posix())
    database.init_db()

    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE institute_invites DROP COLUMN expires_at"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20261006_0010')"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS recovery_codes (id VARCHAR(36) PRIMARY KEY)"))

    database.init_db()

    inspector = inspect(database.engine)
    invite_columns = {column["name"] for column in inspector.get_columns("institute_invites")}
    assert "expires_at" in invite_columns
    assert "recovery_codes" not in inspector.get_table_names()
    assert "pending_queries" in inspector.get_table_names()
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261009_0013"


def test_init_db_refuses_to_adopt_unversioned_schema(tmp_path):
    """If tables exist but alembic_version is missing, startup fails to prevent data loss."""
    database.configure_database("sqlite:///" + (tmp_path / "unversioned.db").as_posix())

    with database.engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError) as exc:
        database.init_db()

    assert "Database has tables but no alembic_version" in str(exc.value)
