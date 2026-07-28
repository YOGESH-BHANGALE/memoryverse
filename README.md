# MemoryVerse AI 🧠

> AI-powered personal knowledge management — upload your resume, certificates,
> and project docs, then explore your journey through an interactive timeline
> and intelligent search.

## Stack

| Layer       | Technology                                  |
|-------------|---------------------------------------------|
| Backend     | FastAPI + Python 3.11                       |
| LLM         | Groq (Llama 3.3-70B-versatile) + LangChain  |
| Embeddings  | Sentence-Transformers (`all-MiniLM-L6-v2`)  |
| Vector DB   | ChromaDB (persistent)                       |
| Frontend    | Next.js 14 + TypeScript + TailwindCSS       |

## Quick Start

### 1. Backend

```bash
cd backend
cp .env.example .env          # add your Groq API key
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

### 3. Docker (full stack)

```bash
docker-compose up --build
```

## 🎥 Demo

| Homepage | Upload & Extraction | Timeline | Related Connections | AI Search |
|----------|---------------------|----------|---------------------|-----------|
| ![Homepage](docs/assets/homepage.png) | ![Extraction](docs/assets/extraction-complete.png) | ![Timeline](docs/assets/timeline-page.png) | ![Related Entities](docs/assets/related-entities.png) | ![Search](docs/assets/search-results.png) |

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional)
- Groq API Key

### Option A: Quick Start (Docker)
1. Add your Groq API key to `backend/.env`
2. Run `docker-compose up --build`
3. Access the frontend at [http://localhost:3000](http://localhost:3000)

### Option B: Local Development
**Backend**
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
# Set GROQ_API_KEY in .env
uvicorn app.main:app --reload
```
API Documentation (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)

**Frontend**
```bash
cd frontend
npm install
npm run dev
```
App: [http://localhost:3000](http://localhost:3000)

### Seeding Demo Data
To quickly test the platform without uploading documents, you can run the seed script:
```bash
cd backend
python -m scripts.seed_demo
```

## API Endpoints

| Method | Endpoint                          | Description                     |
| ------ | --------------------------------- | ------------------------------- |
| POST   | `/api/ingest/upload`              | Upload PDF/DOCX/TXT             |
| POST   | `/api/ingest/link`                | Ingest data from a web URL      |
| GET    | `/api/ingest/status/{job_id}`     | Get parsing status              |
| GET    | `/api/timeline/{user_id}`         | Get chronological timeline      |
| POST   | `/api/search/query`               | Streaming RAG + Hybrid Search   |
| POST   | `/api/search/filter`              | Faceted metadata search         |
| GET    | `/api/search/similar/{entity_id}` | Find related/similar entities   |
| GET    | `/api/search/?q=...`              | Legacy semantic search          |
| GET    | `/api/identity/{user_id}`         | User profile summary            |
| GET    | `/health`                         | Health check                    |

## Architecture

```mermaid
flowchart TD
    %% Define Styles
    classDef frontend fill:#3b82f6,stroke:#2563eb,stroke-width:2px,color:#fff
    classDef backend fill:#10b981,stroke:#059669,stroke-width:2px,color:#fff
    classDef external fill:#f59e0b,stroke:#d97706,stroke-width:2px,color:#fff
    classDef data fill:#8b5cf6,stroke:#7c3aed,stroke-width:2px,color:#fff
    classDef api fill:#6366f1,stroke:#4f46e5,stroke-width:2px,color:#fff,stroke-dasharray: 5 5

    %% Actors
    User([User])

    %% Frontend Components
    subgraph Frontend [Frontend Application - Next.js]
        UI[React Components / UI]
        State[Zustand Store]
        UI <--> State
    end
    class Frontend frontend

    %% Backend Components
    subgraph Backend [FastAPI Backend]
        API_Upload[Ingestion API]
        API_Timeline[Timeline API]
        API_Search[Search API]

        Parser[Document Parser / HTML Scraper]
        LLM_Extract[LLM Extractor]
        Categorizer[Rule-based Categorizer]
        Embedder[Embedding Engine]
        RelationEngine["RelationshipEngine - tag/keyword overlap\nwrites relations field to ChromaDB metadata"]
        TimelineBuilder["TimelineBuilder - reads all entity\ncollections from ChromaDB"]
        RAGChain[RAG Chain]
        HybridSearch[Hybrid Search - Semantic + BM25 + MMR]
        SimilarSearch["find_similar - on-demand cosine\nsimilarity query against ChromaDB"]

        API_Upload --> Parser
        Parser --> LLM_Extract
        LLM_Extract --> Categorizer
        Categorizer --> Embedder
        Categorizer --> RelationEngine

        API_Timeline --> TimelineBuilder

        API_Search --> RAGChain
        API_Search --> SimilarSearch
        RAGChain --> HybridSearch
    end
    class Backend backend
    class API_Upload,API_Timeline,API_Search api

    %% Data Stores - single persistent store, no separate relations store
    subgraph Data ["ChromaDB - Single Persistent Store"]
        Chroma["Collections: skills, projects, certifications,\ninternships, achievements, raw_chunks\n\nEach entity document stores:\n- embedding vector\n- typed metadata\n- relations JSON field (tag/keyword overlap links)"]
    end
    class Data data

    %% External Services
    LLM_API((Groq / OpenAI API))
    class LLM_API external

    %% Connections
    User <-->|HTTP / SSE| UI
    State <-->|REST| API_Upload
    State <-->|REST| API_Timeline
    State <-->|SSE Stream| API_Search

    LLM_Extract <-->|Prompt / Function Call| LLM_API
    RAGChain <-->|Generation Prompt| LLM_API

    Embedder -->|Store vectors + typed metadata| Chroma
    RelationEngine -->|Update relations field in entity metadata| Chroma

    TimelineBuilder <-->|get_all across all collections| Chroma
    HybridSearch <-->|query - semantic + BM25 rerank| Chroma
    SimilarSearch <-->|query - cosine similarity by entity_id| Chroma
```

## ✅ Resolved Improvements & Fixes

| Feature / Bug | Status | Technical Reality & Solution |
|---------------|--------|------------------------------|
| **Original File Retrieval** | **Resolved** | Upload pipeline saves raw file bytes to `UPLOAD_DIR` using a `file_id` indexed in ChromaDB metadata. Citations in Ask AI render clickable `GET /api/files/{file_id}` links opening original documents in browser. |
| **`document_to_entity` Parsing Crash** | **Resolved** | Fixed `json.JSONDecodeError` crash on empty string metadata from demo-seeded entities which previously dropped skills/projects/certifications from the timeline. |

## ⚠️ Known Limitations & Technical Realities

| Feature / Issue | Status | Technical Reality & Honest Impact |
|-----------------|--------|-----------------------------------|
| **Module 3 Relationships** | **Vector Similarity** | Implemented as on-demand cosine vector search (`GET /api/search/similar/{entity_id}`) directly against ChromaDB rather than a standalone graph database. |
| **Windows Memory Pressure / OOM** | **Known Issue** | `sentence-transformers` weight loading can fail under Windows virtual memory pressure (`OSError: paging file too small`). Restarting `uvicorn` loads from local disk cache. |

## License

MIT
