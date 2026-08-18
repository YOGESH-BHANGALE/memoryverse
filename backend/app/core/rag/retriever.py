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
from datetime import datetime
from typing import Any, Optional, Sequence

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.vectordb.client import ChromaClient, COLLECTIONS, collection_for_category
from app.core.vectordb.embeddings import EmbeddingService
from app.core.rag.intent import QueryIntent, detect_intent
from app.models.schemas import (
    EntityCategory,
    RetrievedChunk,
    SearchResult,
    SourceAttribution,
    SourceDocument,
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
        use_intent: bool = True,
    ) -> list[RetrievedChunk]:
        """
        Hybrid retrieve:
        1. Route the query to the categories it names (see ``core.rag.intent``)
        2. Semantic search across the resulting collections
        3. BM25 keyword search across the same docs
        4. RRF merge
        5. Optional MMR reranking
        6. Metadata post-filters (date, tags)

        An explicit ``category`` always wins over the detected intent; the router
        only fills in what the caller left unspecified. Pass ``use_intent=False``
        to search everything regardless of what the query names.
        """
        intent = detect_intent(query) if use_intent and not category else QueryIntent()

        # Determine collections
        if category:
            collections = [collection_for_category(category)]
        elif intent.categories:
            # Restricting to the named categories is the whole point of the
            # router: "show all my certificates" used to return one certificate
            # in eight results because every other collection, and the unlabelled
            # raw chunks, competed for the same slots.
            collections = [collection_for_category(c) for c in intent.categories]
            if intent.wants_documents:
                collections.append("raw_chunks")
        elif intent.wants_documents:
            # A pure document request ("show my latest resume") names no category,
            # so the answer lives in the document text rather than in extracted
            # entities. Searching everything here buried the resume chunks under
            # unrelated skills and achievements.
            collections = ["raw_chunks"]
        else:
            collections = list(COLLECTIONS)

        if intent.matched:
            logger.info(f"Query intent: {intent.describe()} (matched {list(intent.matched)})")

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
        user_id: str | None = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        """
        Find entities similar to a given entity_id by embedding similarity.

        When ``user_id`` is omitted it is read off the seed entity's own
        metadata. Either way the search is scoped to that one user: collections
        are shared across users, so an unscoped query returned other people's
        entities as "similar".
        """
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
                    user_id = user_id or meta.get("user_id")
                    break
            except Exception:
                continue

        if not entity_text:
            return "", []

        where = {"user_id": user_id} if user_id else None

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
                    where=where,
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

    async def find_documents(
        self,
        user_id: str = "default",
        hints: Sequence[str] = (),
        latest_only: bool = False,
        limit: int = 20,
        categories: Sequence[EntityCategory] = (),
    ) -> list[SourceDocument]:
        """
        List the user's original uploaded documents, newest first.

        "Show my latest resume" is not an entity query — no amount of ranking over
        extracted skills answers it. It needs the file itself, so this walks the
        raw chunk metadata to recover the distinct (file_id, source_file) pairs
        that were ingested for this user.

        Narrowing happens in three steps, most specific first:

        1. ``hints`` are matched against filenames, first hit wins, so a query can
           offer a specific hint ("offer letter") before a broader one
           ("internship"). This is the best signal when it fires, because uploads
           are usually named for what they are.
        2. Failing that, ``categories`` narrows to the documents that actually
           produced entities in those categories. "show internship documents"
           previously listed every file the user had ever ingested — a GitHub
           profile link included — because no filename contained "internship".
           The internships live inside two resumes, and those two resumes are the
           honest answer.
        3. Otherwise the full list is returned: "my latest report" should still
           show what documents exist rather than nothing at all.

        Recency comes from the stored original's mtime, because chunk metadata
        carries no ingest timestamp. Files that are no longer on disk are still
        listed, just undated and last: the record of the ingest is real even if
        the original was cleaned up.
        """
        try:
            payload = self.chroma.get_all(
                collection_name="raw_chunks",
                where={"user_id": user_id},
                limit=5000,
            )
        except Exception as exc:
            logger.warning(f"Document listing failed: {exc}")
            return []

        metas = (payload or {}).get("metadatas") or []
        docs: dict[str, SourceDocument] = {}
        for meta in metas:
            meta = meta or {}
            source_file = meta.get("source_file") or ""
            file_id = meta.get("file_id") or ""
            # A link ingest has a source URL but no file_id; key on whichever
            # identifies the document so both kinds are listed exactly once.
            key = file_id or source_file
            if not key:
                continue
            existing = docs.get(key)
            if existing:
                existing.chunk_count += 1
                continue
            resolved_id, uploaded_at = self._resolve_original(file_id, source_file)
            docs[key] = SourceDocument(
                file_id=resolved_id,
                source_file=source_file,
                file_type=meta.get("file_type") or "",
                chunk_count=1,
                uploaded_at=uploaded_at,
            )

        # What each document actually yielded. Two uses: the per-document
        # "N extracted" figure, and the category fallback below.
        entity_counts, docs_by_category = self._entity_provenance(user_id)
        for key, doc in docs.items():
            doc.entity_count = entity_counts.get(key, 0) or entity_counts.get(
                doc.source_file, 0
            )

        results = list(docs.values())

        def _keys(doc: SourceDocument) -> tuple[str, ...]:
            # A document is identified by file_id in some chunk metadata and by
            # filename in others (pre-file_id ingests), so match on either.
            return tuple(k for k in (doc.file_id, doc.source_file) if k)

        narrowed_by_hint = False
        for hint in hints:
            needle = hint.lower().strip()
            if not needle:
                continue
            narrowed = [d for d in results if needle in d.source_file.lower()]
            if narrowed:
                results = narrowed
                narrowed_by_hint = True
                break

        if not narrowed_by_hint and categories:
            wanted: set[str] = set()
            for category in categories:
                wanted |= docs_by_category.get(getattr(category, "value", category), set())
            if wanted:
                narrowed = [d for d in results if wanted.intersection(_keys(d))]
                if narrowed:
                    results = narrowed

        # Undated documents sort last: a file with no mtime is not evidence of
        # being the newest, and letting one win "latest" returned the wrong file.
        results.sort(key=lambda d: d.uploaded_at or "", reverse=True)
        return results[:1] if latest_only and results else results[:limit]

    def _entity_provenance(
        self, user_id: str
    ) -> tuple[dict[str, int], dict[str, set[str]]]:
        """
        Map documents to the entities extracted from them.

        Returns ``(entity_count_by_document_key, document_keys_by_category)``,
        where a document is keyed by *both* its ``file_id`` and its filename.

        Keying on the filename as well is what makes this work in practice.
        Entity metadata records the file_id of the upload it came from, but the
        same document re-uploaded gets a fresh id, and the document listing
        resolves a name to the newest copy on disk — so matching on file_id alone
        silently missed every entity extracted from an earlier copy. Copies of one
        document are one document as far as "which file did this come from?" goes.

        A failed collection read is logged and skipped rather than raised: this
        only enriches a document listing, and losing a count is a far better
        outcome than losing the download links.
        """
        counts: dict[str, int] = {}
        by_category: dict[str, set[str]] = {}
        # Built once rather than globbing per entity: with a few hundred entities
        # that was a few hundred directory scans for one document listing.
        names = self._original_names()

        for collection in COLLECTIONS:
            if collection == "raw_chunks":
                continue  # chunks are the source text, not extracted entities
            try:
                payload = self.chroma.get_all(
                    collection_name=collection,
                    where={"user_id": user_id},
                    limit=5000,
                )
            except Exception as exc:
                logger.warning(f"Provenance read of {collection} failed: {exc}")
                continue

            for meta in (payload or {}).get("metadatas") or []:
                meta = meta or {}
                file_id = meta.get("file_id") or ""
                source_file = meta.get("source_file") or names.get(file_id, "")
                category = meta.get("category") or ""
                for key in (k for k in (file_id, source_file) if k):
                    counts[key] = counts.get(key, 0) + 1
                    if category:
                        by_category.setdefault(category, set()).add(key)

        return counts, by_category

    async def chunks_for_documents(
        self,
        user_id: str,
        documents: Sequence[SourceDocument],
        limit: int = 12,
    ) -> list[RetrievedChunk]:
        """
        Pull the raw text chunks belonging to specific documents, in reading order.

        A document question needs that document's own contents as context.
        Semantic search cannot supply it: "show my latest resume" shares no
        distinctive term with the resume's body text, so the retrieved chunks came
        from whatever else happened to score highest — and the model correctly
        answered that it had no resume content to work from.
        """
        if not documents:
            return []

        wanted_ids = {d.file_id for d in documents if d.file_id}
        wanted_names = {d.source_file for d in documents if d.source_file}

        try:
            payload = self.chroma.get_all(
                collection_name="raw_chunks",
                where={"user_id": user_id},
                limit=5000,
            )
        except Exception as exc:
            logger.warning(f"Document chunk fetch failed: {exc}")
            return []

        ids = (payload or {}).get("ids") or []
        texts = (payload or {}).get("documents") or []
        metas = (payload or {}).get("metadatas") or []

        rows: list[tuple[int, RetrievedChunk]] = []
        for i, chunk_id in enumerate(ids):
            meta = (metas[i] if i < len(metas) else {}) or {}
            # Match on file_id where the chunk has one, and on filename otherwise,
            # so documents whose chunks predate file_id persistence still resolve.
            if not (
                (meta.get("file_id") or "") in wanted_ids
                or (meta.get("source_file") or "") in wanted_names
            ):
                continue
            text = texts[i] if i < len(texts) else ""
            try:
                order = int(meta.get("chunk_index") or 0)
            except (TypeError, ValueError):
                order = 0
            resolved_id = meta.get("file_id") or next(
                (d.file_id for d in documents
                 if d.source_file == meta.get("source_file")), ""
            )
            rows.append((order, RetrievedChunk(
                id=chunk_id,
                text=text,
                combined_score=1.0,
                metadata={**meta, "collection": "raw_chunks"},
                source=SourceAttribution(
                    chunk_id=chunk_id,
                    source_file=meta.get("source_file", ""),
                    collection="raw_chunks",
                    score=1.0,
                    snippet=text[:200],
                    file_id=resolved_id or None,
                ),
            )))

        rows.sort(key=lambda row: row[0])
        return [chunk for _, chunk in rows[:limit]]

    @staticmethod
    def _original_names() -> dict[str, str]:
        """
        Map every stored upload id to the filename it was stored under.

        Originals live at ``{uuid}_{original name}``, so the name is right there
        in the path. A missing or unreadable upload directory yields an empty map
        rather than an error: that only costs the entity counts, not the listing.
        """
        try:
            from app.config import get_settings
            return {
                path.name.split("_", 1)[0]: path.name.split("_", 1)[1]
                for path in get_settings().upload_path.iterdir()
                if path.is_file() and "_" in path.name
            }
        except Exception as exc:
            logger.warning(f"Upload directory scan failed: {exc}")
            return {}

    @staticmethod
    def _resolve_original(
        file_id: str, source_file: str
    ) -> tuple[str, Optional[str]]:
        """
        Locate a document's stored original, returning its id and upload time.

        Originals are saved as ``{uuid}_{original name}``. Chunks ingested before
        file_id was persisted carry only a filename, which left their documents
        with no download link even though the file was sitting in the upload
        directory — so fall back to matching the name and recover the id from it.

        Where several uploads share a name (the same file re-uploaded during
        testing) the newest is chosen. They are copies of one document, so any of
        them serves the same bytes; the newest is the one the user last supplied.
        Link ingests have no stored file and resolve to no id, which is correct —
        a URL is not a file this API can serve.
        """
        try:
            from app.config import get_settings
            upload_dir = get_settings().upload_path

            if file_id:
                matches = [p for p in upload_dir.glob(f"{file_id}*") if p.is_file()]
                if matches:
                    return file_id, datetime.fromtimestamp(
                        matches[0].stat().st_mtime
                    ).isoformat()

            # Not on disk under that id (or no id at all). URLs never are.
            if not source_file or source_file.startswith(("http://", "https://")):
                return file_id, None

            suffix = f"_{source_file}"
            candidates = [
                p for p in upload_dir.iterdir()
                if p.is_file() and p.name.endswith(suffix)
            ]
            if not candidates:
                return file_id, None
            newest = max(candidates, key=lambda p: p.stat().st_mtime)
            recovered = newest.name.split("_", 1)[0]
            return (
                file_id or recovered,
                datetime.fromtimestamp(newest.stat().st_mtime).isoformat(),
            )
        except Exception:
            return file_id, None

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
