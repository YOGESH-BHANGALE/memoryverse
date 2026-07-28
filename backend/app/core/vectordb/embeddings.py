"""
Embeddings — text chunking and embedding generation using OpenAI via LangChain.
"""

from __future__ import annotations

from typing import Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.models.schemas import CategorisedEntity, EntityCategory, RawDocument
from app.models.entities import entity_to_document
from app.core.vectordb.client import ChromaClient
from app.utils.logger import logger


class EmbeddingService:
    """
    Handles:
    1. Chunking raw document text (512 tokens, 50 overlap)
    2. Generating embeddings via text-embedding-3-small
    3. Storing chunks + entity docs into ChromaDB with rich metadata
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.hf_embedding_model,
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self.chroma = ChromaClient()

    # ── Chunk & store raw document text ─────────────────────────────────

    async def store_raw_chunks(
        self,
        document: RawDocument,
        user_id: str = "default",
        file_id: str | None = None,
    ) -> int:
        """Split raw document text into chunks, embed, and store in 'raw_chunks'."""
        chunks = self.splitter.split_text(document.text)
        if not chunks:
            return 0

        formatted_chunks = [f"Document: {document.filename}\n\n{chunk}" for chunk in chunks]
        vectors = await self.embeddings.aembed_documents(formatted_chunks)

        effective_file_id = file_id or document.file_id or ""
        ids = [f"{user_id}_{document.filename}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "user_id": user_id,
                "source_file": document.filename,
                "file_type": document.file_type.value,
                "chunk_index": i,
                "file_id": effective_file_id,
            }
            for i in range(len(chunks))
        ]

        self.chroma.upsert(
            collection_name="raw_chunks",
            ids=ids,
            documents=formatted_chunks,
            metadatas=metadatas,
            embeddings=vectors,
        )
        logger.info(f"Stored {len(chunks)} raw chunks for {document.filename}")
        return len(chunks)

    # ── Store categorised entities ──────────────────────────────────────

    async def store_entities(
        self,
        entities: list[CategorisedEntity],
        user_id: str = "default",
        file_id: str | None = None,
    ) -> int:
        """Embed and store categorised entities in their respective collections."""
        # Group entities by category
        by_category: dict[EntityCategory, list[CategorisedEntity]] = {}
        for entity in entities:
            if file_id and not entity.file_id:
                entity.file_id = file_id
            by_category.setdefault(entity.category, []).append(entity)

        stored = 0
        for category, cat_entities in by_category.items():
            collection_name = f"{category.value}s"  # skill → skills
            docs = [entity_to_document(e) for e in cat_entities]

            doc_texts = [d["document"] for d in docs]
            vectors = await self.embeddings.aembed_documents(doc_texts)

            ids = [d["id"] for d in docs]
            metadatas = [
                {
                    **d["metadata"],
                    "user_id": user_id,
                    "file_id": file_id or d["metadata"].get("file_id", ""),
                }
                for d in docs
            ]

            self.chroma.upsert(
                collection_name=collection_name,
                ids=ids,
                documents=doc_texts,
                metadatas=metadatas,
                embeddings=vectors,
            )
            stored += len(cat_entities)

        logger.info(f"Stored {stored} entities across collections")
        return stored

    # ── Query helper ────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        collection_name: str = "raw_chunks",
        n_results: int = 10,
        where: dict | None = None,
    ) -> dict[str, Any]:
        """Semantic search across a collection."""
        query_embedding = await self.embeddings.aembed_query(query)
        return self.chroma.query(
            collection_name=collection_name,
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
        )
