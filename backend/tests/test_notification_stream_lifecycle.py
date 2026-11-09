"""Real session/JWT/SQLite mutations across already-open SSE generators."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from apps.api.routers import notifications as router
from backend import database
from backend.config import settings
from backend.models import User, Tenant, TenantMembership, AuthSession, Notification
from backend.security import new_session_token, hash_token
from backend.routers.auth import current_user


class Request:
    def __init__(self, token):
        self.cookies = {settings.session_cookie_name: token}

    async def is_disconnected(self):
        return False


def seed():
    with database.SessionLocal() as db:
        user = User(
            full_name="SSE Synthetic",
            email="sse@example.invalid",
            password_hash="synthetic",
            workspace_type="personal",
            workspace_role="owner",
        )
        db.add(user)
        db.flush()
        tenant = Tenant(
            id=user.id,
            owner_user_id=user.id,
            name="Synthetic",
            workspace_type="personal",
        )
        db.add(tenant)
        db.flush()
        db.add(TenantMembership(tenant_id=user.id, user_id=user.id, role="owner"))
        record = AuthSession(
            user_id=user.id,
            token_hash="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(record)
        db.flush()
        token = new_session_token(user.id, record.id, record.expires_at)
        record.token_hash = hash_token(token)
        db.commit()
        return (
            SimpleNamespace(
                id=user.id, workspace_owner_id=None, institute_owner_id=None
            ),
            record.id,
            token,
        )


def add_events(user_id):
    with database.SessionLocal() as db:
        for number in range(2):
            db.add(
                Notification(
                    user_id=user_id,
                    kind="synthetic",
                    title=f"private {number}",
                    body="synthetic data",
                    created_at=datetime.now(timezone.utc)
                    + timedelta(seconds=1, microseconds=number),
                )
            )
        db.commit()


@pytest.mark.parametrize(
    "change", ["revoked", "expired", "membership", "tenant", "role", "jwt_expired"]
)
def test_open_stream_closes_before_new_event_after_auth_change(
    app, monkeypatch, change
):
    user, sid, token = seed()
    slots = router.StreamSlots()
    monkeypatch.setattr(router, "stream_slots", slots)
    monkeypatch.setattr(router, "STREAM_POLL_SECONDS", 0)

    async def scenario():
        response = await router.notification_stream(Request(token), user)
        iterator = response.body_iterator
        assert await anext(iterator) == ": keepalive\n\n"
        with database.SessionLocal() as db:
            record = db.get(AuthSession, sid)
            if change == "revoked":
                record.revoked_at = datetime.now(timezone.utc)
            elif change == "expired":
                record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            elif change == "membership":
                db.delete(
                    db.scalar(
                        select(TenantMembership).where(
                            TenantMembership.user_id == user.id
                        )
                    )
                )
            elif change == "tenant":
                db.get(User, user.id).workspace_owner_id = "different-tenant"
            elif change == "role":
                db.scalar(
                    select(TenantMembership).where(TenantMembership.user_id == user.id)
                ).role = "viewer"
            db.commit()
        if change == "jwt_expired":

            class Future(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.now(timezone.utc) + timedelta(days=2)

            monkeypatch.setattr("jwt.api_jwt.datetime", Future)
        add_events(user.id)
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
        assert slots.count(user.id) == 0

    asyncio.run(scenario())


def test_revocation_between_events_does_not_drain_stale_batch(app, monkeypatch):
    user, sid, token = seed()
    monkeypatch.setattr(router, "STREAM_POLL_SECONDS", 0)

    async def scenario():
        response = await router.notification_stream(Request(token), user)
        iterator = response.body_iterator
        await anext(iterator)
        add_events(user.id)
        assert "private 0" in await anext(iterator)
        with database.SessionLocal() as db:
            db.get(AuthSession, sid).revoked_at = datetime.now(timezone.utc)
            db.commit()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)

    asyncio.run(scenario())


def test_database_failure_closes_fail_closed_and_releases_slot(app, monkeypatch):
    user, sid, token = seed()
    slots = router.StreamSlots()
    monkeypatch.setattr(router, "stream_slots", slots)

    def unavailable():
        raise OperationalError("synthetic", {}, Exception("private DB error"))

    async def scenario():
        response = await router.notification_stream(Request(token), user)
        monkeypatch.setattr(database, "SessionLocal", unavailable)
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        assert slots.count(user.id) == 0

    asyncio.run(scenario())


def test_session_renewal_cookie_survives_streaming_response(app):
    user, sid, token = seed()
    response = Response()
    request = Request(token)
    with database.SessionLocal() as db:
        db.get(AuthSession, sid).expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=10
        )
        db.commit()
        authenticated = current_user(request, response, db)
        stream = asyncio.run(
            router.notification_stream(request, authenticated, response)
        )
    assert any(
        key == b"set-cookie" and settings.session_cookie_name.encode() in value
        for key, value in stream.raw_headers
    )
    asyncio.run(stream.background())
