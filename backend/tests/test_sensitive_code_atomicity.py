"""F13: real concurrent requests, independent DB connections, no outbound email.

SQLite uses files (never StaticPool), both journal modes and explicit/legacy
BEGIN. Optional PostgreSQL uses a fresh schema on a dedicated test database.
"""

import asyncio
from datetime import timedelta
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from backend import database
from backend.main import create_app
from backend.models import AuthSession, EmailChangeCode, LoginChallenge, PasswordResetCode, User
from backend.rate_limit import limiter
from backend.routers import auth
from backend.security import hash_password, hash_token, new_session_token, utcnow, verify_password

CODE = "123456"
OLD_PASSWORD = "original-password10"
NEW_EMAIL = "changed@example.com"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password(OLD_PASSWORD)


@pytest.fixture(params=["sqlite", "sqlite-wal", "sqlite-begin", "sqlite-begin-wal", "postgresql"])
def code_db(request, tmp_path):
    kind = request.param
    schema = None
    if kind == "postgresql":
        url = os.getenv("TEST_AUTH_POSTGRES_URL")
        if not url:
            pytest.skip("TEST_AUTH_POSTGRES_URL not configured (dedicated disposable auth test DB)")
        base = database.make_engine(url)
        assert base.dialect.name == "postgresql", "auth test URL must name PostgreSQL"
        schema = "otp_test_" + uuid4().hex
        with base.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = base.execution_options(schema_translate_map={None: schema})
    else:
        engine = base = database.make_engine("sqlite:///" + (tmp_path / "codes.db").as_posix())
        if kind.endswith("wal"):
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar() == "wal"
        if "begin" in kind:
            @event.listens_for(engine, "connect")
            def explicit_control(connection, _record):
                connection.isolation_level = None

            @event.listens_for(engine, "begin")
            def explicit_begin(connection):
                connection.exec_driver_sql("BEGIN")

            engine.dispose()  # Ensure any previously opened connection gets the new mode.
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield SimpleNamespace(engine=engine, factory=factory, backend=kind)
    finally:
        if schema:
            with base.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        base.dispose()


@pytest.fixture(params=["reset", "email"])
def flow(request, code_db, otp_codes, password_hash, monkeypatch):
    kind = request.param
    now = utcnow()
    user_id = str(uuid4())
    model = PasswordResetCode if kind == "reset" else EmailChangeCode
    raw_tokens = []
    with code_db.factory() as db:
        user = User(id=user_id, full_name="Synthetic User", email="original@example.com",
                    password_hash=password_hash, workspace_type="personal", workspace_role="owner")
        db.add(user)
        db.flush()
        for _ in range(2):
            session_id = str(uuid4())
            token = new_session_token(user_id, session_id, now + timedelta(days=7))
            raw_tokens.append(token)
            db.add(AuthSession(id=session_id, user_id=user_id, token_hash=hash_token(token),
                               created_at=now, expires_at=now + timedelta(days=7)))
        challenge = LoginChallenge(user_id=user_id, code_hash="synthetic-hash", attempts=0,
                                   resend_count=0, created_at=now, expires_at=now + timedelta(minutes=5),
                                   last_sent_at=now)
        db.add(challenge)
        fields = dict(user_id=user_id, code_hash=hash_token(CODE), attempts=0,
                      expires_at=now + timedelta(minutes=5))
        if kind == "email":
            fields["new_email"] = NEW_EMAIL
        record = model(**fields)
        db.add(record)
        db.commit()
        record_id, challenge_id = record.id, challenge.id

    app = create_app(include_product=False)
    requests = []
    mutations = []

    def get_db():
        with code_db.factory() as db:
            # Hold references so connection/session identities cannot be recycled
            # while we assert that overlapping requests did not share a connection.
            connection = db.connection().connection.dbapi_connection
            requests.append((db, connection))
            yield db

    @event.listens_for(code_db.engine, "after_cursor_execute")
    def count_mutations(_connection, cursor, _statement, _parameters, context, _many):
        compiled = context.compiled
        if compiled is not None and getattr(compiled.statement, "is_update", False):
            if compiled.statement.table.name == "users":
                mutations.append(cursor.rowcount)

    app.dependency_overrides[database.get_db] = get_db
    monkeypatch.setattr(limiter, "limit", 100)  # Observe DB attempt cap, not the independent IP cap.
    path = "/api/v1/auth/password/reset" if kind == "reset" else "/api/v1/auth/email/change/verify"

    def payload(code=CODE, password="replacement-password10"):
        if kind == "reset":
            return dict(email="original@example.com", code=code, password=password, confirm_password=password)
        return dict(new_email=NEW_EMAIL, code=code)

    async def post_one(body):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                   cookies={"csrf_token": "test-csrf", "puchoo_session": raw_tokens[0]}) as http:
            return await http.post(path, json=body, headers={"X-CSRF-Token": "test-csrf"})

    def post_many(bodies):
        async def run():
            return await asyncio.gather(*(post_one(body) for body in bodies))
        return asyncio.run(run())

    return SimpleNamespace(**vars(code_db), kind=kind, model=model, user_id=user_id,
                           record_id=record_id, challenge_id=challenge_id, payload=payload,
                           post_many=post_many, requests=requests, mutations=mutations, notices=otp_codes.notices)


