"""Persistent user notifications with a server-sent-event update stream."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend import database
from backend.database import get_db
from backend.models import Notification
from backend.routers.auth import current_user


router = APIRouter(prefix="/notifications", tags=["notifications"])


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
def read_all_notifications(user=Depends(current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    now = datetime.now(timezone.utc)
    for row in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))).all():
        row.read_at = now
    db.commit()
    return {"ok": True}


@router.post("/{notification_id}/read")
def read_notification(notification_id: str, user=Depends(current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.get("/stream")
async def notification_stream(user=Depends(current_user)) -> StreamingResponse:
    """Push newly persisted events to this authenticated user over SSE."""

    user_id = user.id

    async def events():
        last_seen = datetime.now(timezone.utc)
        while True:
            db = database.SessionLocal()
            try:
                rows = db.scalars(
                    select(Notification)
                    .where(Notification.user_id == user_id, Notification.created_at > last_seen)
                    .order_by(Notification.created_at.asc())
                ).all()
                for row in rows:
                    last_seen = max(last_seen, _as_utc(row.created_at))
                    yield f"event: notification\ndata: {json.dumps(_serialize(row))}\n\n"
            finally:
                db.close()
            yield ": keepalive\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
