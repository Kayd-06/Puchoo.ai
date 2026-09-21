"""Local ChromaDB retrieval for workspace-scoped schema grounding."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIRECTORY = PROJECT_ROOT / ".pucho" / "chroma"


class VectorStoreError(RuntimeError):
    """Raised when the optional local retrieval index cannot be used."""


class LocalSchemaEmbedding:
    """Small deterministic embedding for schema retrieval without model downloads.

    Schema documents deliberately contain table/column names and split search
    terms. Hashing those terms into a normalized vector gives Chroma a stable,
    fully local retrieval signal while avoiding the default embedding model's
    external download and user-cache dependency.
    """

    dimensions = 384

    def is_legacy(self) -> bool:
        return False

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine"]

    def get_config(self) -> dict[str, int]:
        return {"dimensions": self.dimensions}

    @staticmethod
    def name() -> str:
        return "puchoo_local_schema_hash"

    @staticmethod
    def build_from_config(config: dict[str, int]) -> "LocalSchemaEmbedding":
        return LocalSchemaEmbedding()

    @staticmethod
    def validate_config(config: dict[str, int]) -> None:
        return None

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.embed_documents(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return [self._embed(document) for document in input]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return [self._embed(query) for query in input]

    def _embed(self, document: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = re.findall(r"[a-z0-9]+", document.lower())
        for term in terms:
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            position = int.from_bytes(digest[:4], "big") % self.dimensions
            direction = 1.0 if digest[4] & 1 else -1.0
            vector[position] += direction
        magnitude = math.sqrt(sum(value * value for value in vector))
        return vector if magnitude == 0 else [value / magnitude for value in vector]


def _collection_name(workspace_id: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", workspace_id).strip("-_").lower()
    if not safe_id:
        raise VectorStoreError("The workspace ID cannot be used for a retrieval index.")
    return f"puchoo-{safe_id}"


def _client():
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise VectorStoreError("ChromaDB is not installed. Install the project dependencies and restart the app.") from exc
    CHROMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIRECTORY), settings=Settings(anonymized_telemetry=False))


def _schema_documents(database_uri: str) -> tuple[list[str], list[str], list[dict[str, str]]]:
    engine = None
    try:
        engine = create_engine(database_uri)
        inspector = inspect(engine)
        ids: list[str] = []
        documents: list[str] = []
        metadata: list[dict[str, str]] = []
        for table in inspector.get_table_names():
            columns = inspector.get_columns(table)
            column_lines = [f"- {column['name']} ({column['type']})" for column in columns]
            search_terms = " ".join(
                part for identifier in [table, *(str(column["name"]) for column in columns)]
                for part in identifier.replace("_", " ").split()
            )
            ids.append(f"table-{table}")
            documents.append(f"Table: {table}\nColumns:\n" + "\n".join(column_lines) + f"\nSearch terms: {search_terms}")
            metadata.append({"table": table})
        if not documents:
            raise VectorStoreError("The workspace has no tables to index.")
        return ids, documents, metadata
    except (SQLAlchemyError, ModuleNotFoundError, ImportError) as exc:
        raise VectorStoreError("Could not read the workspace schema for ChromaDB indexing.") from exc
    finally:
        if engine is not None:
            engine.dispose()


def index_workspace_schema(workspace_id: str, database_uri: str) -> int:
    """Upsert one local vector document per source table for a workspace."""

    ids, documents, metadata = _schema_documents(database_uri)
    try:
        collection = _client().get_or_create_collection(
            name=_collection_name(workspace_id),
            metadata={"workspace_id": workspace_id, "kind": "schema"},
            embedding_function=LocalSchemaEmbedding(),
        )
        collection.upsert(ids=ids, documents=documents, metadatas=metadata)
        return len(documents)
    except Exception as exc:
        raise VectorStoreError("Could not create the local ChromaDB schema index.") from exc


def retrieve_workspace_schema(workspace_id: str, question: str, *, limit: int = 4) -> list[str]:
    """Return only the schema documents most relevant to a question."""

    if not question.strip() or limit <= 0:
        return []
    try:
        collection = _client().get_collection(
            name=_collection_name(workspace_id),
            embedding_function=LocalSchemaEmbedding(),
        )
        count = collection.count()
        if not count:
            return []
        result = collection.query(query_texts=[question], n_results=min(limit, count), include=["documents"])
        documents = result.get("documents", [[]])
        return [document for document in documents[0] if isinstance(document, str)] if documents else []
    except Exception as exc:
        raise VectorStoreError("Could not retrieve relevant workspace schema from ChromaDB.") from exc
