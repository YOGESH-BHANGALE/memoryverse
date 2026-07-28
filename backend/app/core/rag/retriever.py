"""
RAG Retriever — Phase 4: Hybrid search (semantic + BM25) with MMR reranking.

Features:
- Semantic search via ChromaDB embeddings
- BM25 keyword search for lexical recall
- Reciprocal Rank Fusion to merge both signal types
- Maximal Marginal Relevance (MMR) for diversity-aware reranking
- Metadata filters: category, date_range, tags
- Full source attribution on every chunk
"""

from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.vectordb.client import ChromaClient, COLLECTIONS
from app.core.vectordb.embeddings import EmbeddingService
from app.models.schemas import (
    EntityCategory,
    RetrievedChunk,
    SearchResult,
    SourceAttribution,
)
from app.utils.logger import logger


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


class HybridRetriever:
    """
    Multi-signal retriever combining:
    1. Semantic (cosine) via ChromaDB
    2. Keyword (BM25) over the same document corpus
    3. Reciprocal Rank Fusion (RRF) merge
    4. MMR reranking for diversity
    """

    def __init__(self) -> None:
        from app.api.deps import get_embedding_service, get_chroma_client
        self.embedding_service = get_embedding_service()
        self.chroma = get_chroma_client()

    # ── Public API ──────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        category: Optional[EntityCategory] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        tags: Optional[list[str]] = None,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7,
    ) -> list[RetrievedChunk]:
        """
        Hybrid retrieve:
        1. Semantic search across collections
        2. BM25 keyword search across the same docs
        3. RRF merge
        4. Optional MMR reranking
        5. Metadata post-filters (date, tags)
        """
        # Determine collections
        if category:
            collections = [f"{category.value}s"]
        else:
            collections = list(COLLECTIONS)

        # Step 1: Gather ALL docs from target collections (for BM25 corpus)
        corpus_docs = self._gather_corpus(user_id, collections)
        if not corpus_docs:
            logger.info("No documents found in corpus for retrieval")
            return []

        # Step 2: Semantic search
        semantic_results = await self._semantic_search(
            query, user_id, collections, top_k=top_k * 3
        )

        # Step 3: BM25 keyword search
        bm25_results = self._bm25_search(query, corpus_docs, top_k=top_k * 3)

        # Step 4: Reciprocal Rank Fusion
        fused = self._reciprocal_rank_fusion(semantic_results, bm25_results)

        # Step 5: Metadata post-filters
        fused = self._apply_metadata_filters(
            fused, date_from=date_from, date_to=date_to, tags=tags
        )

        # Step 6: MMR reranking for diversity
        if use_mmr and len(fused) > 1:
            fused = await self._mmr_rerank(
                query, fused, top_k=top_k, lambda_param=mmr_lambda
            )
        else:
            fused = fused[:top_k]

        logger.info(
            f"Hybrid retrieval: {len(semantic_results)} semantic + "
            f"{len(bm25_results)} BM25 -> {len(fused)} results (MMR={use_mmr})"
        )
        return fused

    async def find_similar(
        self,
        entity_id: str,
        top_k: int = 10,
    ) -> tuple[str, list[RetrievedChunk]]:
        """Find entities similar to a given entity_id by embedding similarity."""
        # Find the entity in any collection
        entity_text = ""
        entity_title = ""
        entity_collection = ""

        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                col = self.chroma.get_collection(col_name)
                result = col.get(ids=[entity_id], include=["documents", "metadatas"])
                if result and result["ids"]:
                    entity_text = result["documents"][0] if result.get("documents") else ""
                    meta = result["metadatas"][0] if result.get("metadatas") else {}
                    entity_title = meta.get("title", "")
                    entity_collection = col_name
                    break
            except Exception:
                continue

        if not entity_text:
            return "", []

        # Search using the entity text as query across all entity collections
        chunks: list[RetrievedChunk] = []
        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                results = await self.embedding_service.search(
                    query=entity_text,
                    collection_name=col_name,
                    n_results=top_k + 1,
                )
                if not results or not results.get("ids"):
                    continue

                for i, doc_id in enumerate(results["ids"][0]):
                    if doc_id == entity_id:
                        continue  # skip self
                    doc = results["documents"][0][i] if results.get("documents") else ""
                    dist = results["distances"][0][i] if results.get("distances") else 1.0
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}

                    score = round(1.0 - dist, 4)
                    chunks.append(RetrievedChunk(
                        id=doc_id,
                        text=doc,
                        semantic_score=score,
                        combined_score=score,
                        metadata=meta,
                        source=SourceAttribution(
                            chunk_id=doc_id,
                            source_file=meta.get("source_file", meta.get("title", "")),
                            collection=col_name,
                            score=score,
                            snippet=doc[:200],
                            file_id=meta.get("file_id") or None,
                        ),
                    ))
            except Exception as exc:
                logger.warning(f"Similar search in {col_name} failed: {exc}")

        chunks.sort(key=lambda c: c.combined_score, reverse=True)
        return entity_title, chunks[:top_k]

    # ── Semantic Search ─────────────────────────────────────────────────

    async def _semantic_search(
        self,
        query: str,
        user_id: str,
        collections: list[str],
        top_k: int = 30,
    ) -> list[RetrievedChunk]:
        """Cosine-similarity search via ChromaDB."""
        results: list[RetrievedChunk] = []

        for col_name in collections:
            try:
                where = {"user_id": user_id}
                search = await self.embedding_service.search(
                    query=query,
                    collection_name=col_name,
                    n_results=top_k,
                    where=where,
                )
                if not search or not search.get("ids"):
                    continue

                for i, doc_id in enumerate(search["ids"][0]):
                    doc = search["documents"][0][i] if search.get("documents") else ""
                    dist = search["distances"][0][i] if search.get("distances") else 1.0
                    meta = search["metadatas"][0][i] if search.get("metadatas") else {}

                    score = round(max(0.0, 1.0 - dist), 4)
                    results.append(RetrievedChunk(
                        id=doc_id,
                        text=doc,
                        semantic_score=score,
                        combined_score=score,
                        metadata={**meta, "collection": col_name},
                        source=SourceAttribution(
                            chunk_id=doc_id,
                            source_file=meta.get("source_file", meta.get("title", "")),
                            collection=col_name,
                            score=score,
                            snippet=doc[:200],
                            file_id=meta.get("file_id") or None,
                        ),
                    ))
            except Exception as exc:
                logger.warning(f"Semantic search in {col_name} failed: {exc}")

        results.sort(key=lambda c: c.semantic_score, reverse=True)
        return results

    # ── BM25 Keyword Search ─────────────────────────────────────────────

    def _gather_corpus(
        self, user_id: str, collections: list[str]
    ) -> list[dict[str, Any]]:
        """Pull all documents from target collections for BM25 indexing."""
        corpus: list[dict[str, Any]] = []
        for col_name in collections:
            try:
                where = {"user_id": user_id}
                result = self.chroma.get_all(
                    collection_name=col_name,
                    where=where,
                    limit=2000,
                )
                if not result or not result.get("ids"):
                    continue
                for i, doc_id in enumerate(result["ids"]):
                    doc = result["documents"][i] if result.get("documents") else ""
                    meta = result["metadatas"][i] if result.get("metadatas") else {}
                    corpus.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": {**meta, "collection": col_name},
                    })
            except Exception as exc:
                logger.warning(f"Corpus fetch from {col_name} failed: {exc}")
        return corpus

    def _bm25_search(
        self,
        query: str,
        corpus: list[dict[str, Any]],
        top_k: int = 30,
    ) -> list[RetrievedChunk]:
        """BM25 keyword search over the in-memory corpus."""
        if not corpus:
            return []

        tokenized_corpus = [
            _tokenize(f"{doc['metadata'].get('source_file', '')} {doc['metadata'].get('title', '')} {doc['metadata'].get('category', '')} {doc['text']}")
            for doc in corpus
        ]
        # Filter out empty token lists to avoid BM25 issues
        valid_indices = [i for i, t in enumerate(tokenized_corpus) if t]
        if not valid_indices:
            return []

        valid_corpus = [tokenized_corpus[i] for i in valid_indices]
        valid_docs = [corpus[i] for i in valid_indices]

        bm25 = BM25Okapi(valid_corpus)
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = bm25.get_scores(query_tokens)

        # Normalize scores to 0–1 range
        max_score = float(np.max(scores)) if np.max(scores) > 0 else 1.0
        norm_scores = scores / max_score

        # Get top-K indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        results: list[RetrievedChunk] = []
        for idx in top_indices:
            idx = int(idx)
            if norm_scores[idx] < 0.01:
                continue
            doc = valid_docs[idx]
            meta = doc["metadata"]
            col_name = meta.get("collection", "")
            bm25_score = round(float(norm_scores[idx]), 4)

            results.append(RetrievedChunk(
                id=doc["id"],
                text=doc["text"],
                keyword_score=bm25_score,
                combined_score=bm25_score,
                metadata=meta,
                source=SourceAttribution(
                    chunk_id=doc["id"],
                    source_file=meta.get("source_file", meta.get("title", "")),
                    collection=col_name,
                    score=bm25_score,
                    snippet=doc["text"][:200],
                    file_id=meta.get("file_id") or None,
                ),
            ))
        return results

    # ── Reciprocal Rank Fusion ──────────────────────────────────────────

    @staticmethod
    def _reciprocal_rank_fusion(
        semantic: list[RetrievedChunk],
        keyword: list[RetrievedChunk],
        k: int = 60,
    ) -> list[RetrievedChunk]:
        """
        Merge semantic and BM25 results using Reciprocal Rank Fusion.
        RRF score = Σ 1/(k + rank_i) across each result list.
        """
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, RetrievedChunk] = {}
        sem_scores: dict[str, float] = {}
        kw_scores: dict[str, float] = {}

        # Semantic ranks
        for rank, chunk in enumerate(semantic):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunk_map[chunk.id] = chunk
            sem_scores[chunk.id] = chunk.semantic_score

        # Keyword ranks
        for rank, chunk in enumerate(keyword):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            if chunk.id not in chunk_map:
                chunk_map[chunk.id] = chunk
            kw_scores[chunk.id] = chunk.keyword_score

        # Build fused results
        fused: list[RetrievedChunk] = []
        for cid, rrf_score in sorted(rrf_scores.items(), key=lambda x: -x[1]):
            chunk = chunk_map[cid]
            fused.append(RetrievedChunk(
                id=chunk.id,
                text=chunk.text,
                semantic_score=sem_scores.get(cid, 0.0),
                keyword_score=kw_scores.get(cid, 0.0),
                combined_score=round(rrf_score, 6),
                metadata=chunk.metadata,
                source=chunk.source,
            ))

        return fused

    # ── MMR Reranking ───────────────────────────────────────────────────

    async def _mmr_rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 10,
        lambda_param: float = 0.7,
    ) -> list[RetrievedChunk]:
        """
        Maximal Marginal Relevance — balances relevance and diversity.

        MMR = argmax [ λ · sim(d, q) − (1−λ) · max(sim(d, d_selected)) ]
        """
        if len(candidates) <= top_k:
            return candidates

        # Embed query and all candidate texts
        texts = [c.text for c in candidates]
        query_emb = np.array(
            await self.embedding_service.embeddings.aembed_query(query)
        )
        doc_embs = np.array(
            await self.embedding_service.embeddings.aembed_documents(texts)
        )

        # Cosine similarities: query ↔ each doc
        query_sims = self._cosine_similarity_batch(query_emb, doc_embs)

        selected_indices: list[int] = []
        remaining = set(range(len(candidates)))

        for _ in range(min(top_k, len(candidates))):
            best_idx = -1
            best_mmr = -float("inf")

            for idx in remaining:
                relevance = float(query_sims[idx])

                # Max similarity to already-selected docs
                if selected_indices:
                    selected_embs = doc_embs[selected_indices]
                    redundancy = float(
                        np.max(
                            self._cosine_similarity_batch(doc_embs[idx], selected_embs)
                        )
                    )
                else:
                    redundancy = 0.0

                mmr = lambda_param * relevance - (1 - lambda_param) * redundancy

                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx

            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining.discard(best_idx)

        return [candidates[i] for i in selected_indices]

    @staticmethod
    def _cosine_similarity_batch(
        vec: np.ndarray, matrix: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarity between a vector and each row of a matrix."""
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        vec_norm = vec / (np.linalg.norm(vec) + 1e-10)
        mat_norms = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)
        return mat_norms @ vec_norm

    # ── Metadata Filters ────────────────────────────────────────────────

    @staticmethod
    def _apply_metadata_filters(
        chunks: list[RetrievedChunk],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[RetrievedChunk]:
        """Post-filter retrieved chunks by date range and tags."""
        filtered = chunks

        if date_from:
            filtered = [
                c for c in filtered
                if (c.metadata.get("date") or "9999") >= date_from
            ]

        if date_to:
            filtered = [
                c for c in filtered
                if (c.metadata.get("date") or "0000") <= date_to
            ]

        if tags:
            tag_set = set(t.lower() for t in tags)
            def _has_tag(chunk: RetrievedChunk) -> bool:
                import json
                raw_tags = chunk.metadata.get("tags", "[]")
                chunk_tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
                return bool(tag_set & set(t.lower() for t in chunk_tags))
            filtered = [c for c in filtered if _has_tag(c)]

        return filtered


# ── Legacy Compatibility ────────────────────────────────────────────────
# Keep the old Retriever class name as an alias for backwards compat

class Retriever(HybridRetriever):
    """Backwards-compatible alias."""

    async def retrieve(  # type: ignore[override]
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        category: Optional[EntityCategory] = None,
    ) -> list[SearchResult]:
        """Legacy retrieve that returns SearchResult[] for the old chain."""
        from app.models.schemas import SearchResult

        chunks = await super().retrieve(
            query=query,
            user_id=user_id,
            top_k=top_k,
            category=category,
        )
        return [
            SearchResult(
                id=c.id,
                text=c.text,
                score=c.combined_score,
                metadata=c.metadata,
            )
            for c in chunks
        ]
