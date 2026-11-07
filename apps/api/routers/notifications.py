"""Persistent user notifications with a server-sent-event update stream."""

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend import database
from backend.config import settings
from backend.database import get_db
from backend.models import Notification, TenantMembership
from backend.routers.auth import current_user, _active_session
from backend.authorization import tenant_id_for, effective_role

router = APIRouter(prefix="/notifications", tags=["notifications"])
STREAM_POLL_SECONDS = 3


class StreamSlots:
    """Count open notification streams per user so one account cannot hold
    an unbounded number of long-lived connections and database pollers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: dict[str, int] = {}

    def acquire(self, user_id: str, limit: int) -> bool:
        with self._lock:
            current = self._open.get(user_id, 0)
            if current >= limit:
                return False
            self._open[user_id] = current + 1
            return True

    def release(self, user_id: str) -> None:
        with self._lock:
            remaining = self._open.get(user_id, 0) - 1
            if remaining > 0:
                self._open[user_id] = remaining
            else:
                self._open.pop(user_id, None)

    def count(self, user_id: str) -> int:
        with self._lock:
            return self._open.get(user_id, 0)


stream_slots = StreamSlots()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _serialize(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "resource_id": row.resource_id,
        "created_at": _as_utc(row.created_at).isoformat(),
        "read_at": _as_utc(row.read_at).isoformat() if row.read_at else None,
    }


@router.get("/")
def list_notifications(
    limit: int = 20,
    user=Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 50))
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at))
        .limit(safe_limit)
    ).all()
    unread = db.query(Notification).filter_by(user_id=user.id, read_at=None).count()
    return {"items": [_serialize(row) for row in rows], "unread_count": unread}


@router.post("/read-all")
def read_all_notifications(
    user=Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    now = datetime.now(timezone.utc)
    for row in db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all():
        row.read_at = now
    db.commit()
    return {"ok": True}


@router.post("/{notification_id}/read")
def read_notification(
    notification_id: str, user=Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str, user=Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def _stream_authorized(raw_token, user_id, tenant_id, role):
    """Fresh short transaction; never renew sessions or spend HTTP rate-limit quota."""
    try:
        with database.SessionLocal() as db:
            session = _active_session(db, raw_token)
            if session is None or session.user_id != user_id or session.user is None:
                return False
            user = session.user
            if tenant_id_for(user) != tenant_id or effective_role(user) != role:
                return False
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.user_id == user_id,
                    TenantMembership.tenant_id == tenant_id,
                )
            )
            return membership is not None and membership.role == role
    except SQLAlchemyError:
        return False  # Fail closed; no event or raw DB exception reaches the client.


@router.get("/stream")
async def notification_stream(
    request: Request, user=Depends(current_user), response: Response = None
) -> StreamingResponse:
    """Push newly persisted events to this authenticated user over SSE.

    At most ``NOTIFICATION_STREAMS_PER_USER`` streams (default 3) may be open
    per user; extra ones get 429. The slot is released when the stream ends,
    the client disconnects, or the response is torn down before it starts.
    """

    user_id = user.id
    tenant_id, role = tenant_id_for(user), effective_role(user)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not stream_slots.acquire(user_id, settings.notification_streams_per_user):
        raise HTTPException(
            status_code=429,
            detail="Too many open notification streams. Close another tab and try again.",
            headers={"Retry-After": str(STREAM_POLL_SECONDS * 2)},
        )
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            stream_slots.release(user_id)

    async def events():
        try:
            last_seen = datetime.now(timezone.utc)
            while not await request.is_disconnected():
                if not _stream_authorized(raw_token, user_id, tenant_id, role):
                    return
                try:
                    with database.SessionLocal() as db:
                        rows = db.scalars(
                            select(Notification)
                            .where(
                                Notification.user_id == user_id,
                                Notification.created_at > last_seen,
                            )
                            .order_by(Notification.created_at.asc())
                        ).all()
                        batch = [
                            (_as_utc(row.created_at), _serialize(row)) for row in rows
                        ]
                except SQLAlchemyError:
                    return
                for created_at, item in batch:
                    # A slow consumer can span a revocation between events.
                    if not _stream_authorized(raw_token, user_id, tenant_id, role):
                        return
                    last_seen = max(last_seen, created_at)
                    yield f"event: notification\ndata: {json.dumps(item)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(STREAM_POLL_SECONDS)
        finally:
            release()

    stream = StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        # Also runs if the generator never started (it is idempotent).
        background=BackgroundTask(release),
    )

    # current_user may renew a near-expiry cookie. Preserve that header so the
    # browser can reconnect after the old stream token leaves its rotation grace.
    if response is not None:
        stream.raw_headers.extend(
            (key, value)
            for key, value in response.raw_headers
            if key.lower() == b"set-cookie"
        )
    return stream
