"""Persistent, tenant-isolated ChromaDB memory for approved conversations.

Only an approved query's conversational context is stored here. Query result
rows, connection strings, passwords, and authentication tokens are never sent
to ChromaDB. Every read and write includes both tenant and workspace scope.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_PATH = PROJECT_ROOT / ".pucho" / "chroma"
COLLECTION_NAME = "approved_conversations"
EMBEDDING_DIMENSION = 64


class ChatMemoryError(RuntimeError):
    """Raised when persistent conversation memory cannot be read or written."""


def _embedding(text: str) -> list[float]:
    """Small deterministic local embedding; it never downloads a model or sends data away."""

    vector = [0.0] * EMBEDDING_DIMENSION
    for token in re.findall(r"[a-z0-9_]+", text.casefold()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % EMBEDDING_DIMENSION
        vector[bucket] += 1.0
    length = sum(value * value for value in vector) ** 0.5
    return [value / length for value in vector] if length else vector


def _compact_text(value: Any, limit: int = 4_000) -> str:
    text = value if isinstance(value, str) else ""
    return " ".join(text.split())[:limit]


class ApprovedConversationMemory:
    """ChromaDB repository that requires tenant and workspace scope on every call."""

    def __init__(self, persist_path: Path | str | None = None) -> None:
        directory = Path(persist_path or os.getenv("CHROMA_PATH", DEFAULT_CHROMA_PATH))
        directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(directory),
            settings=Settings(anonymized_telemetry=False),
        )
        # Embeddings are always supplied explicitly, avoiding Chroma's hosted/default model.
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"purpose": "approved-user-conversations", "embedding": "local-token-hash-v1"},
        )

    @staticmethod
    def _scope(tenant_id: str, workspace_id: str) -> dict[str, Any]:
        if not tenant_id or not workspace_id:
            raise ChatMemoryError("Tenant and workspace scope are required for conversation memory.")
        return {
            "$and": [
                {"tenant_id": {"$eq": tenant_id}},
                {"workspace_id": {"$eq": workspace_id}},
            ]
        }

    def save_approved_conversation(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        actor_user_id: str,
        record: dict[str, Any],
    ) -> None:
        """Persist approved conversational context, excluding result rows and SQL."""

        self._scope(tenant_id, workspace_id)
        record_id = _compact_text(record.get("id"), 120)
        if not record_id:
            raise ChatMemoryError("Approved conversation requires a record id.")
        question = _compact_text(record.get("question"))
        interpreted = _compact_text(record.get("interpreted_request"))
        planning_question = _compact_text(record.get("processing_question"))
        verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
        verification_summary = _compact_text(verification.get("summary"), 1_000)
        document = "\n".join(
            item
            for item in (
                f"Question: {question}" if question else "",
                f"Interpretation: {interpreted}" if interpreted else "",
                f"Planning question: {planning_question}" if planning_question else "",
                f"Verification: {verification_summary}" if verification_summary else "",
            )
            if item
        )
        if not document:
            raise ChatMemoryError("Approved conversation has no safe text to store.")
        metadata = {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "actor_user_id": actor_user_id,
            "created_at": _compact_text(record.get("executed_at") or record.get("created_at"), 64),
            "status": "approved",
            "memory_generation": int(record.get("memory_generation", 0)),
        }
        try:
            self._collection.upsert(
                ids=[record_id],
                documents=[document],
                embeddings=[_embedding(document)],
                metadatas=[metadata],
            )
        except Exception as exc:  # Chroma wraps storage errors in implementation-specific types.
            raise ChatMemoryError("Could not persist approved conversation memory.") from exc

    def search_approved_conversations(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return only the caller's tenant/workspace matches, never cross-tenant results."""

        where = self._scope(tenant_id, workspace_id)
        clean_query = _compact_text(query)
        if not clean_query:
            return []
        try:
            result = self._collection.query(
                query_embeddings=[_embedding(clean_query)],
                n_results=max(1, min(limit, 10)),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise ChatMemoryError("Could not read approved conversation memory.") from exc
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            {
                "id": item_id,
                "content": document,
                "created_at": metadata.get("created_at") if metadata else None,
                "distance": distance,
                "memory_generation": metadata.get("memory_generation", 0) if metadata else 0,
            }
            for item_id, document, metadata, distance in zip(ids, documents, metadatas, distances)
        ]

    def delete_workspace_memory(self, *, tenant_id: str, workspace_id: str) -> None:
        """Delete this tenant's approved memory for a workspace (used by Clear history)."""

        try:
            self._collection.delete(where=self._scope(tenant_id, workspace_id))
        except Exception as exc:
            raise ChatMemoryError("Could not clear approved conversation memory.") from exc

    def delete_approved_conversation(self, *, tenant_id: str, workspace_id: str, record_id: str) -> None:
        """Delete one approved conversation after verifying its tenant/workspace scope.

        The lookup is deliberately scoped before deleting by id. This avoids an
        identifier-only deletion becoming a cross-tenant operation should a
        record id ever be reused by another storage source.
        """

        where = self._scope(tenant_id, workspace_id)
        clean_record_id = _compact_text(record_id, 120)
        if not clean_record_id:
            raise ChatMemoryError("Conversation memory requires a record id.")
        try:
            found = self._collection.get(ids=[clean_record_id], where=where, include=[])
            if clean_record_id in (found.get("ids") or []):
                self._collection.delete(ids=[clean_record_id])
        except Exception as exc:
            raise ChatMemoryError("Could not delete approved conversation memory.") from exc


