"""
RAG Chain — Phase 4: RetrievalQA with SSE streaming and source citations.

Features:
- Full hybrid retrieval via HybridRetriever
- MemoryVerse-persona system prompt
- Source citations appended to every answer
- Server-Sent Events (SSE) streaming via async generator
- Non-streaming path for regular JSON responses
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.core.rag.retriever import HybridRetriever
from app.models.schemas import (
    EntityCategory,
    RAGAnswerResponse,
    RAGQueryRequest,
    RetrievedChunk,
    SearchResponse,
    SearchResult,
    SourceAttribution,
)
from app.utils.logger import logger


# ── System Prompt ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are MemoryVerse, an AI assistant that answers questions about a user's \
professional journey from their uploaded documents. You have access to their \
skills, projects, certifications, internships, achievements, and raw document \
chunks.

Rules:
1. Only answer based on the provided context. Do NOT invent facts.
2. If the context is insufficient, say "I don't have enough information \
   in your documents to answer that."
3. Be concise, specific, and reference concrete details from the context.
4. When listing items, use bullet points.
5. Always end your answer with a "Sources:" section listing the source files \
   or entities you drew from (this will be auto-appended, so focus on the \
   answer content).
"""

_HUMAN_PROMPT = """\
Context passages (ranked by relevance):
{context}

---
Question: {question}

Provide a clear, accurate answer based only on the context above:
"""


class RAGChain:
    """
    Phase 4 RAG Chain:
    1. Hybrid retrieve (semantic + BM25 + MMR)
    2. Build prompt with source-attributed context
    3. Generate answer (streaming or batch)
    4. Append source citations
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.retriever = HybridRetriever()
        self.llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=1024,
        )
        self.streaming_llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=1024,
            streaming=True,
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ])
        self.chain = self.prompt | self.llm
        self.streaming_chain = self.prompt | self.streaming_llm

    # ── Full RAG Answer (non-streaming) ─────────────────────────────────

    async def query(self, request: RAGQueryRequest) -> RAGAnswerResponse:
        """
        Full RAG pipeline: hybrid retrieve → generate → cite sources.
        Returns RAGAnswerResponse with answer + source citations.
        """
        # 1. Retrieve
        chunks = await self.retriever.retrieve(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            category=request.category,
            date_from=request.date_from,
            date_to=request.date_to,
            tags=request.tags if request.tags else None,
            use_mmr=request.use_mmr,
            mmr_lambda=request.mmr_lambda,
        )

        # 2. Build context with source markers
        context, sources = self._build_context(chunks)

        # 3. Generate answer
        try:
            response = await self.chain.ainvoke({
                "context": context,
                "question": request.query,
            })
            answer_text = response.content
        except Exception as exc:
            logger.error(f"RAG generation failed: {exc}")
            answer_text = "I couldn't generate an answer at this time."

        # 4. Append source citations
        answer_with_sources = self._append_citations(answer_text, sources)

        logger.info(
            f"RAG query complete: {len(chunks)} chunks, {len(sources)} sources"
        )

        return RAGAnswerResponse(
            query=request.query,
            answer=answer_with_sources,
            sources=sources,
            chunks=chunks,
            retrieval_method="hybrid",
        )

    # ── SSE Streaming ───────────────────────────────────────────────────

    async def stream_query(
        self, request: RAGQueryRequest
    ) -> AsyncGenerator[str, None]:
        """
        Streaming RAG: yields SSE-formatted chunks.

        Event types:
        - "chunk": partial answer token
        - "sources": final source citations JSON
        - "done": stream complete signal
        """
        # 1. Retrieve
        chunks = await self.retriever.retrieve(
            query=request.query,
            user_id=request.user_id,
            top_k=request.top_k,
            category=request.category,
            date_from=request.date_from,
            date_to=request.date_to,
            tags=request.tags if request.tags else None,
            use_mmr=request.use_mmr,
            mmr_lambda=request.mmr_lambda,
        )

        context, sources = self._build_context(chunks)

        # 2. Stream LLM response
        try:
            async for token_event in self.streaming_chain.astream({
                "context": context,
                "question": request.query,
            }):
                token = token_event.content if hasattr(token_event, "content") else str(token_event)
                if token:
                    yield self._sse_event("chunk", token)
        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            yield self._sse_event("chunk", "I couldn't generate an answer at this time.")

        # 3. Emit source citations
        sources_json = json.dumps([s.model_dump() for s in sources])
        yield self._sse_event("sources", sources_json)

        # 4. Done signal
        yield self._sse_event("done", "")

    # ── Legacy Ask (backwards compatible with Phase 3 chain) ────────────

    async def ask(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        category: Optional[EntityCategory] = None,
    ) -> SearchResponse:
        """
        Backwards-compatible method — returns SearchResponse.
        Internally uses the new hybrid retriever.
        """
        request = RAGQueryRequest(
            query=query,
            user_id=user_id,
            top_k=top_k,
            category=category,
        )
        rag_response = await self.query(request)

        # Convert to legacy format
        results = [
            SearchResult(
                id=c.id,
                text=c.text,
                score=c.combined_score,
                metadata=c.metadata,
            )
            for c in rag_response.chunks
        ]

        return SearchResponse(
            query=query,
            results=results,
            answer=rag_response.answer,
        )

    # ── Internal Helpers ────────────────────────────────────────────────

    @staticmethod
    def _build_context(
        chunks: list[RetrievedChunk],
    ) -> tuple[str, list[SourceAttribution]]:
        """Build the LLM context string and collect source attributions."""
        context_parts: list[str] = []
        sources: list[SourceAttribution] = []
        seen_sources: set[str] = set()

        for i, chunk in enumerate(chunks, 1):
            source_label = ""
            if chunk.source:
                source_label = f" [Source: {chunk.source.source_file}]"
                if chunk.source.chunk_id not in seen_sources:
                    sources.append(chunk.source)
                    seen_sources.add(chunk.source.chunk_id)

            context_parts.append(
                f"[{i}] (score: {chunk.combined_score:.3f}){source_label}\n"
                f"{chunk.text}"
            )

        context = "\n\n".join(context_parts) if context_parts else (
            "No relevant information found in the user's documents."
        )
        return context, sources

    @staticmethod
    def _append_citations(answer: str, sources: list[SourceAttribution]) -> str:
        """Append a formatted 'Sources:' block to the answer."""
        if not sources:
            return answer

        citation_lines = []
        seen = set()
        for src in sources:
            label = src.source_file or src.collection
            if label not in seen:
                citation_lines.append(
                    f"• {label} ({src.collection}, relevance: {src.score:.0%})"
                )
                seen.add(label)

        citations = "\n".join(citation_lines)
        return f"{answer}\n\n📎 **Sources:**\n{citations}"

    @staticmethod
    def _sse_event(event: str, data: str) -> str:
        """Format a Server-Sent Event string."""
        return f"event: {event}\ndata: {data}\n\n"
