"""Generated SQL runs only after the user approves it (H2).

Covers: generate never executes, approval is CSRF-protected, single-use,
expiring, bound to user/tenant/workspace, re-validated at run time, and a
runtime repair becomes a NEW pending query that needs approval again.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api import pending_queries
from apps.api.routers import query as query_router
from apps.api.session import session_manager
from apps.core import executor as executor_module
from apps.core.query_planning import ComplexityDecision
from backend import database
from backend.main import create_app
from backend.models import PendingQuery, User
from backend.tests.conftest import csrf_headers, finish_signup, signup_payload

WORKSPACE_ID = "approval-workspace"
MIN_INT = -9223372036854775808


class FakeSQLClient:
    provider_name = "fake model"

    def __init__(self) -> None:
        self.sql = "SELECT region, SUM(amount) AS total FROM orders GROUP BY region ORDER BY region"
        self.repair_sql = "SELECT id, amount FROM orders WHERE amount > 0 ORDER BY id"
        self.repair_calls = 0

    def generate_sql(self, *, schema, question, feedback=None, previous_sql=None):
        if previous_sql is not None:
            self.repair_calls += 1
            return self.repair_sql
        return self.sql


class FakeVerification:
    def as_dict(self):
        return {"status": "VERIFIED", "summary": "ok", "details": ""}


class FakeVerifier:
    def verify(self, **_kwargs):
        return FakeVerification()


class FakeMemory:
    def save_approved_conversation(self, **_kwargs):
        return None


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, region TEXT, amount INTEGER)")
    connection.executemany(
        "INSERT INTO orders (region, amount) VALUES (?, ?)",
        [("north", 10), ("south", 20), ("north", 5)],
    )
    connection.commit()
    connection.close()
    return path


def _orders(path: Path) -> list[tuple]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT id, region, amount FROM orders ORDER BY id").fetchall()
    finally:
        connection.close()


def _signup(test_client: TestClient, email: str, otp_codes, **overrides) -> None:
    response = test_client.post(
        "/api/v1/auth/signup",
        json=signup_payload(full_name="Test User", email=email, **overrides),
        headers=csrf_headers(test_client),
    )
    assert response.status_code == 202, response.text
    finish_signup(test_client, email, otp_codes)


def _user_id(email: str) -> str:
    db = database.SessionLocal()
    try:
        return db.query(User).filter_by(email=email).one().id
    finally:
        db.close()


class Env:
    def __init__(self, owner: TestClient, source: Path, fake: FakeSQLClient, executions: list[str]):
        self.owner = owner
        self.source = source
        self.fake = fake
        self.executions = executions

    def generate(self, test_client: TestClient | None = None, question: str = "Show total amount per region"):
        test_client = test_client or self.owner
        return test_client.post(
            f"/api/query/{WORKSPACE_ID}/generate",
            json={"question": question},
            headers=csrf_headers(test_client),
        )

    def approve(self, pending: dict, test_client: TestClient | None = None, *, sql_hash: str | None = None, csrf: bool = True):
        test_client = test_client or self.owner
        return test_client.post(
            f"/api/query/{WORKSPACE_ID}/pending/{pending['pending_id']}/approve",
            json={"sql_hash": sql_hash or pending["sql_hash"]},
            headers=csrf_headers(test_client) if csrf else {},
        )

    def cancel(self, pending: dict, test_client: TestClient | None = None):
        test_client = test_client or self.owner
        return test_client.post(
            f"/api/query/{WORKSPACE_ID}/pending/{pending['pending_id']}/cancel",
            headers=csrf_headers(test_client),
        )


@pytest.fixture
def env(app, otp_codes, tmp_path, monkeypatch):
    source = _source(tmp_path)
    fake = FakeSQLClient()
    executions: list[str] = []
    original_execute = executor_module.ReadOnlyExecutor.execute

    def counting_execute(self, sql, **kwargs):
        executions.append(sql)
        return original_execute(self, sql, **kwargs)

    monkeypatch.setattr(executor_module.ReadOnlyExecutor, "execute", counting_execute)
    monkeypatch.setattr(query_router, "get_sql_client", lambda: fake)
    monkeypatch.setattr(query_router, "schema_guided_fallback_sql", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        query_router, "classify_complexity", lambda *_args, **_kwargs: ComplexityDecision("simple", 0, ())
    )
    monkeypatch.setattr(query_router, "get_verifier", lambda: FakeVerifier())
    monkeypatch.setattr(query_router, "get_chat_memory", lambda: FakeMemory())
    monkeypatch.setattr(session_manager, "save", lambda *args, **kwargs: None)

    with TestClient(create_app(include_product=True)) as owner:
        _signup(owner, "owner@approvalco.com", otp_codes, workspace_type="business", workspace_name="Approval Co")
        session_manager.workspaces[WORKSPACE_ID] = {
            "id": WORKSPACE_ID,
            "name": "Approval source",
            "owner_user_id": _user_id("owner@approvalco.com"),
            "database_uri": f"sqlite:///{source}",
            "dialect": "sqlite",
        }
        session_manager.workspace_guardrails[WORKSPACE_ID] = session_manager.DEFAULT_GUARDRAILS.copy()
        session_manager.query_history[WORKSPACE_ID] = []
        try:
            yield Env(owner, source, fake, executions)
        finally:
            session_manager.workspaces.pop(WORKSPACE_ID, None)
            session_manager.workspace_guardrails.pop(WORKSPACE_ID, None)
            session_manager.query_history.pop(WORKSPACE_ID, None)
            session_manager.schema_snapshots.pop(f"schema_{WORKSPACE_ID}", None)


def _invite_member(env: Env, otp_codes, role: str, email: str) -> TestClient:
    code = env.owner.post(
        "/api/v1/auth/workspace/invite", json={"role": role}, headers=csrf_headers(env.owner)
    ).json()["code"]
    member = TestClient(create_app(include_product=True))
    member.__enter__()
    _signup(member, email, otp_codes, workspace_type="personal", invite_code=code)
    return member


def _set_pending(pending_id: str, **values) -> None:
    db = database.SessionLocal()
    try:
        row = db.get(PendingQuery, pending_id)
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def test_generate_returns_sql_for_approval_without_running_it(env):
    response = env.generate()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["pending_id"].startswith("pq_")
    assert body["sql"].endswith("LIMIT 500")
    assert body["sql_hash"] == pending_queries.sql_hash(body["sql"])
    assert body["expires_at"] > body["created_at"]
    assert "rows" not in body
    assert env.executions == []
    assert session_manager.query_history[WORKSPACE_ID] == []


def test_approved_query_runs_exactly_the_shown_sql_once(env):
    pending = env.generate().json()
    approved = env.approve(pending)
    assert approved.status_code == 200, approved.text
    record = approved.json()["record"]
    assert record["sql"] == pending["sql"]
    assert env.executions == [pending["sql"]]
    assert record["rows"] == [{"region": "north", "total": 15}, {"region": "south", "total": 20}]
    assert record["truncated"] is False
    assert record["approved_pending_id"] == pending["pending_id"]
    assert "sql_hash" not in record and "pending_id" not in record
    # History behaviour is unchanged: one executed record.
    assert [item["status"] for item in session_manager.query_history[WORKSPACE_ID]] == ["executed"]

    again = env.approve(pending)
    assert again.status_code == 409
    assert "already run" in again.json()["detail"]
    assert len(env.executions) == 1


def test_approval_requires_csrf_token(env):
    pending = env.generate().json()
    response = env.approve(pending, csrf=False)
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    assert env.executions == []
    # The failed attempt did not consume the approval.
    assert env.approve(pending).status_code == 200


def test_expired_approval_is_rejected(env):
    pending = env.generate().json()
    _set_pending(pending["pending_id"], expires_at=pending_queries.utcnow() - timedelta(seconds=1))
    response = env.approve(pending)
    assert response.status_code == 410
    assert "expired" in response.json()["detail"]
    assert env.executions == []


def test_ttl_is_about_ten_minutes_by_default(env, monkeypatch):
    monkeypatch.delenv("PENDING_QUERY_TTL_SECONDS", raising=False)
    pending = env.generate().json()
    db = database.SessionLocal()
    try:
        row = db.get(PendingQuery, pending["pending_id"])
        lifetime = (row.expires_at - row.created_at).total_seconds()
    finally:
        db.close()
    assert lifetime == 600


def test_sql_hash_must_match_the_shown_sql(env):
    pending = env.generate().json()
    response = env.approve(pending, sql_hash="0" * 64)
    assert response.status_code == 409
    assert env.executions == []
    assert env.approve(pending).status_code == 200


def test_unknown_or_malformed_ids_are_rejected(env):
    pending = env.generate().json()
    missing = dict(pending, pending_id="pq_" + "0" * 32)
    assert env.approve(missing).status_code == 404
    malformed = dict(pending, pending_id="../../etc")
    assert env.approve(malformed).status_code in {404, 422}
    assert env.executions == []


def test_other_users_cannot_approve_or_cancel(env, otp_codes):
    pending = env.generate().json()
    editor = _invite_member(env, otp_codes, "editor", "editor@approvalco.com")
    try:
        # Same tenant, same workspace, different user.
        assert env.approve(pending, editor).status_code == 404
        assert env.cancel(pending, editor).status_code == 404
    finally:
        editor.__exit__(None, None, None)

    with TestClient(create_app(include_product=True)) as outsider:
        _signup(outsider, "outsider@elsewhereco.com", otp_codes, workspace_type="business", workspace_name="Other Co")
        assert env.approve(pending, outsider).status_code == 404
        assert env.cancel(pending, outsider).status_code == 404

    assert env.executions == []
    assert env.approve(pending).status_code == 200


def test_viewers_cannot_approve(env, otp_codes):
    pending = env.generate().json()
    viewer = _invite_member(env, otp_codes, "viewer", "viewer@approvalco.com")
    try:
        assert env.approve(pending, viewer).status_code == 403
    finally:
        viewer.__exit__(None, None, None)
    assert env.executions == []


def test_cancelled_approval_cannot_run(env):
    pending = env.generate().json()
    assert env.cancel(pending).status_code == 204
    assert env.cancel(pending).status_code == 204  # idempotent
    response = env.approve(pending)
    assert response.status_code == 409
    assert env.executions == []


def test_tampered_stored_sql_is_revalidated_and_blocked(env):
    pending = env.generate().json()
    evil = "SELECT load_extension('/tmp/evil.so')"
    _set_pending(pending["pending_id"], sql=evil, sql_hash=pending_queries.sql_hash(evil))
    response = env.approve(pending, sql_hash=pending_queries.sql_hash(evil))
    assert response.status_code == 403
    assert "load_extension" in response.json()["detail"]
    assert env.executions == [evil]  # reached execute(), which refused before connecting
    assert _orders(env.source)[0] == (1, "north", 10)


def test_write_sql_smuggled_into_storage_never_runs(env):
    pending = env.generate().json()
    evil = "DELETE FROM orders"
    _set_pending(pending["pending_id"], sql=evil, sql_hash=pending_queries.sql_hash(evil))
    response = env.approve(pending, sql_hash=pending_queries.sql_hash(evil))
    assert response.status_code == 403
    assert len(_orders(env.source)) == 3


def test_tightened_limits_after_proposal_block_the_old_sql(env):
    pending = env.generate().json()
    session_manager.workspace_guardrails[WORKSPACE_ID] = {**session_manager.DEFAULT_GUARDRAILS, "max_rows": 10}
    response = env.approve(pending)
    assert response.status_code == 403
    assert "no longer matches" in response.json()["detail"]


def test_schema_change_after_proposal_is_caught_at_run_time(env):
    pending = env.generate().json()
    connection = sqlite3.connect(env.source)
    connection.execute("ALTER TABLE orders RENAME TO orders_archive")
    connection.commit()
    connection.close()
    response = env.approve(pending)
    assert response.status_code == 403
    assert "not part of this data source" in response.json()["detail"]


def test_runtime_error_proposes_a_repair_that_needs_new_approval(env, monkeypatch):
    connection = sqlite3.connect(env.source)
    connection.execute("INSERT INTO orders (region, amount) VALUES ('west', ?)", (MIN_INT,))
    connection.commit()
    connection.close()
    env.fake.sql = "SELECT ABS(amount) AS size FROM orders"  # integer overflow at run time
    pending = env.generate().json()
    assert pending["status"] == "pending_approval"
    monkeypatch.setattr(query_router, "LocalMLXSQLClient", FakeSQLClient)

    response = env.approve(pending)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "repair_pending_approval"
    repaired = body["proposal"]
    assert repaired["pending_id"] != pending["pending_id"]
    assert repaired["repair_of"] == pending["pending_id"]
    assert repaired["sql"].startswith("SELECT id, amount FROM orders WHERE amount > 0")
    assert repaired["sql_hash"] == pending_queries.sql_hash(repaired["sql"])
    # Only the original SQL ran; the repair was proposed, not executed.
    assert env.executions == [pending["sql"]]
    assert env.fake.repair_calls == 1
    assert session_manager.query_history[WORKSPACE_ID] == []

    # The failed original cannot be retried by id.
    assert env.approve(pending).status_code == 409

    run_again = env.approve(repaired)
    assert run_again.status_code == 200, run_again.text
    assert run_again.json()["record"]["sql"] == repaired["sql"]
    assert env.executions == [pending["sql"], repaired["sql"]]
    assert env.approve(repaired).status_code == 409


def test_runtime_error_without_a_repair_capable_model_is_reported(env):
    connection = sqlite3.connect(env.source)
    connection.execute("INSERT INTO orders (region, amount) VALUES ('west', ?)", (MIN_INT,))
    connection.commit()
    connection.close()
    env.fake.sql = "SELECT ABS(amount) AS size FROM orders"
    pending = env.generate().json()
    response = env.approve(pending)
    assert response.status_code == 400
    assert env.fake.repair_calls == 0


def test_unsafe_generated_sql_is_blocked_with_a_clear_message(env):
    env.fake.sql = "SELECT * FROM sqlite_master"
    response = env.generate()
    assert response.status_code == 403
    assert "sqlite_master" in response.json()["detail"]
    assert session_manager.query_history[WORKSPACE_ID][0]["status"] == "blocked"
    db = database.SessionLocal()
    try:
        assert db.query(PendingQuery).count() == 0
    finally:
        db.close()


def test_row_cap_truncation_is_flagged(env, monkeypatch):
    monkeypatch.setenv("QUERY_MAX_ROWS", "2")
    env.fake.sql = "SELECT id FROM orders ORDER BY id"
    pending = env.generate().json()
    assert pending["sql"].endswith("LIMIT 2")
    record = env.approve(pending).json()["record"]
    assert record["row_count"] == 2
    assert record["truncated"] is True
    assert record["row_cap"] == 2


def test_legacy_auto_execute_endpoint_is_gone(env):
    env.generate()
    response = env.owner.post(
        f"/api/query/{WORKSPACE_ID}/execute",
        json={"proposal_id": "qry_000000000000"},
        headers=csrf_headers(env.owner),
    )
    assert response.status_code in {404, 405}
    assert env.executions == []


def test_open_approvals_per_user_are_bounded(env):
    first = env.generate().json()
    for _ in range(pending_queries.MAX_OPEN_PER_USER):
        env.generate()
    response = env.approve(first)
    assert response.status_code == 409


def test_migration_creates_pending_queries_table(tmp_path):
    original_url = database.engine.url.render_as_string(hide_password=False)
    try:
        database.configure_database("sqlite:///" + (tmp_path / "upgrade.db").as_posix())
        database.init_db()
        with database.engine.begin() as connection:
            connection.execute(text("DROP TABLE pending_queries"))
            connection.execute(text("UPDATE alembic_version SET version_num = '20261008_0012'"))
        database.init_db()
        with database.engine.connect() as connection:
            tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
            assert "pending_queries" in tables
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261009_0013"
    finally:
        database.configure_database(original_url)
