"""
Ingest API — file upload and processing pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup

from app.api.deps import (
    get_categorizer,
    get_embedding_service,
    get_extractor,
    get_relation_engine,
)
from app.config import get_settings
from app.core.ingestion.parser import parse_file
from app.models.schemas import IngestionResult, IngestionStatusResponse, JobStatus, LinkIngestionRequest
from app.utils.helpers import detect_file_type, generate_job_id
from app.utils.logger import logger

router = APIRouter(prefix="/api/ingest", tags=["Ingestion"])

# In-memory job tracker (swap for Redis/DB in production)
_jobs: dict[str, IngestionStatusResponse] = {}


@router.post("/upload", response_model=IngestionResult)
async def upload_file(file: UploadFile = File(...), user_id: str = "default"):
    """
    Upload a document file (PDF, DOCX, TXT) for extraction and ingestion.

    Pipeline:
    1. Parse file → RawDocument
    2. LLM extraction → ExtractionResult
    3. Categorize → CategorisedEntity[]
    4. Embed + store in ChromaDB
    5. Build relations
    """
    job_id = generate_job_id()
    _jobs[job_id] = IngestionStatusResponse(
        job_id=job_id, status=JobStatus.PROCESSING, progress="Starting…"
    )

    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        file_type = detect_file_type(file.filename)
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        # Save original file to UPLOAD_DIR
        file_id = generate_job_id()
        settings = get_settings()
        stored_filename = f"{file_id}_{file.filename}"
        dest_path = settings.upload_path / stored_filename
        with open(dest_path, "wb") as f:
            f.write(file_bytes)
        logger.info(f"Saved original file to {dest_path}")

        # Step 1: Parse
        _jobs[job_id].progress = "Parsing file…"
        raw_doc = parse_file(file_bytes, file.filename, file_type)
        raw_doc.file_id = file_id
        logger.info(f"Parsed {file.filename}: {len(raw_doc.text)} chars, {raw_doc.page_count} pages")

        # Step 2: LLM Extraction
        _jobs[job_id].progress = "Extracting entities via LLM…"
        extractor = get_extractor()
        extraction = await extractor.extract(raw_doc.text)

        # Step 3: Categorize
        _jobs[job_id].progress = "Categorizing entities…"
        categorizer = get_categorizer()
        entities = categorizer.categorise(extraction)
        for e in entities:
            e.file_id = file_id

        # Step 4: Embed & Store
        _jobs[job_id].progress = "Embedding and storing…"
        embedding_svc = get_embedding_service()
        await embedding_svc.store_raw_chunks(raw_doc, user_id, file_id=file_id)
        await embedding_svc.store_entities(entities, user_id, file_id=file_id)

        # Step 5: Build Relations
        _jobs[job_id].progress = "Building relations…"
        relation_engine = get_relation_engine()
        relations = relation_engine.build_relations(entities)
        relation_engine.store_relations(entities, relations)

        # Done
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.COMPLETED, progress="Done"
        )

        return IngestionResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            filename=file.filename,
            entities_extracted=len(entities),
            entities=entities,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ingestion failed for job {job_id}: {exc}", exc_info=True)
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.FAILED, progress=str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


@router.post("/link", response_model=IngestionResult)
async def ingest_link(request: LinkIngestionRequest, user_id: str = "default"):
    """
    Ingest a portfolio or GitHub link.
    """
    job_id = generate_job_id()
    _jobs[job_id] = IngestionStatusResponse(
        job_id=job_id, status=JobStatus.PROCESSING, progress="Starting…"
    )
    
    url = request.url.strip()
    if not url.startswith("http"):
        url = "https://" + url
        
    try:
        _jobs[job_id].progress = "Fetching URL content…"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            
        _jobs[job_id].progress = "Extracting text from HTML…"
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Strip script and style elements
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=" ", strip=True)
        
        if not text or len(text) < 50:
            raise HTTPException(status_code=400, detail="Could not extract enough text from the provided link.")
            
        logger.info(f"Scraped {url}: {len(text)} chars extracted")

        # Step 2: LLM Extraction
        _jobs[job_id].progress = "Extracting entities via LLM…"
        extractor = get_extractor()
        extraction = await extractor.extract(text)

        # Step 3: Categorize
        _jobs[job_id].progress = "Categorizing entities…"
        categorizer = get_categorizer()
        entities = categorizer.categorise(extraction)

        # Step 4: Embed & Store
        _jobs[job_id].progress = "Embedding and storing…"
        embedding_svc = get_embedding_service()
        
        # Create a mock RawDocument for embedding storage compatibility
        from app.models.schemas import RawDocument, FileType
        raw_doc = RawDocument(
            text=text,
            filename=url,
            file_type=FileType.TXT,
            page_count=1
        )
        await embedding_svc.store_raw_chunks(raw_doc, user_id)
        await embedding_svc.store_entities(entities, user_id)

        # Step 5: Build Relations
        _jobs[job_id].progress = "Building relations…"
        relation_engine = get_relation_engine()
        relations = relation_engine.build_relations(entities)
        relation_engine.store_relations(entities, relations)

        # Done
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.COMPLETED, progress="Done"
        )

        return IngestionResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            filename=url,
            entities_extracted=len(entities),
            entities=entities,
        )

    except httpx.HTTPError as exc:
        logger.error(f"Failed to fetch URL {url}: {exc}")
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.FAILED, progress=f"Failed to fetch URL: {exc}"
        )
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Link ingestion failed for job {job_id}: {exc}", exc_info=True)
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.FAILED, progress=str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Link ingestion failed: {exc}")


@router.get("/status/{job_id}", response_model=IngestionStatusResponse)
async def get_status(job_id: str):
    """Check the processing status of an ingestion job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]
