"""Database-level read-only limits: read-only sessions, timeouts and row caps.

SQLite tests always run. PostgreSQL and MySQL/MariaDB tests run when
``PUCHOO_TEST_POSTGRES_URL`` / ``PUCHOO_TEST_MYSQL_URL`` point at a disposable
test database (they create and drop a ``puchoo_ro_probe`` table).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from apps.core.executor import (
    QueryTimeoutError,
    ReadOnlyExecutor,
    max_result_rows,
    statement_timeout_seconds,
)
from apps.core.guardrails import GuardedSQL, SQLGuardrailError


class _PermissiveGuard:
    """Simulates a guardrail bypass so the database layer is tested alone."""

    def __init__(self, sql: str, limit: int = 1_000_000) -> None:
        self.guarded = GuardedSQL(sql=sql, limit=limit, limit_clamped=False)

    def validate_and_clamp(self, _sql):
        return self.guarded

    def validate_exact(self, _sql):
        return self.guarded


@pytest.fixture
def sqlite_source(tmp_path) -> Path:
    # Spaces in the path must survive the file: URI used for mode=ro.
    folder = tmp_path / "data dir"
    folder.mkdir()
    path = folder / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE metrics (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)")
    connection.executemany("INSERT INTO metrics (amount) VALUES (?)", [(value,) for value in range(10)])
    connection.commit()
    connection.close()
    return path


def _row_count(path: Path) -> int:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    finally:
        connection.close()


def test_env_ceilings_have_safe_defaults(monkeypatch):
    monkeypatch.delenv("QUERY_STATEMENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("QUERY_MAX_ROWS", raising=False)
    assert statement_timeout_seconds() == 15
    assert max_result_rows() == 5000
    monkeypatch.setenv("QUERY_STATEMENT_TIMEOUT_SECONDS", "not-a-number")
    monkeypatch.setenv("QUERY_MAX_ROWS", "-4")
    assert statement_timeout_seconds() == 15
    assert max_result_rows() == 1


def test_workspace_settings_cannot_exceed_server_ceilings(monkeypatch, sqlite_source):
    monkeypatch.setenv("QUERY_STATEMENT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("QUERY_MAX_ROWS", "4")
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=10_000, timeout_seconds=300)
    assert executor.timeout_seconds == 5
    assert executor.row_cap == 4
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=2, timeout_seconds=1)
    assert executor.timeout_seconds == 1
    assert executor.row_cap == 2


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM metrics",
        "UPDATE metrics SET amount = 0",
        "INSERT INTO metrics (amount) VALUES (1)",
        "DROP TABLE metrics",
        "CREATE TABLE stolen AS SELECT * FROM metrics",
        "PRAGMA user_version = 7",
    ],
)
def test_sqlite_source_is_opened_read_only_even_without_query_only(sqlite_source, statement):
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}")
    # Not even calling _begin_read_only: mode=ro alone must refuse writes.
    with executor.engine.connect() as connection:
        with pytest.raises(SQLAlchemyError, match="readonly|read-only|read only"):
            connection.exec_driver_sql(statement)
    executor.engine.dispose()
    assert _row_count(sqlite_source) == 10


def test_sqlite_query_only_cannot_be_turned_back_on_write(sqlite_source):
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}")
    executor.guardrails = _PermissiveGuard("DELETE FROM metrics")
    with pytest.raises(Exception):
        executor.execute("DELETE FROM metrics")
    assert _row_count(sqlite_source) == 10


def test_write_sql_is_rejected_before_execution(sqlite_source):
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}")
    with pytest.raises(SQLGuardrailError):
        executor.execute("DELETE FROM metrics")
    assert _row_count(sqlite_source) == 10


def test_sqlite_long_query_is_interrupted(monkeypatch, sqlite_source):
    monkeypatch.setenv("QUERY_STATEMENT_TIMEOUT_SECONDS", "1")
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", timeout_seconds=30)
    started = perf_counter()
    with pytest.raises(QueryTimeoutError, match="longer than 1 seconds"):
        executor.execute(
            "WITH RECURSIVE counter AS (SELECT 1 AS x UNION ALL SELECT x + 1 FROM counter) SELECT COUNT(*) FROM counter"
        )
    assert perf_counter() - started < 10


def test_row_cap_clamps_and_flags_truncation(monkeypatch, sqlite_source):
    monkeypatch.setenv("QUERY_MAX_ROWS", "3")
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=500)
    result = executor.execute("SELECT id FROM metrics ORDER BY id")
    assert result.row_count == 3
    assert result.truncated is True
    assert result.row_cap == 3
    assert result.sql.endswith("LIMIT 3")


def test_small_user_limit_is_not_reported_as_truncated(sqlite_source):
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=500)
    result = executor.execute("SELECT id FROM metrics ORDER BY id LIMIT 2")
    assert result.row_count == 2
    assert result.truncated is False
    full = executor.execute("SELECT id FROM metrics")
    assert full.row_count == 10 and full.truncated is False


def test_fetchmany_caps_rows_even_if_the_limit_is_missing(monkeypatch, sqlite_source):
    monkeypatch.setenv("QUERY_MAX_ROWS", "4")
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}")
    executor.guardrails = _PermissiveGuard("SELECT id FROM metrics")
    result = executor.execute("SELECT id FROM metrics")
    assert result.row_count == 4
    assert result.truncated is True


def test_exact_mode_refuses_sql_that_is_not_already_guarded(sqlite_source):
    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=5)
    with pytest.raises(SQLGuardrailError, match="no longer matches"):
        executor.execute("SELECT id FROM metrics", exact=True)
    approved = executor.prepare("SELECT id FROM metrics").sql
    result = executor.execute(approved, exact=True, limit_clamped=True)
    assert result.sql == approved
    assert result.truncated is True


def test_sql_runs_verbatim_with_colons_and_percent_signs(sqlite_source):
    """``:name`` and ``%`` inside literals must not become bind parameters."""

    executor = ReadOnlyExecutor(f"sqlite:///{sqlite_source}", max_rows=5)
    sql = "SELECT 'at 10:30 :id 50%' AS note, id FROM metrics WHERE amount >= 0 AND 'x' LIKE '%' ORDER BY id"
    planned = executor.validate_query_plan(sql)
    result = executor.execute(planned.sql, exact=True)
    assert result.sql == planned.sql
    assert result.rows[0]["note"] == "at 10:30 :id 50%"


# --- Optional server databases ------------------------------------------------

POSTGRES_URL = os.getenv("PUCHOO_TEST_POSTGRES_URL")
MYSQL_URL = os.getenv("PUCHOO_TEST_MYSQL_URL")


@pytest.fixture
def server_table(request):
    url = request.param
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS puchoo_ro_probe")
        connection.exec_driver_sql("CREATE TABLE puchoo_ro_probe (id INTEGER PRIMARY KEY, amount INTEGER)")
        connection.exec_driver_sql(
            "INSERT INTO puchoo_ro_probe (id, amount) VALUES " + ", ".join(f"({i}, {i})" for i in range(10))
        )
    yield url
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS puchoo_ro_probe")
        connection.exec_driver_sql("DROP TABLE IF EXISTS puchoo_ro_stolen")
    engine.dispose()


def _server_params():
    params = []
    if POSTGRES_URL:
        params.append(pytest.param(POSTGRES_URL, id="postgresql"))
    if MYSQL_URL:
        params.append(pytest.param(MYSQL_URL, id="mysql"))
    return params or [pytest.param(None, marks=pytest.mark.skip(reason="no server test database configured"))]


def _dialect(url: str) -> str:
    return "postgresql" if url.startswith("postgresql") else "mysql"


def _count(url: str) -> int:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql("SELECT COUNT(*) FROM puchoo_ro_probe").scalar_one()
    finally:
        engine.dispose()


@pytest.mark.parametrize("server_table", _server_params(), indirect=True)
@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM puchoo_ro_probe",
        "UPDATE puchoo_ro_probe SET amount = 0",
        "INSERT INTO puchoo_ro_probe (id, amount) VALUES (99, 99)",
        "CREATE TABLE puchoo_ro_stolen (id INTEGER)",
    ],
)
def test_server_session_is_read_only(server_table, statement):
    url = server_table
    executor = ReadOnlyExecutor(url, dialect=_dialect(url))
    executor.guardrails = _PermissiveGuard(statement)
    with pytest.raises(Exception, match="(?i)read.only|readonly"):
        executor.execute(statement)
    assert _count(url) == 10


@pytest.mark.parametrize("server_table", _server_params(), indirect=True)
def test_server_session_cannot_switch_back_to_read_write(server_table):
    url = server_table
    executor = ReadOnlyExecutor(url, dialect=_dialect(url))
    with executor.engine.connect() as connection:
        executor._begin_read_only(connection, perf_counter())
        with pytest.raises(SQLAlchemyError):
            connection.exec_driver_sql("DELETE FROM puchoo_ro_probe")
    executor.engine.dispose()
    assert _count(url) == 10


@pytest.mark.parametrize("server_table", _server_params(), indirect=True)
def test_server_statement_timeout(monkeypatch, server_table):
    url = server_table
    monkeypatch.setenv("QUERY_STATEMENT_TIMEOUT_SECONDS", "1")
    executor = ReadOnlyExecutor(url, dialect=_dialect(url))
    if url.startswith("postgresql"):
        slow = "SELECT COUNT(*) FROM generate_series(1, 1000000000)"
    else:
        slow = (
            "SELECT COUNT(*) FROM puchoo_ro_probe a, puchoo_ro_probe b, puchoo_ro_probe c, puchoo_ro_probe d, "
            "puchoo_ro_probe e, puchoo_ro_probe f, puchoo_ro_probe g, puchoo_ro_probe h, puchoo_ro_probe i"
        )
    executor.guardrails = _PermissiveGuard(slow)
    started = perf_counter()
    with pytest.raises(QueryTimeoutError):
        executor.execute(slow)
    assert perf_counter() - started < 15


@pytest.mark.parametrize("server_table", _server_params(), indirect=True)
def test_server_row_cap(monkeypatch, server_table):
    url = server_table
    monkeypatch.setenv("QUERY_MAX_ROWS", "3")
    executor = ReadOnlyExecutor(url, dialect=_dialect(url))
    result = executor.execute("SELECT id FROM puchoo_ro_probe ORDER BY id")
    assert result.row_count == 3 and result.truncated is True
    executor = ReadOnlyExecutor(url, dialect=_dialect(url))
    executor.guardrails = _PermissiveGuard("SELECT id FROM puchoo_ro_probe")
    result = executor.execute("ignored")
    assert result.row_count == 3 and result.truncated is True


@pytest.mark.parametrize("server_table", _server_params(), indirect=True)
def test_server_sql_runs_verbatim_with_colons_and_percent_signs(server_table):
    url = server_table
    executor = ReadOnlyExecutor(url, dialect=_dialect(url), max_rows=5)
    sql = "SELECT 'at 10:30 :id 50%' AS note, id FROM puchoo_ro_probe WHERE 'x' LIKE '%' ORDER BY id"
    planned = executor.validate_query_plan(sql)
    result = executor.execute(planned.sql, exact=True)
    assert result.rows[0]["note"] == "at 10:30 :id 50%"
