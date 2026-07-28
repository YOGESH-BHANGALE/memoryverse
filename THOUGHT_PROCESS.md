# MemoryVerse AI — Design Decisions & Thought Process

## 1. LLM Choice: Groq + Llama 3.3-70B for Structured Extraction

**What the plan said vs. what actually ships:** The initial implementation plan listed GPT-4o. The actual `.env` and runtime configuration use `GROQ_MODEL=llama-3.3-70b-versatile` with a Groq API key. This was a deliberate substitution made during development.

**Why Groq/Llama instead of GPT-4o:**

The core extraction task — parsing raw document text and outputting a structured JSON of skills, certifications, internships, projects, and achievements — is fundamentally a structured extraction problem rather than a long-form reasoning problem. Groq's custom LPU hardware delivers inference for Llama 3.3-70B at token speeds 5–10× faster than standard OpenAI API calls, completely free of per-token API costs during development. For a hackathon project with frequent test document uploads and interactive iteration, this speed and zero-cost profile was a key advantage.

**Tradeoffs accepted:** Llama 3.3-70B occasionally produces slight formatting variance that requires retries in the extraction pipeline. GPT-4o with native function calling offers slightly tighter JSON schema adherence out of the box. However, because the backend relies on LangChain abstractions, switching back to GPT-4o in production requires only updating the model name and API key in `.env`.

---

## 2. Vector Store: ChromaDB

**Why ChromaDB over alternatives (Pinecone, Weaviate, Qdrant, pgvector):**

The primary architecture constraint was **zero external infrastructure setup**. ChromaDB runs in-process with a local persistence directory (`./chroma_db`), requiring no separate database server, cloud credentials, or Docker container for storage.

**Key features leveraged:**

- **Persistent Client Mode:** Data persists across backend service restarts without re-ingestion (`chromadb.PersistentClient`).
- **Native Cosine Similarity Space:** Setting `{"hnsw:space": "cosine"}` at collection creation ensures similarity search operates in standard cosine distance.
- **Metadata Filters:** `where={"user_id": user_id}` enables efficient user-scoped queries directly within vector search without requiring manual post-filtering.
- **Direct ID Retrieval:** `collection.get(ids=[entity_id])` enables O(1) text and metadata fetching for specific entities without needing an embedding calculation step.

---

## 3. Retrieval Strategy: Verified Implementation

The retrieval pipeline in `retriever.py` implements a multi-signal hybrid retrieval architecture:

1. **Semantic Search (`_semantic_search`):** Embeds the incoming query using `all-MiniLM-L6-v2` and queries ChromaDB vector collections, converting cosine distance to a similarity score (`score = max(0.0, 1.0 - distance)`).
2. **Keyword Search (`_bm25_search`):** Gathers all documents across target collections (`_gather_corpus`) and runs an in-memory `BM25Okapi` search to capture exact keyword and acronym matches.
3. **Reciprocal Rank Fusion (`_reciprocal_rank_fusion`):** Combines semantic and keyword rankings using $RRF = \sum \frac{1}{k + r_i}$ (with $k=60$). This rank-based fusion prevents score scaling mismatches between vector similarity and BM25 scores.
4. **Maximal Marginal Relevance (`_mmr_rerank`):** Reranks candidate results using $MMR = \lambda \cdot \text{sim}(d,q) - (1-\lambda) \cdot \max \text{sim}(d, d_{\text{selected}})$ with $\lambda=0.7$, balancing query relevance with result diversity.
5. **Metadata Post-Filtering (`_apply_metadata_filters`):** Applies optional date range and tag filters after ranking.

---

## 4. Entity Relationships: On-Demand Vector Similarity vs. Graph Store

**Architectural evolution:** The initial concept called for a dedicated graph store (`RelationsStore`) and relationship engine. During implementation, this was refined to an on-demand vector similarity model via `GET /api/search/similar/{entity_id}`.

**Why on-demand similarity was chosen:**

1. **Simplified Infrastructure:** Eliminates a separate graph database, removing data synchronization overhead between vector and graph stores.
2. **Dynamic Relationship Discovery:** Rather than relying solely on pre-computed static links generated at ingestion time, `find_similar` executes an on-demand vector query against the full ChromaDB index. When new documents or entities are added, existing entities immediately discover semantic relationships with the new data without re-building a graph index.
3. **Leverages Pre-Existing Embeddings:** Uses the vector representation already generated during ingestion, keeping memory and storage footprints lean.

---

## 5. Original File Storage & Known Limitations

- **Original File Serving (Wired & Implemented):** The ingestion pipeline saves raw document bytes to `UPLOAD_DIR` using a unique `file_id`. The `file_id` is indexed into ChromaDB document metadata for both raw chunks and extracted entities. Source citations returned by `HybridRetriever` include `file_id`, enabling the frontend search UI to render clickable links pointing to `GET /api/files/{file_id}` which streams original PDF/TXT files directly in the browser viewer.
- **In-Memory BM25 Corpus Build:** BM25 corpus construction happens in memory on each search request. While performant for personal-scale knowledge bases (< 1,000 entities), larger enterprise datasets would require a persistent lexical index (e.g., Elasticsearch or Tantivy).
- **Windows Paging File Memory Pressure:** Under high system memory utilization, initial loading of `sentence-transformers` embedding model weights can trigger a Windows virtual memory allocation error. Pre-loading model weights during server startup resolves this issue.
