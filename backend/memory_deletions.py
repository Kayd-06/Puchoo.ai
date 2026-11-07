"""Durable suppression and bounded cleanup; SQL is authoritative, Chroma is derived.

All API transitions run under STATE_LOCK. Single process only, not a distributed lock.
"""
from datetime import timedelta
from sqlalchemy import select
from backend import database
from backend.models import MemoryDeletion, MemoryGeneration
from backend.security import utcnow
from apps.core.local_state import STATE_LOCK


def generation(db, tenant_id, workspace_id):
    state = db.get(MemoryGeneration, (tenant_id, workspace_id))
    return state.generation if state else 0


def suppressed(db, tenant_id, workspace_id, record_id, record_generation):
    if record_generation != generation(db, tenant_id, workspace_id):
        return True
    return db.scalar(select(MemoryDeletion.id).where(
        MemoryDeletion.tenant_id == tenant_id, MemoryDeletion.workspace_id == workspace_id,
        MemoryDeletion.record_id == record_id, MemoryDeletion.generation >= record_generation,
    ).limit(1)) is not None


def enqueue(db, tenant_id, workspace_id, record_id=None):
    current = generation(db, tenant_id, workspace_id)
    if record_id is None:
        state = db.get(MemoryGeneration, (tenant_id, workspace_id))
        if state is None:
            state = MemoryGeneration(tenant_id=tenant_id, workspace_id=workspace_id, generation=current)
            db.add(state)
        state.generation = current + 1
    else:
        existing = db.scalar(select(MemoryDeletion).where(
            MemoryDeletion.tenant_id == tenant_id, MemoryDeletion.workspace_id == workspace_id,
            MemoryDeletion.record_id == record_id, MemoryDeletion.generation == current,
        ))
        if existing is not None:
            return existing.id
    intent = MemoryDeletion(tenant_id=tenant_id, workspace_id=workspace_id,
                            generation=current, record_id=record_id)
    db.add(intent)
    db.flush()
    return intent.id


def retry_deletions(*, limit=10, intent_id=None):
    """At most limit intents and 200 vectors/intent. Retry time is durable, no hotloop.

    Used at startup, after a delete, and by the maintenance command. Tombstones
    are retained after cleanup to reject late upserts. Returns remaining count
    among the selected intents, not a global queue length.
    """
    from apps.core.chat_memory import get_chat_memory
    with STATE_LOCK:
        with database.SessionLocal() as db:
            query = select(MemoryDeletion).where(MemoryDeletion.completed.is_(False))
            if intent_id:
                query = query.where(MemoryDeletion.id == intent_id)
            else:
                query = query.where(MemoryDeletion.next_attempt_at <= utcnow())
            intents = db.scalars(query.order_by(MemoryDeletion.next_attempt_at).limit(max(1, min(limit, 10)))).all()
            pending = 0
            for intent in intents:
                # Even explicit retries respect backoff after the initial attempt.
                due = intent.next_attempt_at
                if due.tzinfo is None:
                    due = due.replace(tzinfo=utcnow().tzinfo)
                if due > utcnow():
                    pending += 1
                    continue
                try:
                    memory = get_chat_memory()
                    complete, _ = memory.cleanup(intent)
                    intent.completed = complete
                except Exception:
                    # Suppression remains committed even if initialization/physical cleanup fails.
                    intent.completed = False
                intent.attempts += 1
                intent.next_attempt_at = utcnow() + timedelta(seconds=min(300, 2 ** min(intent.attempts, 8)))
                pending += not intent.completed
            db.commit()
            return pending


async def deletion_worker(stop):
    """Same API process/owner; never run a separate cleanup process alongside it."""
    import asyncio
    import logging
    while not stop.is_set():
        try:
            await asyncio.to_thread(retry_deletions, limit=10)
        except Exception:
            logging.getLogger(__name__).warning("memory_cleanup_retry_unavailable")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass
