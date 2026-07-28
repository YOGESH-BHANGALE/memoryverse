"""
Search API — Phase 4: NL question answering, similar entities, faceted search.

Endpoints:
- POST /api/search/query          — NL question → answer + sources (+ SSE streaming)
- GET  /api/search/similar/{id}   — find similar entities
- POST /api/search/filter         — structured faceted search
- GET  /api/search/               — legacy simple search (backwards compat)
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_rag_chain, get_hybrid_retriever
from app.models.schemas import (
    EntityCategory,
    FacetedSearchRequest,
    FacetedSearchResponse,
    RAGAnswerResponse,
    RAGQueryRequest,
    RetrievedChunk,
    SearchResponse,
    SimilarEntityResponse,
    SourceAttribution,
)

router = APIRouter(prefix="/api/search", tags=["Search"])


# ── POST /api/search/query ──────────────────────────────────────────────

@router.post("/query", response_model=RAGAnswerResponse)
async def search_query(request: RAGQueryRequest):
    """
    Natural language question → RAG answer with source citations.

    Supports:
    - Hybrid retrieval (semantic + BM25)
    - MMR reranking for diversity
    - Metadata filters (category, date_range, tags)
    - SSE streaming (set `stream: true` in request body)

    When `stream=true`, returns a text/event-stream with events:
    - `chunk`: partial answer tokens
    - `sources`: JSON array of source attributions
    - `done`: stream complete
    """
    rag = get_rag_chain()

    if request.stream:
        return StreamingResponse(
            rag.stream_query(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return await rag.query(request)


# ── GET /api/search/similar/{entity_id} ────────────────────────────────

@router.get("/similar/{entity_id}", response_model=SimilarEntityResponse)
async def find_similar(
    entity_id: str,
    top_k: int = Query(10, ge=1, le=50, description="Number of similar entities"),
):
    """
    Find entities similar to a given entity by embedding similarity.
    Searches across all entity collections (skills, projects, certifications, etc.)
    """
    retriever = get_hybrid_retriever()
    entity_title, similar_chunks = await retriever.find_similar(
        entity_id=entity_id,
        top_k=top_k,
    )

    if not entity_title and not similar_chunks:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found in any collection",
        )

    return SimilarEntityResponse(
        entity_id=entity_id,
        entity_title=entity_title,
        similar=similar_chunks,
    )


# ── POST /api/search/filter ────────────────────────────────────────────

@router.post("/filter", response_model=FacetedSearchResponse)
async def faceted_search(request: FacetedSearchRequest):
    """
    Structured faceted search with multiple filter dimensions.

    Supports:
    - Filter by categories (multiple)
    - Filter by tags
    - Filter by date range
    - Filter by minimum importance score
    - Optional semantic query component
    """
    retriever = get_hybrid_retriever()

    all_results: list[RetrievedChunk] = []

    # Determine categories to search
    categories = request.categories if request.categories else list(EntityCategory)

    for category in categories:
        if request.query:
            # Hybrid search with semantic component
            chunks = await retriever.retrieve(
                query=request.query,
                user_id=request.user_id,
                top_k=request.top_k,
                category=category,
                date_from=request.date_from,
                date_to=request.date_to,
                tags=request.tags if request.tags else None,
                use_mmr=False,  # no MMR for faceted — want completeness
            )
            all_results.extend(chunks)
        else:
            # Pure metadata filter (no semantic query)
            from app.core.vectordb.client import ChromaClient
            chroma = ChromaClient()
            col_name = f"{category.value}s"

            try:
                result = chroma.get_all(
                    collection_name=col_name,
                    where={"user_id": request.user_id},
                    limit=request.top_k,
                )
                if result and result.get("ids"):
                    for i, doc_id in enumerate(result["ids"]):
                        doc = result["documents"][i] if result.get("documents") else ""
                        meta = result["metadatas"][i] if result.get("metadatas") else {}
                        all_results.append(RetrievedChunk(
                            id=doc_id,
                            text=doc,
                            combined_score=1.0,
                            metadata={**meta, "collection": col_name},
                            source=SourceAttribution(
                                chunk_id=doc_id,
                                source_file=meta.get("source_file", meta.get("title", "")),
                                collection=col_name,
                                score=1.0,
                                snippet=doc[:200],
                            ),
                        ))
            except Exception:
                continue

    # Post-filter by importance score
    if request.min_importance > 1:
        all_results = [
            r for r in all_results
            if int(r.metadata.get("importance_score", 0)) >= request.min_importance
        ]

    # Post-filter by date range
    if request.date_from:
        all_results = [
            r for r in all_results
            if (r.metadata.get("date") or "9999") >= request.date_from
        ]
    if request.date_to:
        all_results = [
            r for r in all_results
            if (r.metadata.get("date") or "0000") <= request.date_to
        ]

    # Post-filter by tags
    if request.tags:
        tag_set = set(t.lower() for t in request.tags)
        def _has_tag(chunk: RetrievedChunk) -> bool:
            raw_tags = chunk.metadata.get("tags", "[]")
            chunk_tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
            return bool(tag_set & set(t.lower() for t in chunk_tags))
        all_results = [r for r in all_results if _has_tag(r)]

    # Deduplicate by ID
    seen_ids: set[str] = set()
    deduped: list[RetrievedChunk] = []
    for r in all_results:
        if r.id not in seen_ids:
            deduped.append(r)
            seen_ids.add(r.id)

    # Sort by combined score
    deduped.sort(key=lambda r: r.combined_score, reverse=True)
    deduped = deduped[:request.top_k]

    # Build filters-applied summary
    filters = {
        "categories": [c.value for c in categories],
        "tags": request.tags,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "min_importance": request.min_importance,
        "query": request.query,
    }

    return FacetedSearchResponse(
        filters_applied={k: v for k, v in filters.items() if v},
        total_results=len(deduped),
        results=deduped,
    )


# ── GET /api/search/ (legacy) ──────────────────────────────────────────

@router.get("/", response_model=SearchResponse)
async def search_legacy(
    q: str = Query(..., description="Search query"),
    user_id: str = Query("default", description="User ID"),
    top_k: int = Query(10, ge=1, le=50, description="Number of results"),
    category: Optional[str] = Query(None, description="Filter by entity category"),
):
    """
    Legacy semantic search — backwards compatible with Phase 3.
    Returns ranked results AND a RAG-generated answer.
    """
    cat_enum: Optional[EntityCategory] = None
    if category:
        try:
            cat_enum = EntityCategory(category)
        except ValueError:
            pass

    rag = get_rag_chain()
    return await rag.ask(
        query=q,
        user_id=user_id,
        top_k=top_k,
        category=cat_enum,
    )
