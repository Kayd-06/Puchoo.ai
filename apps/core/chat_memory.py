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
        verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
        verification_summary = _compact_text(verification.get("summary"), 1_000)
        document = "\n".join(
            item
            for item in (
                f"Question: {question}" if question else "",
                f"Interpretation: {interpreted}" if interpreted else "",
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


_memory: ApprovedConversationMemory | None = None


def get_chat_memory() -> ApprovedConversationMemory:
    global _memory
    if _memory is None:
        # Keep a damaged or unavailable local Chroma store contained to the
        # memory-dependent endpoint. Authentication, startup, and approved
        # query execution must remain available when local persistence cannot
        # be opened (a missing directory itself is recreated in __init__).
        try:
            _memory = ApprovedConversationMemory()
        except ChatMemoryError:
            raise
        except Exception as exc:
            raise ChatMemoryError("Could not initialize approved conversation memory.") from exc
    return _memory
