# MemoryVerse AI — Implementation Plan
> Hackathon Build Tracker | Stack: FastAPI + ChromaDB + LangChain + Next.js

---

## 🏁 Phase 0 — Project Bootstrap
- [x] Define folder structure (backend/ + frontend/)
- [x] Create requirements.txt and package.json
- [x] Setup .env files (OpenAI key, ChromaDB path, CORS origins)
- [ ] Initialize Git repository
- [ ] Verify Python 3.11+ and Node 18+ environments

---

## 🔵 Phase 1 — Data Ingestion & Categorization

### 1.1 File Parsing (`backend/app/core/ingestion/parser.py`)
- [x] Implement `PDFParser` using `pypdf2` + `pdfplumber` fallback
- [x] Implement `TextParser` for raw .txt files
- [x] Implement `DocxParser` using `python-docx`
- [x] Return normalized `RawDocument` schema (text, filename, file_type, page_count)

### 1.2 LLM Structured Extraction (`backend/app/core/ingestion/extractor.py`)
- [x] Define LangChain extraction chain with structured output parser
- [x] Build Pydantic output schema (Certification, Skill, Project, Internship, Achievement)
- [x] Use GPT-4o with function calling for zero-shot extraction
- [x] Handle partial extractions gracefully (optional fields)

### 1.3 Categorizer (`backend/app/core/ingestion/categorizer.py`)
- [x] Route extracted entities to typed buckets
- [x] Assign `category` and `importance_score` (1-10) per entity
- [x] Validate output against Pydantic models

### 1.4 Ingest API Route (`backend/app/api/routes/ingest.py`)
- [x] `POST /api/ingest/upload` — multipart file upload
- [x] `GET  /api/ingest/status/{job_id}` — processing status
- [x] Return structured `IngestionResult` JSON

---

## 🟣 Phase 2 — Relationship Engine & Vector DB

### 2.1 ChromaDB Client (`backend/app/core/vectordb/client.py`)
- [x] Initialize persistent ChromaDB client
- [x] Create collections: skills, projects, certifications, internships, achievements, raw_chunks
- [x] Implement upsert, query, delete helpers

### 2.2 Embeddings (`backend/app/core/vectordb/embeddings.py`)
- [x] Use `text-embedding-3-small` via LangChain embeddings wrapper
- [x] Chunk raw document text (512 tokens, 50 overlap)
- [x] Attach metadata per chunk

### 2.3 Relationship Engine (`backend/app/core/vectordb/relations.py`)
- [x] Build entity graph (Skill→Project, Project→Certificate, Internship→Skill)
- [x] Store relations as metadata cross-references in ChromaDB
- [x] Implement `get_related_entities(entity_id)` traversal
- [x] Compute `relevance_score` between linked entities

---

## 🟢 Phase 3 — Journey Timeline API

### 3.1 Timeline Builder (`backend/app/core/timeline/builder.py`)
- [x] Aggregate all dated entities from ChromaDB
- [x] Sort chronologically, resolve date ambiguities
- [x] Group by year and category
- [x] Enrich each milestone with related entities

### 3.2 Timeline API Route (`backend/app/api/routes/timeline.py`)
- [x] `GET /api/timeline/{user_id}` — full chronological JSON
- [x] `GET /api/timeline/{user_id}?year=2023` — year filter
- [x] `GET /api/timeline/{user_id}?category=projects` — category filter
- [x] Return `TimelineResponse`

---

## 🟠 Phase 4 — Smart Retrieval (RAG)

### 4.1 Retriever (`backend/app/core/rag/retriever.py`)
- [x] Implement hybrid search: semantic (ChromaDB) + keyword (BM25)
- [x] Top-K retrieval with MMR (Maximal Marginal Relevance) reranking
- [x] Filter by category, date_range, tags metadata
- [x] Return `RetrievedChunk[]` with source attribution
- [x] Reciprocal Rank Fusion (RRF) for merging signal types

### 4.2 RAG Chain (`backend/app/core/rag/chain.py`)
- [x] Build LangChain RetrievalQA chain with MemoryVerse persona
- [x] System prompt: "You are MemoryVerse, answering questions about a user's professional journey…"
- [x] Stream responses via SSE (Server-Sent Events)
- [x] Append source citations to every answer

### 4.3 Search API Routes (`backend/app/api/routes/search.py`)
- [x] `POST /api/search/query` — NL question → answer + sources (+ SSE streaming)
- [x] `GET  /api/search/similar/{entity_id}` — find similar entities
- [x] `POST /api/search/filter` — structured faceted search
- [x] Legacy `GET /api/search/` preserved for backwards compat

---

## 🔴 Phase 5 — Frontend (Next.js)

### 5.1 Core Setup
- [x] Next.js 14 App Router + Tailwind CSS + Framer Motion
- [x] Axios API client with base URL from env
- [x] Global state with Zustand (`lib/store.ts`)

### 5.2 Pages
- [x] `/` — Premium landing page with product hero & animations
- [x] `/upload` — Pipeline visualization & uploader
- [x] `/dashboard` — Identity overview: skills graph, stats cards, top skills
- [x] `/timeline` — Interactive vertical timeline with filters
- [x] `/search` — Conversational RAG search chat interface

### 5.3 Key Components
- [x] `<FileUploader />` — react-dropzone + upload progress bar
- [x] `<TimelineView />` — Framer Motion animated milestones & pulsing dots
- [x] `<SearchBar />` — AI chat interface with auto-resize & streaming support
- [x] `<SkillGraph />` — Recharts radar & bar charts for skill visualization
- [x] `<EntityCard />` — Reusable animated card for any entity type

---

## 🟢 Phase 6 — Integration & Polish

- [x] CORS configuration for frontend <-> backend (Configured in `main.py`)
- [x] Error boundary and loading states on all routes (`error.tsx`, `loading.tsx`)
- [x] Docker Compose for one-command local startup (`docker-compose.yml`, `frontend/Dockerfile`)
- [x] API documentation via FastAPI /docs (Swagger) (Configured metadata in `main.py`)
- [x] README with setup instructions + demo GIF (Updated `README.md`)
- [x] Seed demo data script for hackathon judges (`scripts/seed_demo.py`)

---

## ✅ Implementation Complete

All Phases 0–6 have been successfully implemented with full working code. The hackathon project is complete!
