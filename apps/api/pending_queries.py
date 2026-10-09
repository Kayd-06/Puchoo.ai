"""Pending (unapproved) SQL: create, claim once, cancel.

Generated SQL is stored here and returned to the user. Nothing runs until the
same user approves the exact SQL (by id and SHA-256) before it expires. A claim
is a single conditional UPDATE, so two concurrent approvals cannot both win.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from apps.api.security import tenant_owner_id
from backend.models import PendingQuery

DEFAULT_TTL_SECONDS = 600
MAX_OPEN_PER_USER = 20
PENDING_ID_PATTERN = r"^pq_[a-f0-9]{32}$"
SQL_HASH_PATTERN = r"^[a-f0-9]{64}$"


def pending_ttl_seconds() -> int:
    raw = os.getenv("PENDING_QUERY_TTL_SECONDS", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_TTL_SECONDS
    except ValueError:
        value = DEFAULT_TTL_SECONDS
    return max(30, min(value, 3600))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes; every stored value is UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _purge(db: Session, user_id: str, now: datetime) -> None:
    """Drop this user's expired or long-finished approvals."""

    db.execute(
        delete(PendingQuery).where(
            PendingQuery.user_id == user_id,
            (PendingQuery.expires_at <= now - timedelta(days=1))
            | ((PendingQuery.consumed_at.is_not(None)) & (PendingQuery.consumed_at <= now - timedelta(days=1))),
        )
        .execution_options(synchronize_session=False)
    )


def create_pending(
    db: Session,
    *,
    user: Any,
    workspace_id: str,
    sql: str,
    limit_clamped: bool,
    context: dict[str, Any],
    parent_id: str | None = None,
) -> PendingQuery:
    now = utcnow()
    _purge(db, user.id, now)
    open_ids = db.scalars(
        select(PendingQuery.id)
        .where(PendingQuery.user_id == user.id, PendingQuery.consumed_at.is_(None), PendingQuery.expires_at > now)
        .order_by(PendingQuery.created_at.desc())
    ).all()
    stale = open_ids[MAX_OPEN_PER_USER - 1 :]
    if stale:
        db.execute(
            update(PendingQuery)
            .where(PendingQuery.id.in_(stale), PendingQuery.consumed_at.is_(None))
            .values(consumed_at=now, outcome="superseded")
            .execution_options(synchronize_session=False)
        )
    pending = PendingQuery(
        id="pq_" + secrets.token_hex(16),
        user_id=user.id,
        tenant_id=tenant_owner_id(user),
        workspace_id=workspace_id,
        sql=sql,
        sql_hash=sql_hash(sql),
        limit_clamped=bool(limit_clamped),
        context_json=json.dumps(context, ensure_ascii=False, default=str),
        parent_id=parent_id,
        created_at=now,
        expires_at=now + timedelta(seconds=pending_ttl_seconds()),
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


def public_pending(pending: PendingQuery) -> dict[str, Any]:
    """Fields the client needs to show the SQL and approve it."""

    return {
        "pending_id": pending.id,
        "sql": pending.sql,
        "sql_hash": pending.sql_hash,
        "created_at": _aware(pending.created_at).isoformat(),
        "expires_at": _aware(pending.expires_at).isoformat(),
        "repair_of": pending.parent_id,
    }


def _owned(pending: PendingQuery | None, *, user: Any, workspace_id: str) -> bool:
    return (
        pending is not None
        and pending.user_id == user.id
        and pending.tenant_id == tenant_owner_id(user)
        and pending.workspace_id == workspace_id
    )


def claim_pending(
    db: Session, *, pending_id: str, user: Any, workspace_id: str, expected_hash: str
) -> PendingQuery:
    """Consume an approval exactly once, or raise a user-facing HTTP error."""

    now = utcnow()
    result = db.execute(
        update(PendingQuery)
        .where(
            PendingQuery.id == pending_id,
            PendingQuery.user_id == user.id,
            PendingQuery.tenant_id == tenant_owner_id(user),
            PendingQuery.workspace_id == workspace_id,
            PendingQuery.sql_hash == expected_hash,
            PendingQuery.consumed_at.is_(None),
            PendingQuery.expires_at > now,
        )
        .values(consumed_at=now, outcome="approved")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    pending = db.get(PendingQuery, pending_id)
    if result.rowcount == 1 and pending is not None:
        if sql_hash(pending.sql) != pending.sql_hash:  # stored row was altered
            raise HTTPException(status_code=409, detail="This query changed after it was shown to you. Ask the question again.")
        return pending
    # Same answer for "missing" and "someone else's", so ids cannot be probed.
    if not _owned(pending, user=user, workspace_id=workspace_id):
        raise HTTPException(status_code=404, detail="This query approval was not found.")
    if pending.consumed_at is not None:
        raise HTTPException(
            status_code=409,
            detail="This query was already run or cancelled. Ask the question again to run it again.",
        )
    if _aware(pending.expires_at) <= now:
        raise HTTPException(status_code=410, detail="This query approval expired. Ask the question again.")
    raise HTTPException(
        status_code=409, detail="The SQL you approved does not match the SQL that was proposed. Ask the question again."
    )


def finish_pending(db: Session, pending: PendingQuery, outcome: str) -> None:
    pending.outcome = outcome[:20]
    db.commit()


def cancel_pending(db: Session, *, pending_id: str, user: Any, workspace_id: str) -> None:
    now = utcnow()
    result = db.execute(
        update(PendingQuery)
        .where(
            PendingQuery.id == pending_id,
            PendingQuery.user_id == user.id,
            PendingQuery.tenant_id == tenant_owner_id(user),
            PendingQuery.workspace_id == workspace_id,
            PendingQuery.consumed_at.is_(None),
        )
        .values(consumed_at=now, outcome="cancelled")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount != 1:
        pending = db.get(PendingQuery, pending_id)
        if not _owned(pending, user=user, workspace_id=workspace_id):
            raise HTTPException(status_code=404, detail="This query approval was not found.")
        # Already run, cancelled or superseded: cancelling again is a no-op.


def pending_context(pending: PendingQuery) -> dict[str, Any]:
    try:
        context = json.loads(pending.context_json or "{}")
    except ValueError:
        context = {}
    return context if isinstance(context, dict) else {}
