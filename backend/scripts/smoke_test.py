"""
Live smoke test — verifies the fixes from the 2026-08-16 debug pass against a
running backend, using the real ChromaDB as the source of truth for what the
API *should* return.

What it checks
--------------
  A. Collection naming invariant — every EntityCategory maps to a name that the
     read paths actually scan (offline; catches a future category being added to
     the enum but not to COLLECTIONS).
  B. Academics visibility — the 16 stranded degree records must be reachable
     through /api/timeline (filtered and unfiltered), /api/identity and
     /api/search/filter. Expected counts are read straight out of the SQLite
     store, so this is a real comparison and not a self-fulfilling one.
  C. SSE framing — a multi-line payload must survive the server encoder and the
     client parser. The offline half is deterministic (no LLM, no network); the
     live half asserts the wire format of a real streamed answer.
  D. Source links — file_ids attached to entities must resolve through
     /api/files/{file_id}, which is what the fixed source links point at.

Nothing is written: this is read-only against both the API and the database.

Usage
-----
    # from the backend/ directory, with the project venv active and
    # `uvicorn app.main:app` already running in another terminal
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://localhost:8000
    python scripts/smoke_test.py --user-id a7b3e329-1832-45a7-9f3f-428468acddff
    python scripts/smoke_test.py --skip-llm      # skip the two checks that call Groq

Exit code is 0 when there are no failures, 1 otherwise — so it can gate a
deploy. WARN and SKIP do not fail the run.
"""

from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

PASS, FAIL, WARN, SKIP, INFO = "PASS", "FAIL", "WARN", "SKIP", "INFO"

# Read paths only ever scan these; kept as a fallback for when the app package
# cannot be imported (no venv). The real list is imported when possible.
FALLBACK_COLLECTIONS = [
    "skills", "projects", "certifications", "internships",
    "achievements", "academics", "raw_chunks",
]

_results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    _results.append((status, name, detail))
    print(f"  [{status}] {name}")
    if detail:
        for line in str(detail).rstrip().split("\n"):
            print(f"         {line}")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


# ── HTTP helpers (stdlib only, so this runs even without httpx/requests) ──

def _request(req: urllib.request.Request, timeout: float) -> tuple[int, str]:
    """
    Perform a request, turning every failure into a status/body pair.

    A dropped connection or unhandled server exception must be reported as a
    failed check, not raised — one bad endpoint should not abort the whole run.
    """
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, f"<transport error> {type(exc).__name__}: {exc}"


def http_get(base: str, path: str, timeout: float = 60.0) -> tuple[int, str]:
    return _request(
        urllib.request.Request(base + path, headers={"Accept": "application/json"}),
        timeout,
    )


def http_post(base: str, path: str, payload: dict, timeout: float = 120.0) -> tuple[int, str]:
    return _request(
        urllib.request.Request(
            base + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        ),
        timeout,
    )


