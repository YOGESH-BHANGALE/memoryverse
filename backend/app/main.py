"""
MemoryVerse AI — FastAPI Application Entry Point
"""

import os

# Prevent OpenBLAS / PyTorch memory allocation errors on Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.routes import ingest, timeline, search, identity
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — startup and shutdown."""
    settings = get_settings()
    logger.info("MemoryVerse AI starting up...")
    logger.info(f"   ChromaDB path : {settings.chroma_path}")
    logger.info(f"   Upload dir    : {settings.upload_path}")
    logger.info(f"   LLM model     : {settings.groq_model}")
    logger.info(f"   Embedding     : {settings.hf_embedding_model}")
    
    # Pre-warm embedding service & ChromaDB client on startup
    from app.api.deps import get_embedding_service, get_chroma_client
    try:
        get_embedding_service()
        get_chroma_client()
        logger.info("Pre-warmed EmbeddingService & ChromaClient weights successfully.")
    except Exception as e:
        logger.warning(f"EmbeddingService pre-warm warning: {e}")
        
    yield
    logger.info("👋 MemoryVerse AI shutting down…")


app = FastAPI(
    title="MemoryVerse AI",
    description=(
        "Personal knowledge management API — upload documents, extract structured "
        "entities (skills, projects, certifications, internships, achievements), "
        "build a journey timeline, and search with RAG."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────────────
settings = get_settings()
origins = settings.cors_origin_list
if "*" not in origins:
    origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────
app.include_router(ingest.router)
app.include_router(timeline.router)
app.include_router(search.router)
app.include_router(identity.router)


# ── File Serving ────────────────────────────────────────────────────────
@app.get("/api/files/{file_id}", tags=["Files"])
async def get_file(file_id: str):
    """Serve original uploaded file by file_id."""
    settings = get_settings()
    upload_dir = settings.upload_path

    # Search for matching file starting with file_id
    matching_files = list(upload_dir.glob(f"{file_id}*"))
    if not matching_files:
        raise HTTPException(status_code=404, detail="File not found")

    target_file = matching_files[0]
    filename = (
        target_file.name.split("_", 1)[1]
        if "_" in target_file.name
        else target_file.name
    )

    return FileResponse(
        path=target_file,
        filename=filename,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Health Check ────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "MemoryVerse AI",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