def overlap_code_reads(monkeypatch, count):
    """Force every request to observe the same pre-claim row, without mocking DB writes."""
    barrier = Barrier(count, timeout=15)
    original = auth.tokens_match

    def compare(left, right):
        result = original(left, right)
        if left == hash_token(CODE):
            barrier.wait()
        return result

    monkeypatch.setattr(auth, "tokens_match", compare)


def assert_unchanged(flow):
    with flow.factory() as db:
        user = db.get(User, flow.user_id)
        assert user.email == "original@example.com"
        assert verify_password(OLD_PASSWORD, user.password_hash)
        sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == flow.user_id)).all()
        assert len(sessions) == 2
        assert all(row.revoked_at is None for row in sessions)
        challenge = db.get(LoginChallenge, flow.challenge_id)
        assert challenge.consumed_at is None and challenge.locked_at is None


def test_overlapping_valid_code_mutates_once(flow, monkeypatch):
    overlap_code_reads(monkeypatch, 2)
    bodies = [flow.payload(password=f"replacement-password{i}0") for i in range(2)]
    responses = flow.post_many(bodies)
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert len({id(db) for db, _ in flow.requests}) == 2
    assert len({id(connection) for _, connection in flow.requests}) == 2
    assert flow.mutations == [1], "exactly one account UPDATE, not merely one final value"
    winner = next(i for i, response in enumerate(responses) if response.status_code == 200)
    with flow.factory() as db:
        assert db.get(flow.model, flow.record_id).consumed_at is not None
        user = db.get(User, flow.user_id)
        sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == flow.user_id)).all()
        assert sum(row.revoked_at is not None for row in sessions) == 2
        assert sum(row.revoked_at is None for row in sessions) == (1 if flow.kind == "email" else 0)
        challenge = db.get(LoginChallenge, flow.challenge_id)
        assert challenge.consumed_at is not None and challenge.locked_at is not None
        if flow.kind == "reset":
            assert verify_password(bodies[winner]["password"], user.password_hash)
            assert not verify_password(bodies[1 - winner]["password"], user.password_hash)
        else:
            assert user.email == NEW_EMAIL
            assert responses[winner].cookies.get("puchoo_session")
    assert flow.notices == (["original@example.com"] if flow.kind == "email" else [])


@pytest.mark.parametrize("count", [3, 8])
def test_overlapping_wrong_codes_count_every_attempt_up_to_cap(flow, monkeypatch, count):
    overlap_code_reads(monkeypatch, count)
    responses = flow.post_many([flow.payload(code="000000") for _ in range(count)])
    assert all(response.status_code == 401 for response in responses)
    assert all(response.json() == {"detail": auth.INVALID_CODE} for response in responses)
    assert len({id(connection) for _, connection in flow.requests}) == count
    with flow.factory() as db:
        row = db.get(flow.model, flow.record_id)
        assert row.attempts == min(count, auth.MAX_CHALLENGE_ATTEMPTS)
        assert (row.consumed_at is not None) is (count >= auth.MAX_CHALLENGE_ATTEMPTS)
    assert_unchanged(flow)
    assert flow.mutations == []