class GuardedConversationMemory:
    """The API/RAG boundary: fail closed if durable deletion policy cannot be read."""
    def __init__(self, storage):
        self.storage = storage

    def save_approved_conversation(self, *, tenant_id, workspace_id, actor_user_id, record):
        from apps.core.local_state import STATE_LOCK
        from backend import database
        from backend.models import WorkspaceRecord, WorkspaceHistoryRecord
        from backend.memory_deletions import suppressed
        from sqlalchemy import select
        try:
            with STATE_LOCK, database.SessionLocal() as db:
                workspace = db.get(WorkspaceRecord, workspace_id)
                record_id = str(record.get("id", ""))
                saved = db.scalar(select(WorkspaceHistoryRecord.id).where(
                    WorkspaceHistoryRecord.workspace_id == workspace_id,
                    WorkspaceHistoryRecord.entry_id == record_id))
                if not workspace or workspace.tenant_id != tenant_id or saved is None:
                    return False
                if suppressed(db, tenant_id, workspace_id, record_id, int(record.get("memory_generation", 0))):
                    return False
                self.storage.save_approved_conversation(tenant_id=tenant_id, workspace_id=workspace_id,
                    actor_user_id=actor_user_id, record=record)
                return True
        except Exception as exc:
            raise ChatMemoryError("Conversation memory policy or storage is unavailable.") from exc

    def search_approved_conversations(self, *, tenant_id, workspace_id, query, limit=5):
        from apps.core.local_state import STATE_LOCK
        from backend import database
        from backend.models import WorkspaceRecord, WorkspaceHistoryRecord
        from sqlalchemy import select
        from backend.memory_deletions import suppressed
        try:
            with STATE_LOCK, database.SessionLocal() as db:
                workspace = db.get(WorkspaceRecord, workspace_id)
                if not workspace or workspace.tenant_id != tenant_id:
                    return []
                matches = self.storage.search_approved_conversations(tenant_id=tenant_id,
                    workspace_id=workspace_id, query=query, limit=limit)
                return [item for item in matches if db.scalar(select(WorkspaceHistoryRecord.id).where(
                    WorkspaceHistoryRecord.workspace_id == workspace_id, WorkspaceHistoryRecord.entry_id == item["id"])) is not None
                    and not suppressed(db, tenant_id, workspace_id,
                    item["id"], int(item.get("memory_generation", 0)))]
        except Exception as exc:
            raise ChatMemoryError("Conversation memory policy or storage is unavailable.") from exc

    def cleanup(self, intent):
        # Caller holds STATE_LOCK. Bulk cleanup selects only suppressed epochs;
        # Chroma $ne includes missing legacy generation metadata (zero).
        from backend import database
        from backend.memory_deletions import generation
        scope = self.storage._scope(intent.tenant_id, intent.workspace_id)
        if intent.record_id:
            where = scope
            kwargs = {"ids": [intent.record_id]}
        else:
            with database.SessionLocal() as db:
                current = generation(db, intent.tenant_id, intent.workspace_id)
            if current <= intent.generation:
                raise ChatMemoryError("Deletion generation policy is unavailable.")
            # Later clears also suppress every older epoch. Never select current
            # records, including newly indexed records that reuse an old vector id.
            where = {"$and": [scope, {"memory_generation": {"$ne": current}}]}
            kwargs = {"limit": 200}
        found = self.storage._collection.get(where=where, include=["metadatas"], **kwargs)
        ids, metadata = found.get("ids") or [], found.get("metadatas") or []
        removed = [item_id for item_id, meta in zip(ids, metadata)
                   if not intent.record_id or int((meta or {}).get("memory_generation", 0)) <= intent.generation]
        if removed:
            self.storage._collection.delete(ids=removed, where=where)
        # No offsets over a mutating collection: each retry starts at eligible data.
        return bool(intent.record_id) or len(ids) < 200, 0


_memory: GuardedConversationMemory | None = None


def get_chat_memory() -> GuardedConversationMemory:
    from apps.core.local_state import STATE_LOCK
    global _memory
    with STATE_LOCK:
        if _memory is None:
            try:
                _memory = GuardedConversationMemory(ApprovedConversationMemory())
            except ChatMemoryError:
                raise
            except Exception as exc:
                raise ChatMemoryError("Could not initialize approved conversation memory.") from exc
        return _memory
