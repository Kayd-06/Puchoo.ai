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
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert "image_url" in user_columns
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261016_0016"
    assert {"tenants", "tenant_memberships", "workspace_records", "workspace_guardrails", "workspace_history_records"}.issubset(
        set(inspector.get_table_names())
    )


def test_init_db_refuses_to_adopt_unversioned_schema(tmp_path):
    """If tables exist but alembic_version is missing, startup fails to prevent data loss."""
    database.configure_database("sqlite:///" + (tmp_path / "unversioned.db").as_posix())

    with database.engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError) as exc:
        database.init_db()

    assert "Database has tables but no alembic_version" in str(exc.value)


def test_migration_0015_creates_missing_tables_when_tenants_already_exists(tmp_path):
    """A partial schema (only `tenants`) must still receive the other tenant tables."""

    from alembic import command

    database.configure_database("sqlite:///" + (tmp_path / "partial.db").as_posix())
    database.init_db()
    config = database._alembic_config()
    command.downgrade(config, "20261014_0014")
    with database.engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE tenants (id VARCHAR(36) PRIMARY KEY, owner_user_id VARCHAR(36) NOT NULL UNIQUE, "
            "name VARCHAR(200) NOT NULL, workspace_type VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)"
        ))

    command.upgrade(config, "20261015_0015")

    tables = set(inspect(database.engine).get_table_names())
    assert {"tenant_memberships", "workspace_records", "workspace_guardrails", "workspace_history_records"} <= tables


def test_migration_0015_is_reversible_and_sets_created_at_server_default(tmp_path):
    from alembic import command

    database.configure_database("sqlite:///" + (tmp_path / "roundtrip.db").as_posix())
    database.init_db()
    config = database._alembic_config()
    command.downgrade(config, "20261014_0014")
    assert "tenants" not in inspect(database.engine).get_table_names()
    command.upgrade(config, "20261015_0015")
    created = {c["name"]: c for c in inspect(database.engine).get_columns("tenants")}["created_at"]
    assert created["default"] is not None
