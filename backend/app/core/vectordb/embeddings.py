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


def _cap_onnx_runtime_threads() -> None:
    """
    Force onnxruntime to a single intra/inter-op thread.

    Render grants ~0.1 CPU but exposes the host's 8 cores, and chromadb 0.5.5
    builds its ``InferenceSession`` without setting ``intra_op_num_threads`` — so
    ORT sizes its thread pool from those 8 visible cores. Each pool thread
    carries its own allocator arena (several MB of resident memory), bought for
    parallelism we cannot use on a fraction of one core. On a 512 MB worker that
    waste is the difference between an upload that fits and one that OOM-kills.

    chromadb owns the session, so the clean interception point is the constructor
    itself: every ``InferenceSession`` — however chromadb calls it — routes
    through this wrapper, which caps the thread counts only when they are still
    at ORT's "use all cores" default (0). Fully defensive: any failure leaves ORT
    exactly as it was, because a broken embedding backend takes the whole app
    down, which is strictly worse than using too much memory.
    """
    try:
        import onnxruntime as ort
    except Exception:  # noqa: BLE001 - ORT absent (e.g. torch backend); nothing to cap
        return
    if getattr(ort.InferenceSession, "_mv_thread_capped", False):
        return

    _orig = ort.InferenceSession

    def _capped(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            # sess_options may arrive positionally (2nd arg) or by keyword.
            so = None
            if len(args) >= 2 and isinstance(args[1], ort.SessionOptions):
                so = args[1]
            elif kwargs.get("sess_options") is not None:
                so = kwargs["sess_options"]
            else:
                so = ort.SessionOptions()
                kwargs["sess_options"] = so
            if so.intra_op_num_threads == 0:
                so.intra_op_num_threads = 1
            if so.inter_op_num_threads == 0:
                so.inter_op_num_threads = 1
        except Exception:  # noqa: BLE001 - never block session creation
            pass
        return _orig(*args, **kwargs)

    _capped._mv_thread_capped = True  # type: ignore[attr-defined]
    ort.InferenceSession = _capped  # type: ignore[assignment]


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
    # smaller slices bounds what it allocates internally. This matters twice
    # over: ORT's arena is a high-water-mark allocator that never shrinks, so the
    # LARGEST batch ever seen sets the worker's permanent memory floor — not just
    # a momentary transient. At 4, that peak is ~12 MB (vs ~101 MB at 32). Total
    # CPU work is unchanged (0.1 CPU is the real throughput limit), so bounding
    # the batch costs nothing measurable and keeps the resident floor low enough
    # that successive uploads don't stack into the ceiling. See probe results in
    # docs/DEPLOYMENT.md.
    _BATCH_SIZE = 4

    def __init__(self) -> None:
        # Cap ORT threads before chromadb lazily builds its session on first
        # inference — see _cap_onnx_runtime_threads for why 8 host cores vs
        # 0.1 granted CPU makes this a memory fix, not a speed one.
        _cap_onnx_runtime_threads()

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
