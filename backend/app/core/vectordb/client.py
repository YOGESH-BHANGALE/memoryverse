"""
ChromaDB Client — persistent vector database with typed collections.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.utils.logger import logger


# Collection names
COLLECTIONS = [
    "skills",
    "projects",
    "certifications",
    "internships",
    "achievements",
    "academics",
    "raw_chunks",
]

# Maps an EntityCategory value → its collection name.
# Most category values are singular ("skill" → "skills"), but "academics" is
# already plural, so the naive f"{value}s" produced "academicss" — a collection
# nothing else ever read from. Keep this mapping as the single source of truth.
_CATEGORY_COLLECTIONS = {
    "skill": "skills",
    "project": "projects",
    "certification": "certifications",
    "internship": "internships",
    "achievement": "achievements",
    "academics": "academics",
}


def collection_for_category(category: Any) -> str:
    """
    Return the canonical collection name for an EntityCategory (or its value).

    Accepts either the enum member or a plain string so callers don't need to
    import the schema module.
    """
    value = getattr(category, "value", category)
    return _CATEGORY_COLLECTIONS.get(value, f"{value}s")


class ChromaClient:
    """
    Singleton wrapper around the persistent ChromaDB client.
    Creates typed collections on first use.
    """

    _instance: Optional["ChromaClient"] = None

    def __new__(cls) -> "ChromaClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        settings = get_settings()
        self.prefix = settings.chroma_collection_prefix
        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._ensure_collections()
        self._initialized = True
        logger.info(f"ChromaDB initialized at {settings.chroma_path}")

    # ── Collection Management ───────────────────────────────────────────

    def _col_name(self, name: str) -> str:
        return f"{self.prefix}_{name}"

    def _ensure_collections(self) -> None:
        for name in COLLECTIONS:
            self.client.get_or_create_collection(
                name=self._col_name(name),
                metadata={"hnsw:space": "cosine"},
            )

    def get_collection(self, name: str):
        return self.client.get_or_create_collection(
            name=self._col_name(name),
            metadata={"hnsw:space": "cosine"},
        )

    # ── CRUD Helpers ────────────────────────────────────────────────────

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: Optional[list[list[float]]] = None,
    ) -> None:
        """Upsert documents into a named collection."""
        col = self.get_collection(collection_name)
        kwargs: dict[str, Any] = {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        if embeddings:
            kwargs["embeddings"] = embeddings
        col.upsert(**kwargs)
        logger.info(f"Upserted {len(ids)} docs into {collection_name}")

    def query(
        self,
        collection_name: str,
        query_texts: Optional[list[str]] = None,
        query_embeddings: Optional[list[list[float]]] = None,
        n_results: int = 10,
        where: Optional[dict] = None,
        include: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Query a collection by text or embedding."""
        col = self.get_collection(collection_name)
        kwargs: dict[str, Any] = {"n_results": n_results}
        if query_texts:
            kwargs["query_texts"] = query_texts
        if query_embeddings:
            kwargs["query_embeddings"] = query_embeddings
        if where:
            kwargs["where"] = where
        if include:
            kwargs["include"] = include
        else:
            kwargs["include"] = ["documents", "metadatas", "distances"]
        return col.query(**kwargs)

    def get_all(
        self,
        collection_name: str,
        where: Optional[dict] = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Retrieve all documents from a collection (optionally filtered)."""
        col = self.get_collection(collection_name)
        kwargs: dict[str, Any] = {"limit": limit, "include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        return col.get(**kwargs)

    def delete(
        self,
        collection_name: str,
        ids: list[str],
    ) -> None:
        """Delete documents by ID from a collection."""
        col = self.get_collection(collection_name)
        col.delete(ids=ids)
        logger.info(f"Deleted {len(ids)} docs from {collection_name}")

    def count(self, collection_name: str) -> int:
        """Return the number of documents in a collection."""
        col = self.get_collection(collection_name)
        return col.count()
