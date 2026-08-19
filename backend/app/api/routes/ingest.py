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
from app.utils.helpers import detect_file_type, generate_job_id, url_to_filename
from app.utils.logger import logger
from app.utils.memory import trim_memory

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

        # A scanned-image PDF or a file we could not extract from yields little
        # or no text. Reject it clearly here — mirroring the link route — rather
        # than spending an LLM call on an empty string and returning nothing.
        if len(raw_doc.text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract enough text from this file — is it a scanned image or empty?",
            )

        # Step 2: LLM Extraction
        _jobs[job_id].progress = "Extracting entities via LLM…"
        extractor = get_extractor()
        extraction = await extractor.extract(raw_doc.text)

        # Step 3: Categorize
        _jobs[job_id].progress = "Categorizing entities…"
        categorizer = get_categorizer()
        entities = categorizer.categorise(extraction, user_id)
        for e in entities:
            e.file_id = file_id

        # Step 4: Embed & Store
        _jobs[job_id].progress = "Embedding and storing…"
        embedding_svc = get_embedding_service()
        await embedding_svc.store_raw_chunks(raw_doc, user_id, file_id=file_id)
        await embedding_svc.store_entities(entities, user_id, file_id=file_id)

        # Step 5: Build Relations — across this user's whole corpus. Scoping
        # this to the current upload's entities left every document as its own
        # disconnected island in the knowledge graph.
        _jobs[job_id].progress = "Building relations…"
        relation_engine = get_relation_engine()
        relation_engine.rebuild_user_graph(user_id)

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
    except ValueError as exc:
        # Unsupported extension (detect_file_type) or an unregistered parser
        # type (parse_file) is a client mistake, not a server fault — surface
        # it as a 400 instead of letting the broad handler below make it a 500.
        logger.warning(f"Rejected upload for job {job_id}: {exc}")
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.FAILED, progress=str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Ingestion failed for job {job_id}: {exc}", exc_info=True)
        _jobs[job_id] = IngestionStatusResponse(
            job_id=job_id, status=JobStatus.FAILED, progress=str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")
    finally:
        # Reclaim transient buffers (file bytes, embedding batches, graph
        # scratch) between uploads, AND hand glibc's freed heap back to the OS.
        # One worker serves many requests on the free tier; the probe showed a
        # plain gc.collect() left RSS ~65 MB above idle after an upload, so the
        # NEXT upload started near the 512 MB ceiling and OOM-killed. trim_memory
        # adds malloc_trim(0) so each upload starts from the same low baseline.
        trim_memory()


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

        # Persist the fetched page verbatim, exactly like an uploaded file, so
        # link-derived entities can be traced back through /api/files/{file_id}.
        # Without this every link ingest produced orphaned entities with no
        # retrievable original.
        file_id = generate_job_id()
        settings = get_settings()
        original_name = f"{url_to_filename(url)}.html"
        dest_path = settings.upload_path / f"{file_id}_{original_name}"
        dest_path.write_bytes(resp.content)
        logger.info(f"Saved original page to {dest_path}")

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
        entities = categorizer.categorise(extraction, user_id)
        for e in entities:
            e.file_id = file_id

        # Step 4: Embed & Store
        _jobs[job_id].progress = "Embedding and storing…"
        embedding_svc = get_embedding_service()

        # Wrap the scraped text in a RawDocument so it flows through the same
        # chunk/embed path as an uploaded file.
        from app.models.schemas import RawDocument, FileType
        raw_doc = RawDocument(
            text=text,
            filename=original_name,
            file_type=FileType.TXT,
            page_count=1,
            file_id=file_id,
        )
        await embedding_svc.store_raw_chunks(raw_doc, user_id, file_id=file_id)
        await embedding_svc.store_entities(entities, user_id, file_id=file_id)

        # Step 5: Build Relations — across this user's whole corpus, not just
        # the entities from this one page.
        _jobs[job_id].progress = "Building relations…"
        relation_engine = get_relation_engine()
        relation_engine.rebuild_user_graph(user_id)

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
    finally:
        trim_memory()


@router.get("/status/{job_id}", response_model=IngestionStatusResponse)
async def get_status(job_id: str):
    """Check the processing status of an ingestion job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]