def http_post_stream(base: str, path: str, payload: dict,
                     timeout: float = 180.0) -> tuple[int, str, str]:
    """POST and drain the whole response body, returning it verbatim."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + path, data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    chunks: list[bytes] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        reader = getattr(resp, "read1", resp.read)
        while True:
            piece = reader(4096)
            if not piece:
                break
            chunks.append(piece)
        return resp.status, ctype, b"".join(chunks).decode("utf-8", "replace")


# ── SSE parsing: a faithful mirror of frontend/src/lib/api.ts ─────────────

_ALLOWED_PREFIXES = ("event:", "data:", "id:", "retry:", ":")


def _parse_block(block: str) -> tuple[str, str]:
    """One event block -> (event name, payload with newlines restored)."""
    name = ""
    data_lines: list[str] = []
    for raw_line in block.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if line.startswith(":"):
            continue  # comment / keep-alive
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            value = line[5:]
            data_lines.append(value[1:] if value.startswith(" ") else value)
    return name, "\n".join(data_lines)


class SSEReader:
    """Incremental reader — only dispatches blocks terminated by a blank line."""

    def __init__(self) -> None:
        self.buffer = ""
        self.events: list[tuple[str, str]] = []

    def feed(self, text: str) -> None:
        self.buffer += text
        while True:
            sep = self.buffer.find("\n\n")
            if sep == -1:
                break
            block = self.buffer[:sep]
            self.buffer = self.buffer[sep + 2:]
            if block.strip():
                self.events.append(_parse_block(block))

    def close(self) -> list[tuple[str, str]]:
        if self.buffer.strip():
            self.events.append(_parse_block(self.buffer))
        self.buffer = ""
        return self.events


def parse_sse(raw: str) -> list[tuple[str, str]]:
    reader = SSEReader()
    reader.feed(raw)
    return reader.close()


def wire_violations(raw: str) -> list[str]:
    """
    Lines that are not legal SSE fields.

    This is the fingerprint of the old bug: a raw multi-line payload emitted as
    a single "data:" field leaves continuation lines with no field prefix, and
    an embedded blank line terminates the event early.
    """
    bad: list[str] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        for raw_line in block.split("\n"):
            line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
            if line and not line.startswith(_ALLOWED_PREFIXES):
                bad.append(line)
    return bad


def load_sse_encoder():
    """RAGChain._sse_event, imported if deps allow, else lifted from source."""
    try:
        from app.core.rag.chain import RAGChain  # noqa: WPS433
        return RAGChain._sse_event, "imported from app.core.rag.chain"
    except Exception:
        source = (BACKEND_DIR / "app" / "core" / "rag" / "chain.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "_sse_event":
                node.decorator_list = []
                module = ast.Module(body=[node], type_ignores=[])
                namespace: dict[str, Any] = {}
                exec(compile(ast.fix_missing_locations(module), "<chain>", "exec"), namespace)
                return namespace["_sse_event"], "lifted from source via ast (deps unavailable)"
        raise RuntimeError("_sse_event not found in app/core/rag/chain.py")


# ── ChromaDB inspection (read-only SQLite; no chromadb import needed) ─────

_META_KEYS = ("user_id", "category", "file_id", "title", "date")


def open_db(chroma_path: Path) -> Optional[sqlite3.Connection]:
    db_file = chroma_path / "chroma.sqlite3"
    if not db_file.exists():
        return None
    return sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)


def collection_records(con: sqlite3.Connection, name: str) -> Optional[list[dict]]:
    """Metadata for every record in a collection, or None if it does not exist."""
    cur = con.cursor()
    cur.execute("SELECT id FROM collections WHERE name = ?", (name,))
    row = cur.fetchone()
    if row is None:
        return None

    cur.execute("SELECT id FROM segments WHERE collection = ?", (row[0],))
    segments = [r[0] for r in cur.fetchall()]

    rowids: dict[int, str] = {}
    for segment in segments:
        cur.execute("SELECT id, embedding_id FROM embeddings WHERE segment_id = ?", (segment,))
        for rowid, embedding_id in cur.fetchall():
            rowids[rowid] = embedding_id

    records: dict[int, dict] = {rid: {"_id": eid} for rid, eid in rowids.items()}
    ids = list(rowids)
    for start in range(0, len(ids), 400):
        batch = ids[start:start + 400]
        placeholders = ",".join("?" * len(batch))
        cur.execute(
            f"SELECT id, key, string_value FROM embedding_metadata WHERE id IN ({placeholders})",
            tuple(batch),
        )
        for rowid, key, value in cur.fetchall():
            if key in _META_KEYS:
                records[rowid][key] = value

    # De-duplicate in case a record appears in more than one segment.
    unique: dict[str, dict] = {}
    for rec in records.values():
        unique[rec["_id"]] = rec
    return list(unique.values())


def resolve_settings(explicit_path: Optional[str]) -> tuple[Path, str, str]:
    """(chroma_path, collection_prefix, how it was resolved)."""
    if explicit_path:
        return Path(explicit_path), "memoryverse", "--chroma-path"
    try:
        from app.config import get_settings  # noqa: WPS433
        settings = get_settings()
        return Path(settings.chroma_path), settings.chroma_collection_prefix, "app.config"
    except Exception as exc:
        return Path("chroma_db"), "memoryverse", f"defaults ({type(exc).__name__} importing app.config)"


# ── Checks ────────────────────────────────────────────────────────────────

def check_preflight(base: str) -> bool:
    section("Preflight")
    try:
        status, body = http_get(base, "/health", timeout=10)
    except Exception as exc:
        record(FAIL, f"backend reachable at {base}",
               f"{type(exc).__name__}: {exc}\n"
               f"Start it first:  cd backend && uvicorn app.main:app --reload")
        return False

    if status == 200 and json.loads(body).get("status") == "healthy":
        record(PASS, f"GET /health -> 200 healthy  ({base})")
        return True
    record(FAIL, "GET /health", f"status={status} body={body[:200]}")
    return False


def check_naming_invariant(collections: list[str]) -> None:
    section("A. Collection naming invariant (offline)")
    try:
        from app.core.vectordb.client import collection_for_category  # noqa: WPS433
        from app.models.schemas import EntityCategory  # noqa: WPS433
    except Exception as exc:
        record(SKIP, "every EntityCategory maps into COLLECTIONS",
               f"cannot import the app package ({type(exc).__name__}: {exc}); "
               f"activate the venv to run this check")
        return

    mapped = {cat.value: collection_for_category(cat) for cat in EntityCategory}
    unmapped = {v: c for v, c in mapped.items() if c not in collections}
    detail = "\n".join(f"{v:14s} -> {c}" for v, c in mapped.items())
    if unmapped:
        record(FAIL, "every EntityCategory maps into COLLECTIONS",
               detail + "\nnot present in COLLECTIONS: " + ", ".join(sorted(unmapped.values()))
               + "\nRead paths iterate COLLECTIONS, so these categories are invisible.")
    else:
        record(PASS, f"all {len(mapped)} EntityCategory values map into COLLECTIONS", detail)

    if collection_for_category("academics") != "academics":
        record(FAIL, "academics is not naively pluralised",
               f'collection_for_category("academics") returned '
               f'"{collection_for_category("academics")}"')
    else:
        record(PASS, 'collection_for_category("academics") == "academics"')


def check_academics(base: str, user_id: str, target_recs: list[dict],
                    legacy_recs: list[dict], collections: list[str],
                    con: sqlite3.Connection, prefix: str) -> None:
    section(f"B. Academics visible through the live API (user {user_id})")

    target_for_user = [r for r in target_recs if r.get("user_id") == user_id]
    legacy_for_user = [r for r in legacy_recs if r.get("user_id") == user_id]

    # Records in the legacy collection *ought* to be visible, so they count
    # towards the expectation. That way a pending migration fails the run
    # instead of quietly skipping it.
    expected = target_for_user + legacy_for_user
    expected_count = len(expected)
    titles = sorted({(r.get("title") or "(untitled)") for r in expected})
    remedy = ("\n-> " + str(len(legacy_for_user)) + " of these are still in the legacy "
              "collection; run:\n   python scripts/migrate_academics_collection.py --apply"
              ) if legacy_for_user else ""

    if expected_count == 0:
        record(SKIP, "academics reachable via API",
               "this user has no academics records in either collection")
        return

    # B1 — unfiltered timeline
    status, body = http_get(base, f"/api/timeline/{user_id}")
    if status != 200:
        record(FAIL, "GET /api/timeline/{user} -> 200", f"status={status} body={body[:300]}")
    else:
        milestones = json.loads(body).get("milestones", [])
        found = [m for m in milestones if m.get("category") == "academics"]
        if len(found) == expected_count:
            record(PASS, f"unfiltered timeline contains all {expected_count} academics milestone(s)",
                   f"{len(milestones)} milestone(s) total\n"
                   + "\n".join(f"- {m.get('date') or 'undated':8s} {m.get('title')}" for m in found))
        else:
            record(FAIL, "unfiltered timeline contains every academics milestone",
                   f"expected {expected_count} from the database, API returned {len(found)}\n"
                   f"{len(milestones)} milestone(s) total; expected titles: {titles}" + remedy)

    # B2 — category-filtered timeline
    status, body = http_get(base, f"/api/timeline/{user_id}?category=academics")
    if status != 200:
        record(FAIL, "GET /api/timeline/{user}?category=academics -> 200",
               f"status={status} body={body[:300]}")
    else:
        milestones = json.loads(body).get("milestones", [])
        wrong = [m.get("category") for m in milestones if m.get("category") != "academics"]
        if len(milestones) == expected_count and not wrong:
            record(PASS, f"?category=academics returns exactly the {expected_count} academics milestone(s)")
        else:
            record(FAIL, "?category=academics returns exactly the academics milestones",
                   f"expected {expected_count}, got {len(milestones)}"
                   + (f"; non-academics categories leaked in: {Counter(wrong)}" if wrong else "")
                   + remedy)

    # B3 — identity totals
    per_collection: dict[str, int] = {}
    for name in collections:
        if name == "raw_chunks":
            continue
        recs = collection_records(con, f"{prefix}_{name}") or []
        # The route reads with limit=500 per collection, so cap the expectation.
        per_collection[name] = min(sum(1 for r in recs if r.get("user_id") == user_id), 500)
    expected_total = sum(per_collection.values()) + len(legacy_for_user)

    status, body = http_get(base, f"/api/identity/{user_id}")
    if status != 200:
        record(FAIL, "GET /api/identity/{user} -> 200", f"status={status} body={body[:300]}")
    else:
        total = json.loads(body).get("total_entities", 0)
        breakdown = ", ".join(f"{k}={v}" for k, v in per_collection.items() if v)
        if legacy_for_user:
            breakdown += f", academics(legacy)={len(legacy_for_user)}"
        if total == expected_total:
            record(PASS, f"identity total_entities == {expected_total} (academics included)",
                   breakdown)
        else:
            record(FAIL, "identity total_entities counts academics",
                   f"expected {expected_total} from the database, API returned {total}\n"
                   f"database breakdown: {breakdown}\n"
                   f"the shortfall of {expected_total - total} matches the academics count "
                   f"({expected_count}), so academics are still unreachable" + remedy)

    # B4 — faceted search, pure metadata path (no LLM involved)
    status, body = http_post(base, "/api/search/filter", {
        "user_id": user_id, "categories": ["academics"], "top_k": 100,
    })
    if status != 200:
        record(FAIL, "POST /api/search/filter categories=[academics] -> 200",
               f"status={status} body={body[:300]}")
    else:
        payload = json.loads(body)
        results = payload.get("results", [])
        buckets = Counter(r.get("metadata", {}).get("collection") for r in results)
        if not results:
            record(FAIL, "faceted search returns academics",
                   f"total_results=0, filters_applied={payload.get('filters_applied')}" + remedy)
        elif set(buckets) == {"academics"} and len(results) == expected_count:
            record(PASS, f"faceted search returns {len(results)} academics record(s) "
                         f'from collection "academics"')
        else:
            record(FAIL, 'faceted search reads the whole "academics" collection',
                   f"expected {expected_count} record(s), got {len(results)}; "
                   f"collections seen: {dict(buckets)} "
                   f'(anything named "academicss" means a read path is still mis-naming)'
                   + remedy)


def check_sse_offline() -> None:
    section("C. SSE framing")
    try:
        encode, provenance = load_sse_encoder()
    except Exception as exc:
        record(FAIL, "load RAGChain._sse_event", f"{type(exc).__name__}: {exc}")
        return

    payload = (
        "Here are your degrees:\n"
        "- B.E. Computer Engineering, Dr. D. Y. Patil\n"
        "- B.S. Computer Science, Stanford\n"
        "\n"
        "Both appear in your timeline."
    )
    wire = encode("chunk", payload)

    violations = wire_violations(wire)
    if violations:
        record(FAIL, "encoder emits only legal SSE field lines",
               f"{len(violations)} unprefixed line(s), e.g. {violations[:3]!r}\n"
               f"({provenance})")
    else:
        record(PASS, f"encoder emits one data: field per payload line ({provenance})")

    events = parse_sse(wire)
    if len(events) == 1 and events[0] == ("chunk", payload):
        record(PASS, "multi-line payload survives the round trip intact",
               f"{len(payload)} chars, {payload.count(chr(10))} newlines, "
               f"including an embedded blank line")
    else:
        got = events[0][1] if events else ""
        record(FAIL, "multi-line payload survives the round trip",
               f"{len(events)} event(s) parsed; {len(got)}/{len(payload)} chars and "
               f"{got.count(chr(10))}/{payload.count(chr(10))} newlines preserved\n"
               f"got: {got!r}")

    # Network reads split wherever they like — the parser must not care.
    stream = "".join(encode(name, data) for name, data in
                     [("chunk", "Line one\nLine two"), ("chunk", "- bullet\n- bullet two"),
                      ("sources", json.dumps([{"chunk_id": "x", "source_file": "f",
                                               "collection": "academics", "score": 1.0}])),
                      ("done", "")])
    reference = parse_sse(stream)
    failures = []
    for size in (1, 2, 3, 7, 13, 512):
        reader = SSEReader()
        for start in range(0, len(stream), size):
            reader.feed(stream[start:start + size])
        if reader.close() != reference:
            failures.append(size)
    if failures:
        record(FAIL, "parser is agnostic to network read boundaries",
               f"mismatch at chunk size(s): {failures}")
    else:
        record(PASS, "parser survives every read boundary (1, 2, 3, 7, 13, 512 bytes)",
               f"{len(reference)} events recovered identically each time")


def check_sse_live(base: str, user_id: str, timeout: float) -> str:
    """Returns the assembled answer so the non-streamed check can compare sizes."""
    section("C. SSE framing — live stream")
    question = "List my academic qualifications and degrees as bullet points."
    try:
        status, ctype, raw = http_post_stream(base, "/api/search/query", {
            "query": question, "user_id": user_id, "top_k": 10, "stream": True,
        }, timeout=timeout)
    except Exception as exc:
        record(FAIL, "POST /api/search/query stream=true",
               f"{type(exc).__name__}: {exc}")
        return ""

    if status != 200:
        record(FAIL, "streamed query -> 200", f"status={status}")
        return ""
    if "text/event-stream" not in ctype:
        record(FAIL, "streamed response is text/event-stream", f"Content-Type: {ctype}")
    else:
        record(PASS, f"streamed response is text/event-stream ({len(raw)} bytes on the wire)")

    violations = wire_violations(raw)
    if violations:
        record(FAIL, "live stream contains only legal SSE field lines",
               f"{len(violations)} unprefixed line(s) — payload newlines are being "
               f"emitted raw, which truncates events. e.g. {violations[:3]!r}")
    else:
        record(PASS, "every line of the live stream is a legal SSE field")

    events = parse_sse(raw)
    names = Counter(name for name, _ in events)
    answer = "".join(data for name, data in events if name == "chunk")

    if names.get(""):
        record(FAIL, "every event on the wire is named",
               f"{names['']} block(s) arrived with no event: field — a payload was "
               f"split across event boundaries, so part of the answer is unroutable")
    elif names.get("chunk", 0) and names.get("done", 0):
        record(PASS, f"event sequence complete: {dict(names)}")
    else:
        record(FAIL, "stream emits chunk and done events", f"saw {dict(names)}")

    sources_payloads = [d for n, d in events if n == "sources"]
    if not sources_payloads:
        record(WARN, "stream emits a sources event", "no sources event was received")
    else:
        try:
            sources = json.loads(sources_payloads[-1])
            collections_cited = Counter(s.get("collection") for s in sources)
            with_file = sum(1 for s in sources if s.get("file_id"))
            record(PASS, f"sources event parses as JSON ({len(sources)} source(s))",
                   f"collections cited: {dict(collections_cited)}\n"
                   f"{with_file}/{len(sources)} carry a file_id (these become clickable links)")
        except json.JSONDecodeError as exc:
            record(FAIL, "sources event parses as JSON", f"{exc}: {sources_payloads[-1][:200]}")

    if "I couldn't generate an answer at this time." in answer:
        record(WARN, "streamed answer has real content",
               "the backend returned its no-LLM fallback, which means GROQ_API_KEY is "
               "missing, empty or rejected. Set a valid key in backend/.env and check the "
               "backend log for the 401. Framing checks above still hold; the newline "
               "check below is inconclusive without real content.")
        return answer

    newlines = answer.count("\n")
    if newlines:
        record(PASS, f"streamed answer preserves {newlines} newline(s) across "
                     f"{len(answer)} chars",
               "first 3 lines:\n" + "\n".join(answer.split("\n")[:3]))
    elif violations:
        # Not "the model wrote one long line" — the newlines were eaten in transit,
        # which is exactly what the unprefixed lines above are evidence of.
        record(FAIL, "streamed answer preserves newlines",
               f"0 newlines in {len(answer)} delivered chars, and the wire carried "
               f"{len(violations)} unprefixed line(s). The payload newlines are being "
               f"dropped in framing, not absent from the model output.")
    else:
        record(WARN, "streamed answer preserves newlines",
               f"the model answered in {len(answer)} chars with no line breaks, so this "
               f"run could not exercise multi-line framing. The offline round trip above "
               f"covers it deterministically.")
    return answer


def check_nonstream(base: str, user_id: str, timeout: float,
                    streamed: Optional[str] = None) -> None:
    question = "List my academic qualifications and degrees as bullet points."
    status, body = http_post(base, "/api/search/query", {
        "query": question, "user_id": user_id, "top_k": 10, "stream": False,
    }, timeout=timeout)
    if status != 200:
        record(FAIL, "POST /api/search/query stream=false -> 200",
               f"status={status} body={body[:300]}")
        return
    payload = json.loads(body)
    answer = payload.get("answer", "")
    if "I couldn't generate an answer at this time." in answer:
        record(WARN, "non-streamed answer has real content",
               "no-LLM fallback returned — see the GROQ_API_KEY note above")
        return
    cited = Counter(s.get("collection") for s in payload.get("sources", []))
    record(PASS, f"non-streamed answer returned {len(answer)} chars, "
                 f"{len(payload.get('sources', []))} source(s)",
           f"collections cited: {dict(cited)}\n"
           f"retrieval_method={payload.get('retrieval_method')}")

    # Heuristic: the two calls are separate generations so lengths will never
    # match exactly, but the framing bug cost ~54% of every answer, which is far
    # outside normal variation between two responses to the same question.
    if streamed and answer:
        ratio = len(streamed) / len(answer)
        if ratio < 0.70:
            record(WARN, "streamed and non-streamed answers are comparable in size",
                   f"streamed delivered {len(streamed)} chars vs {len(answer)} "
                   f"non-streamed ({ratio:.0%}). Two generations do differ, but a gap "
                   f"this large is the signature of content being lost in the stream.")
        else:
            record(PASS, f"streamed and non-streamed answers are comparable "
                         f"({len(streamed)} vs {len(answer)} chars, {ratio:.0%})")


def check_file_links(base: str, records: list[dict]) -> None:
    section("D. Source links resolve")
    file_ids = [r["file_id"] for r in records if r.get("file_id")][:3]
    if not file_ids:
        record(SKIP, "GET /api/files/{file_id}", "no file_id on any academics record")
        return
    ok, missing = 0, []
    for file_id in file_ids:
        status, _ = http_get(base, f"/api/files/{file_id}", timeout=30)
        if status == 200:
            ok += 1
        else:
            missing.append(f"{file_id} -> {status}")
    if ok == len(file_ids):
        record(PASS, f"all {ok} sampled file_id(s) resolve through /api/files/")
    elif ok:
        record(WARN, "sampled file_ids resolve through /api/files/",
               f"{ok}/{len(file_ids)} resolved; unresolved: {missing}\n"
               f"the originals were probably cleared out of backend/uploads/ — "
               f"source links for those entities will 404")
    else:
        record(WARN, "sampled file_ids resolve through /api/files/",
               f"none of {len(file_ids)} resolved: {missing}\n"
               f"check that the backend was started from backend/ so upload_dir "
               f"points at backend/uploads/")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Live smoke test for MemoryVerse AI.")
    ap.add_argument("--base-url", default="http://localhost:8000",
                    help="backend base URL (default: http://localhost:8000)")
    ap.add_argument("--user-id", default=None,
                    help="user to test with (default: the user with the most academics records)")
    ap.add_argument("--chroma-path", default=None,
                    help="override the ChromaDB directory")
    ap.add_argument("--skip-llm", action="store_true",
                    help="skip the two checks that call Groq")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="seconds to allow for LLM-backed requests (default: 180)")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")

    print("MemoryVerse AI — live smoke test")
    print("=" * 64)

    chroma_path, prefix, how = resolve_settings(args.chroma_path)
    print(f"backend      : {base}")
    print(f"ChromaDB     : {chroma_path}  (via {how})")
    print(f"prefix       : {prefix}")

    try:
        from app.core.vectordb.client import COLLECTIONS  # noqa: WPS433
        collections = list(COLLECTIONS)
    except Exception:
        collections = list(FALLBACK_COLLECTIONS)
        print("COLLECTIONS  : using built-in fallback (app package not importable)")

    if not check_preflight(base):
        print("\nAborting: nothing else can be checked without a running backend.")
        return 1

    con = open_db(chroma_path)
    if con is None:
        record(FAIL, "ChromaDB readable",
               f"no chroma.sqlite3 under {chroma_path}. Run this from the backend/ "
               f"directory, or pass --chroma-path.")
        print_summary()
        return 1

    target = collection_records(con, f"{prefix}_{TARGET}")
    legacy = collection_records(con, f"{prefix}_{LEGACY}")
    print(f"\n{prefix}_{TARGET:<12} : "
          f"{'absent' if target is None else str(len(target)) + ' record(s)'}")
    print(f"{prefix}_{LEGACY:<12} : "
          f"{'absent' if legacy is None else str(len(legacy)) + ' record(s)'}")

    if legacy:
        print(f"\n  NOTE: {len(legacy)} record(s) are still in the legacy collection. "
              f"Until you run\n"
              f"        python scripts/migrate_academics_collection.py --apply\n"
              f"        the academics checks in section B are expected to fail.")

    pool = target or legacy or []
    if args.user_id:
        user_id = args.user_id
    elif pool:
        user_id = Counter(r.get("user_id") for r in pool).most_common(1)[0][0]
    else:
        user_id = "default"
    if pool:
        spread = Counter(r.get("user_id") for r in pool)
        print(f"\nacademics by user: {dict(spread)}")
    print(f"testing as user  : {user_id}")

    check_naming_invariant(collections)
    check_academics(base, user_id, target or [], legacy or [], collections, con, prefix)
    check_sse_offline()
    if args.skip_llm:
        section("C. SSE framing — live stream")
        record(SKIP, "live streamed query", "--skip-llm was passed")
    else:
        streamed = check_sse_live(base, user_id, args.timeout)
        check_nonstream(base, user_id, args.timeout, streamed)
    check_file_links(base, target or legacy or [])

    con.close()
    return print_summary()


def print_summary() -> int:
    counts = Counter(status for status, _, _ in _results)
    print("\n" + "=" * 64)
    print("Summary: " + "  ".join(
        f"{status}={counts.get(status, 0)}" for status in (PASS, FAIL, WARN, SKIP)))
    failures = [name for status, name, _ in _results if status == FAIL]
    if failures:
        print("\nFailed checks:")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("\nAll checks passed.")
    return 0


LEGACY = "academicss"
TARGET = "academics"

if __name__ == "__main__":
    raise SystemExit(main())
