"""
Diagnostics — runtime facts about the container that is actually serving traffic.

Render's free tier gives no shell, no metrics and no retained logs, and ``/``
reports a hardcoded version, so from outside there is no way to tell *which*
image is live, how much memory it is using, or how close it is to the 512 MB
ceiling that OOM-kills the worker mid-upload. Debugging that blind costs a
~5 minute deploy per guess.

These endpoints turn that into direct observation:

* ``GET  /api/diag``       — which build is live, what is loaded, memory headroom.
* ``POST /api/diag/probe`` — run the ingest pipeline stage by stage, reporting
  resident memory and elapsed time after each, so the stage that overruns the
  ceiling is identified rather than inferred.

Read-only and side-effect-light by design. Never returns a secret *value* —
credentials are reported only as booleans.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import time

from fastapi import APIRouter, File, UploadFile

router = APIRouter(prefix="/api/diag", tags=["Diagnostics"])

# Bumped on every deploy. ``/`` returns a static "1.0.0", so this is the only
# way to confirm from outside that a push actually replaced the running image
# (a failed Render build silently keeps serving the previous one).
BUILD_MARKER = "onnx-no-torch-diag-1"

# Only the user_id the probe writes under, kept separate so diagnostic runs
# never pollute the demo identity's dashboard/graph.
PROBE_USER = "__diag_probe__"


def _rss_bytes() -> int | None:
    """Resident set size of this process, or None off Linux."""
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _read_int(path: str) -> int | None:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
        return None if raw == "max" else int(raw)
    except (OSError, ValueError):
        return None


def _cgroup_memory() -> dict[str, int | None]:
    """
    Container memory limit/usage as the kernel sees it.

    This is the number that matters: Render caps the *cgroup*, so the OOM killer
    fires on ``memory.current`` crossing ``memory.max`` — not on anything Python
    can see about its own heap. cgroup v2 paths first, then v1.
    """
    v2 = {
        "limit_bytes": _read_int("/sys/fs/cgroup/memory.max"),
        "current_bytes": _read_int("/sys/fs/cgroup/memory.current"),
        "peak_bytes": _read_int("/sys/fs/cgroup/memory.peak"),
    }
    if v2["limit_bytes"] is not None or v2["current_bytes"] is not None:
        v2["cgroup"] = 2  # type: ignore[assignment]
        return v2
    v1 = {
        "limit_bytes": _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
        "current_bytes": _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes"),
        "peak_bytes": _read_int("/sys/fs/cgroup/memory/memory.max_usage_in_bytes"),
    }
    # Only claim a cgroup version if something was actually readable. Off Linux
    # nothing is, and reporting "v1" there would be a fabricated number in the
    # one diagnostic we intend to trust about the OOM ceiling.
    if v1["limit_bytes"] is not None or v1["current_bytes"] is not None:
        v1["cgroup"] = 1  # type: ignore[assignment]
    else:
        v1["cgroup"] = None
    return v1


def _mb(value: int | None) -> float | None:
    return None if value is None else round(value / 1024 / 1024, 1)


def _version(module_name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(module_name)
    except Exception:
        return None


def _installed(module_name: str) -> bool | None:
    """
    Whether a module is importable, without importing it.

    ``find_spec`` can raise (a missing parent package, or any finder on
    ``sys.meta_path`` that objects), and a diagnostics endpoint that 500s is
    worse than useless — so failures report None rather than propagating.
    """
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return None


@router.get("")
async def diag() -> dict:
    """Runtime facts about the live container. No secret values, ever."""
    from app.api.deps import get_embedding_service
    from app.config import get_settings

    settings = get_settings()
    cg = _cgroup_memory()
    rss = _rss_bytes()

    # cache_info() reports whether the lru_cache singleton has been built
    # WITHOUT building it — constructing EmbeddingService here would load the
    # ONNX model and change the very memory number we are trying to measure.
    emb_built = get_embedding_service.cache_info().currsize > 0

    try:
        affinity = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        affinity = None

    return {
        "build_marker": BUILD_MARKER,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "versions": {
            "chromadb": _version("chromadb"),
            "onnxruntime": _version("onnxruntime"),
            "tokenizers": _version("tokenizers"),
            "numpy": _version("numpy"),
            "langchain": _version("langchain"),
        },
        # The whole point of the no-torch rebuild: torch must be neither loaded
        # nor installed. If either is true here, the heavy image is still live.
        "torch_loaded": "torch" in sys.modules,
        "torch_installed": _installed("torch"),
        "transformers_installed": _installed("transformers"),
        "sentence_transformers_installed": _installed("sentence_transformers"),
        "embedding_service_built": emb_built,
        "memory": {
            "rss_mb": _mb(rss),
            "cgroup_version": cg.get("cgroup"),
            "limit_mb": _mb(cg.get("limit_bytes")),
            "current_mb": _mb(cg.get("current_bytes")),
            "peak_mb": _mb(cg.get("peak_bytes")),
            "headroom_mb": (
                _mb((cg["limit_bytes"] or 0) - (cg["current_bytes"] or 0))
                if cg.get("limit_bytes") and cg.get("current_bytes")
                else None
            ),
        },
        "cpu": {
            "os_cpu_count": os.cpu_count(),
            "sched_affinity": affinity,
            "thread_env": {
                k: os.environ.get(k)
                for k in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "TOKENIZERS_PARALLELISM",
                )
            },
        },
        "config": {
            # Presence only — never the key itself.
            "groq_key_present": bool(settings.groq_api_key),
            "groq_model": settings.groq_model,
            "use_torch_embeddings": settings.use_torch_embeddings,
        },
        "loaded_module_count": len(sys.modules),
    }


@router.post("/probe")
async def probe(file: UploadFile = File(...)) -> dict:
    """
    Run the ingest pipeline one stage at a time, measuring memory after each.

    The production route either succeeds or dies as a unit, which says nothing
    about *where* the memory goes. This walks the identical stages and records
    resident/cgroup memory plus elapsed time after each, so a run that survives
    localises the cost and a run that dies identifies the last stage reached.

    Each stage is caught individually: a failure is reported and the walk stops,
    instead of collapsing into a bare 500.
    """
    from app.api.deps import (
        get_categorizer,
        get_embedding_service,
        get_extractor,
        get_relation_engine,
    )
    from app.core.ingestion.parser import parse_file
    from app.utils.helpers import detect_file_type

    stages: list[dict] = []
    started = time.monotonic()

    def mark(name: str, extra: dict | None = None) -> None:
        cg = _cgroup_memory()
        stages.append(
            {
                "stage": name,
                "elapsed_s": round(time.monotonic() - started, 2),
                "rss_mb": _mb(_rss_bytes()),
                "cgroup_current_mb": _mb(cg.get("current_bytes")),
                "cgroup_peak_mb": _mb(cg.get("peak_bytes")),
                **(extra or {}),
            }
        )

    mark("baseline")

    state: dict = {}
    failed: dict | None = None

    async def run(name: str, fn) -> bool:
        """Execute one stage, recording memory after it. False if it raised."""
        nonlocal failed
        try:
            result = fn()
            if hasattr(result, "__await__"):
                result = await result
            state[name] = result
            mark(name)
            return True
        except Exception as exc:  # noqa: BLE001 - diagnostics: report, don't raise
            failed = {"stage": name, "error": f"{type(exc).__name__}: {exc}"[:500]}
            mark(name, {"failed": True})
            return False

    filename = file.filename or "probe.txt"
    file_bytes = await file.read()
    mark("file_read", {"bytes": len(file_bytes)})

    # Constructing the embedding service loads the ONNX model — measured on its
    # own so the model's resident cost is separated from per-request buffers.
    if not await run("embedding_service_init", lambda: get_embedding_service()):
        return {"build_marker": BUILD_MARKER, "stages": stages, "failed": failed}
    embedding_svc = state["embedding_service_init"]

    if not await run(
        "parse",
        lambda: parse_file(file_bytes, filename, detect_file_type(filename)),
    ):
        return {"build_marker": BUILD_MARKER, "stages": stages, "failed": failed}
    raw_doc = state["parse"]
    raw_doc.file_id = "diag-probe"

    ok = await run("llm_extract", lambda: get_extractor().extract(raw_doc.text))
    extraction = state.get("llm_extract")

    entities = []
    if ok:
        if await run(
            "categorize",
            lambda: get_categorizer().categorise(extraction, PROBE_USER),
        ):
            entities = state["categorize"] or []

    if entities or ok:
        await run(
            "store_raw_chunks",
            lambda: embedding_svc.store_raw_chunks(
                raw_doc, PROBE_USER, file_id="diag-probe"
            ),
        )
        if entities:
            await run(
                "store_entities",
                lambda: embedding_svc.store_entities(
                    entities, PROBE_USER, file_id="diag-probe"
                ),
            )
        await run(
            "rebuild_graph",
            lambda: get_relation_engine().rebuild_user_graph(PROBE_USER),
        )

    import gc

    gc.collect()
    mark("after_gc")

    return {
        "build_marker": BUILD_MARKER,
        "filename": filename,
        "text_chars": len(getattr(raw_doc, "text", "") or ""),
        "entities_extracted": len(entities),
        "raw_chunks_stored": state.get("store_raw_chunks"),
        "failed": failed,
        "memory_limit_mb": _mb(_cgroup_memory().get("limit_bytes")),
        "stages": stages,
    }
