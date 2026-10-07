"""Database startup upgrades versioned schemas before serving requests."""

from sqlalchemy import inspect, text

from backend import database


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
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261008_0012"
