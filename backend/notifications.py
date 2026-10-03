"""Persistence helpers for real account notifications."""

from sqlalchemy.orm import Session

from backend.models import Notification


def create_notification(
    db: Session,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: str = "",
    resource_id: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        kind=kind[:50],
        title=title[:160],
        body=body[:500],
        resource_id=resource_id[:120] if resource_id else None,
    )
    db.add(notification)
    return notification
