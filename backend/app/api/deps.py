"""
API Dependencies — shared dependency injection for FastAPI routes.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.ingestion.extractor import EntityExtractor
from app.core.ingestion.categorizer import Categorizer
from app.core.vectordb.client import ChromaClient
from app.core.vectordb.embeddings import EmbeddingService
from app.core.vectordb.relations import RelationshipEngine
from app.core.timeline.builder import TimelineBuilder
from app.core.rag.chain import RAGChain
from app.core.rag.retriever import HybridRetriever


@lru_cache()
def get_chroma_client() -> ChromaClient:
    return ChromaClient()


@lru_cache()
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


@lru_cache()
def get_extractor() -> EntityExtractor:
    return EntityExtractor()


@lru_cache()
def get_categorizer() -> Categorizer:
    return Categorizer()


@lru_cache()
def get_relation_engine() -> RelationshipEngine:
    return RelationshipEngine()


@lru_cache()
def get_timeline_builder() -> TimelineBuilder:
    return TimelineBuilder()


@lru_cache()
def get_rag_chain() -> RAGChain:
    return RAGChain()


@lru_cache()
def get_hybrid_retriever() -> HybridRetriever:
    return HybridRetriever()