@pytest.mark.parametrize("state", ["expired", "consumed", "exhausted"])
@pytest.mark.parametrize("code", [CODE, "000000"])
def test_ineligible_codes_do_not_mutate_or_increment(flow, state, code):
    with flow.factory() as db:
        row = db.get(flow.model, flow.record_id)
        if state == "expired":
            row.expires_at = utcnow() - timedelta(seconds=1)
        elif state == "consumed":
            row.consumed_at = utcnow()
        else:
            row.attempts = auth.MAX_CHALLENGE_ATTEMPTS
        db.commit()
    response = flow.post_many([flow.payload(code=code)])[0]
    assert response.status_code == 401
    assert response.json() == {"detail": auth.INVALID_CODE}
    with flow.factory() as db:
        row = db.get(flow.model, flow.record_id)
        assert row.attempts == (auth.MAX_CHALLENGE_ATTEMPTS if state == "exhausted" else 0)
        assert (row.consumed_at is not None) is (state == "consumed")
    assert_unchanged(flow)


@pytest.mark.parametrize("phase", ["after_mutation", "before_commit"])
def test_failure_rolls_back_code_account_revocations_and_new_session(flow, monkeypatch, phase):
    with monkeypatch.context() as patch:
        if phase == "after_mutation":
            original = auth._revoke_sessions_and_challenges

            def fail(db, user_id, now):
                original(db, user_id, now)
                db.flush()  # Actual account/revocation writes must be rolled back, not just ORM values.
                raise RuntimeError("synthetic post-mutation failure")

            patch.setattr(auth, "_revoke_sessions_and_challenges", fail)
        else:
            def fail_commit(db):
                db.flush()
                raise RuntimeError("synthetic commit failure")
            event.listen(flow.factory, "before_commit", fail_commit)
        try:
            response = flow.post_many([flow.payload()])[0]
        finally:
            if phase == "before_commit":
                event.remove(flow.factory, "before_commit", fail_commit)
    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred."}
    assert_unchanged(flow)
    with flow.factory() as db:
        row = db.get(flow.model, flow.record_id)
        assert row.consumed_at is None and row.attempts == 0
    assert flow.notices == []
    # Same unchanged code/session can retry after rollback; no partially committed claim.
    assert flow.post_many([flow.payload()])[0].status_code == 200


def test_last_wrong_attempt_racing_valid_code_has_one_consistent_outcome(flow, monkeypatch):
    with flow.factory() as db:
        db.get(flow.model, flow.record_id).attempts = auth.MAX_CHALLENGE_ATTEMPTS - 1
        db.commit()
    overlap_code_reads(monkeypatch, 2)
    valid, wrong = flow.post_many([flow.payload(), flow.payload(code="000000")])
    assert wrong.status_code == 401
    assert valid.status_code in (200, 401)
    with flow.factory() as db:
        row = db.get(flow.model, flow.record_id)
        assert row.consumed_at is not None
        assert row.attempts == (4 if valid.status_code == 200 else 5)
    assert flow.mutations == ([1] if valid.status_code == 200 else [])
    if valid.status_code == 401:
        assert_unchanged(flow)


@pytest.mark.parametrize("change", ["expired", "consumed", "exhausted", "rotated"])
def test_claim_rechecks_database_not_lookup_snapshot(flow, change):
    with flow.factory() as db:
        snapshot = db.get(flow.model, flow.record_id)
        db.expunge(snapshot)  # Retain deliberately stale lookup values after releasing its read transaction.
        db.rollback()
        with flow.factory() as other:
            values = {"expired": {"expires_at": utcnow() - timedelta(seconds=1)},
                      "consumed": {"consumed_at": utcnow()},
                      "exhausted": {"attempts": auth.MAX_CHALLENGE_ATTEMPTS},
                      "rotated": {"code_hash": hash_token("999999")}}[change]
            other.execute(update(flow.model).where(flow.model.id == flow.record_id).values(**values))
            other.commit()
        with pytest.raises(HTTPException) as caught:
            auth._claim_sensitive_code(db, snapshot, CODE)
        assert caught.value.status_code == 401
    assert_unchanged(flow)
