"""
Embeddings — text chunking and embedding generation.

Two backends produce the same all-MiniLM-L6-v2 vectors:

* ONNX (default): ChromaDB's built-in embedding function. No PyTorch, small
  resident memory — the only backend that fits a 512 MB free-tier container.
* PyTorch: sentence-transformers via HuggingFaceEmbeddings. Heavier; opt in
  with USE_TORCH_EMBEDDINGS=true where memory is not the constraint.

Both docs and queries always go through the *same* instance, so cosine
similarity stays consistent regardless of which backend is active.
"""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings

from app.config import get_settings
from app.models.schemas import CategorisedEntity, EntityCategory, RawDocument
from app.models.entities import entity_to_document
from app.core.vectordb.client import ChromaClient, collection_for_category
from app.core.vectordb.text_splitter import RecursiveCharacterTextSplitter
from app.utils.logger import logger


class ONNXEmbeddings(Embeddings):
    """
    Zero-PyTorch embedding backend using ONNX all-MiniLM-L6-v2.

    This is ChromaDB's built-in ``DefaultEmbeddingFunction`` — the same model as
    the sentence-transformers path but via onnxruntime, so it needs no torch and
    keeps the worker's resident memory well inside a 512 MB free-tier container.
    """

    # ChromaDB's ONNX encoder runs an internal batch of 32 and pads every input
    # to a fixed 256 tokens. For this model (6 layers, 12 heads) the attention
    # tensor for one full batch is 32 × 12 × 256 × 256 × 4 B ≈ 101 MB — a single
    # transient big enough to push a 512 MB container into the OOM killer, which
    # kills the worker outright and surfaces as a 502 mid-upload.
    #
    # We cannot pass a batch size through ``__call__``, but feeding the encoder
    # smaller slices bounds what it allocates internally: at 8, that same peak is
    # ~25 MB. Total CPU work is unchanged (the free tier's 0.1 CPU is the real
    # throughput limit), so this costs nothing measurable and buys ~75 MB of
    # headroom on the hottest path in the app.
    _BATCH_SIZE = 8

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions

        self._ef = embedding_functions.DefaultEmbeddingFunction()
        if self._ef is None:  # thin-client builds return None
            raise RuntimeError(
                "chromadb returned no default embedding function "
                "(thin-client install?); cannot embed without it."
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH_SIZE):
            batch = texts[start : start + self._BATCH_SIZE]
            for vec in self._ef(batch):
                out.append([float(x) for x in vec])
        return out

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        res = self._ef([text])[0]
        return [float(x) for x in res]

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


class EmbeddingService:
    """
    Handles:
    1. Chunking raw document text (512 tokens, 50 overlap)
    2. Generating all-MiniLM-L6-v2 embeddings (ONNX by default, see config)
    3. Storing chunks + entity docs into ChromaDB with rich metadata
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.embeddings = self._build_embeddings(settings)

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=512,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self.chroma = ChromaClient()

    @staticmethod
    def _build_embeddings(settings) -> Embeddings:
        """
        Select the embedding backend, defaulting to ONNX.

        PyTorch's resident footprint (~300-400 MB) on its own overruns what a
        512 MB free-tier worker can spare once the rest of the app is loaded, so
        processing a real document OOM-kills the worker — observed live as a 502
        on ``/api/ingest/upload``. ONNX produces the same all-MiniLM-L6-v2
        vectors without importing torch at all, so it is the default; the torch
        path is opt-in for environments with memory to spare.
        """
        if settings.use_torch_embeddings:
            try:
                # Imported lazily: this module pulls in sentence-transformers and
                # torch, which must not be loaded at all on the default path.
                from langchain_huggingface import HuggingFaceEmbeddings

                emb = HuggingFaceEmbeddings(model_name=settings.hf_embedding_model)
                emb.embed_query("warmup")
                logger.info("Using HuggingFaceEmbeddings (PyTorch/SentenceTransformers)")
                return emb
            except Exception as e:
                logger.warning(
                    f"HuggingFaceEmbeddings unavailable ({e}); "
                    "falling back to the ONNX embedding backend."
                )

        emb = ONNXEmbeddings()
        # Force the ONNX model to download/load now rather than on the first
        # upload, so a cold request pays for retrieval only, not model init.
        emb.embed_query("warmup")
        logger.info("Using ONNX DefaultEmbeddingFunction (no PyTorch)")
        return emb

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
            collection_name = collection_for_category(category)  # skill → skills
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
