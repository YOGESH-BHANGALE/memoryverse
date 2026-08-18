"""
Relations API — the explainable knowledge graph.

Three views over the same graph:

* ``GET /api/relations/graph/{user_id}``   — the whole map, for the graph view
* ``GET /api/relations/entity/{entity_id}`` — one entity's connections + reasons
* ``GET /api/relations/legend``            — relation types and what they mean

Every edge returned carries an ``evidence`` list, so the UI can always answer
"why are these two connected?" without guessing from a similarity score.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_relation_engine
from app.core.vectordb.relations import RELATION_LABELS
from app.models.schemas import EntityConnectionsResponse, KnowledgeGraphResponse

router = APIRouter(prefix="/api/relations", tags=["Relations"])


@router.get("/legend")
async def get_legend() -> dict[str, str]:
    """Relation type → plain-English meaning, for the graph legend."""
    return RELATION_LABELS


@router.get("/graph/{user_id}", response_model=KnowledgeGraphResponse)
async def get_graph(
    user_id: str,
    refresh: bool = Query(False, description="Recompute instead of using the cache"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    relation_type: str | None = Query(None, description="Keep only this relation type"),
) -> KnowledgeGraphResponse:
    """
    The user's full knowledge graph — entities, derived career paths, and the
    explainable edges between them.
    """
    engine = get_relation_engine()
    graph = engine.get_user_graph(user_id, refresh=refresh)

    if not graph.nodes:
        raise HTTPException(status_code=404, detail="No data found for this user")

    if min_confidence > 0 or relation_type:
        edges = [
            edge for edge in graph.edges
            if edge.confidence >= min_confidence
            and (not relation_type or edge.relation_type == relation_type)
        ]
        # Filtering edges strands nodes, so drop the ones nothing points at —
        # except when no filter narrowed anything, where the full node set stands.
        kept_ids = {e.source_id for e in edges} | {e.target_id for e in edges}
        graph = graph.model_copy(update={
            "edges": edges,
            "nodes": [n for n in graph.nodes if n.id in kept_ids],
            "relation_counts": {
                rt: sum(1 for e in edges if e.relation_type == rt)
                for rt in {e.relation_type for e in edges}
            },
        })

    return graph


@router.get("/entity/{entity_id}", response_model=EntityConnectionsResponse)
async def get_entity_connections(
    entity_id: str,
    user_id: str = Query("default"),
) -> EntityConnectionsResponse:
    """Everything connected to one entity, each with the reasons why."""
    engine = get_relation_engine()
    response = engine.get_entity_connections(entity_id, user_id)
    if not response.entity_title and not response.connections:
        raise HTTPException(status_code=404, detail="Entity not found in this user's graph")
    return response


@router.post("/rebuild/{user_id}", response_model=KnowledgeGraphResponse)
async def rebuild_graph(user_id: str) -> KnowledgeGraphResponse:
    """
    Force a full graph rebuild and persist it back into entity metadata.

    Ingest does this automatically; this endpoint exists for corpora that were
    ingested before the cross-document engine landed.
    """
    engine = get_relation_engine()
    graph = engine.rebuild_user_graph(user_id)
    if not graph.nodes:
        raise HTTPException(status_code=404, detail="No data found for this user")
    return graph
