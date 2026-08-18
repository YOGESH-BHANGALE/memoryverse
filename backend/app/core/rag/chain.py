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
from app.core.rag.intent import detect_intent
from app.core.rag.retriever import HybridRetriever
from app.models.schemas import (
    EntityCategory,
    RAGAnswerResponse,
    RAGQueryRequest,
    RetrievedChunk,
    SearchResponse,
    SearchResult,
    SourceAttribution,
    SourceDocument,
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
        from app.api.deps import get_hybrid_retriever
        self.retriever = get_hybrid_retriever()
        self.llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=2048,
        )
        self.streaming_llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=2048,
            streaming=True,
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ])
        self.chain = self.prompt | self.llm
        self.streaming_chain = self.prompt | self.streaming_llm
        # Retrieval keeps working when the generation model is retired or rate
        # limited, so the failure is invisible in the logs until every answer
        # reads "I couldn't generate an answer at this time". The extractor
        # already fell back to a second model; the answer path now does too.
        self.fallback_chain = self.prompt | ChatGroq(
            model=settings.groq_fallback_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=2048,
        )

    async def _generate(self, context: str, question: str) -> str:
        """Generate an answer, falling back to the secondary model on error."""
        try:
            response = await self.chain.ainvoke(
                {"context": context, "question": question}
            )
            return response.content
        except Exception as exc:
            settings = get_settings()
            logger.warning(
                f"RAG generation failed on {settings.groq_model} ({exc}). "
                f"Falling back to {settings.groq_fallback_model}..."
            )
        try:
            response = await self.fallback_chain.ainvoke(
                {"context": context, "question": question}
            )
            return response.content
        except Exception as exc:
            logger.error(f"RAG generation fallback failed: {exc}")
            return "I couldn't generate an answer at this time."

    # ── Full RAG Answer (non-streaming) ─────────────────────────────────

    async def query(self, request: RAGQueryRequest) -> RAGAnswerResponse:
        """
        Full RAG pipeline: hybrid retrieve → generate → cite sources.
        Returns RAGAnswerResponse with answer + source citations.
        """
        # 0. Read the question's intent. An explicit `category` filter overrides
        #    it, matching the retriever, so the router never fights a caller that
        #    already knows what it wants.
        intent = detect_intent(request.query) if not request.category else None

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

        # 2. A question about a *document* ("show my latest resume") is answered
        #    by naming the file, not by reciting facts scraped out of it. Fetch
        #    the matching originals so the answer can name them and the client
        #    can link to /api/files/{file_id}.
        documents: list[SourceDocument] = []
        if intent and intent.wants_documents:
            documents = await self.retriever.find_documents(
                user_id=request.user_id,
                hints=intent.document_hints,
                latest_only=intent.wants_latest,
                categories=intent.categories,
            )

        # 3. Build context with source markers
        context, sources = self._build_context(chunks)
        if documents:
            # The document's own text has to be in the context, or the model
            # answers "I don't have enough information" while the file it needs
            # is sitting right there in the list above.
            doc_chunks = await self.retriever.chunks_for_documents(
                user_id=request.user_id, documents=documents
            )
            if doc_chunks:
                chunks = self._merge_chunks(doc_chunks, chunks, request.top_k)
                # Context keeps the merged set so the model has rich material to
                # answer from. Citations, though, are scoped to the resolved
                # documents: a "latest resume" answer should cite that résumé —
                # not a GitHub link or a different résumé that global retrieval
                # happened to surface on the word "resume".
                context, _ = self._build_context(chunks)
                _, sources = self._build_context(doc_chunks)
            context = self._prepend_documents(context, documents)

        # 4. Generate answer
        answer_text = await self._generate(context, request.query)

        # 5. Append source citations
        answer_with_sources = self._append_citations(answer_text, sources)

        logger.info(
            f"RAG query complete: {len(chunks)} chunks, {len(sources)} sources, "
            f"intent={intent.describe() if intent else 'explicit-category'}"
        )

        return RAGAnswerResponse(
            query=request.query,
            answer=answer_with_sources,
            sources=sources,
            chunks=chunks,
            retrieval_method="hybrid",
            intent=intent.describe() if intent else f"category={request.category.value}",
            documents=documents,
        )

    # ── SSE Streaming ───────────────────────────────────────────────────

    async def stream_query(
        self, request: RAGQueryRequest
    ) -> AsyncGenerator[str, None]:
        """
        Streaming RAG: yields SSE-formatted chunks.

        Event types:
        - "chunk": partial answer token
        - "intent": what the query router read from the question
        - "documents": matching original files, for document-level questions
        - "sources": final source citations JSON
        - "done": stream complete signal
        """
        intent = detect_intent(request.query) if not request.category else None
        yield self._sse_event(
            "intent",
            intent.describe() if intent else f"category={request.category.value}",
        )

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

        documents: list[SourceDocument] = []
        if intent and intent.wants_documents:
            documents = await self.retriever.find_documents(
                user_id=request.user_id,
                hints=intent.document_hints,
                latest_only=intent.wants_latest,
                categories=intent.categories,
            )
        if documents:
            doc_chunks = await self.retriever.chunks_for_documents(
                user_id=request.user_id, documents=documents
            )
            if doc_chunks:
                chunks = self._merge_chunks(doc_chunks, chunks, request.top_k)
                # Context keeps the merged set so the model has rich material to
                # answer from. Citations, though, are scoped to the resolved
                # documents: a "latest resume" answer should cite that résumé —
                # not a GitHub link or a different résumé that global retrieval
                # happened to surface on the word "resume".
                context, _ = self._build_context(chunks)
                _, sources = self._build_context(doc_chunks)
            context = self._prepend_documents(context, documents)
            # Emitted before the answer so the UI can show download links
            # immediately rather than waiting for generation to finish.
            yield self._sse_event("documents", json.dumps(
                [d.model_dump() for d in documents]
            ))

        # 2. Stream LLM response
        emitted = False
        try:
            async for token_event in self.streaming_chain.astream({
                "context": context,
                "question": request.query,
            }):
                token = token_event.content if hasattr(token_event, "content") else str(token_event)
                if token:
                    emitted = True
                    yield self._sse_event("chunk", token)
        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            if emitted:
                # Tokens already reached the client; replaying a fresh answer
                # would splice two half-answers together, so stop here.
                yield self._sse_event("chunk", "\n\n[answer truncated]")
            else:
                # Nothing was sent yet, so the fallback model can answer cleanly.
                yield self._sse_event(
                    "chunk", await self._generate(context, request.query)
                )

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
    def _merge_chunks(
        primary: list[RetrievedChunk],
        secondary: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """
        Put the requested document's chunks first, then fill with search results.

        The search results are kept rather than discarded so a question like
        "show internship documents" still benefits from the internship *entities*
        that hybrid retrieval found, while the offer letters themselves lead.
        """
        seen = {c.id for c in primary}
        merged = list(primary)
        for chunk in secondary:
            if chunk.id not in seen:
                merged.append(chunk)
                seen.add(chunk.id)
        return merged[:max(top_k, len(primary))]

    @staticmethod
    def _prepend_documents(context: str, documents: list[SourceDocument]) -> str:
        """
        Put the matching original files at the top of the context.

        A document question needs the file's identity — name, type, when it was
        uploaded — and none of that is in the chunk text, which is just the
        document's *contents*. Without this block the LLM answered "show my
        latest resume" by reciting resume bullet points and never named the file.
        """
        lines = ["Original documents on file (most recent first):"]
        for doc in documents:
            bits = [doc.source_file or "(unnamed)"]
            if doc.file_type:
                bits.append(doc.file_type.upper())
            if doc.uploaded_at:
                bits.append(f"uploaded {doc.uploaded_at[:10]}")
            if doc.download_url:
                bits.append(f"download: {doc.download_url}")
            lines.append("- " + " | ".join(bits))
        return "\n".join(lines) + "\n\n" + context

    @staticmethod
    def _sse_event(event: str, data: str) -> str:
        """
        Format a Server-Sent Event string.

        Per the SSE spec each line of the payload needs its own "data:" field;
        the receiver rejoins them with "\\n". Emitting a raw multi-line payload
        silently truncates the event at the first newline (and an embedded blank
        line terminates the event early), which dropped newlines and bullet
        lists out of streamed answers.
        """
        data_block = "".join(f"data: {line}\n" for line in data.split("\n"))
        return f"event: {event}\n{data_block}\n"
