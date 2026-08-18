/**
 * MemoryVerse AI — Chrome DevTools smoke test
 * ===========================================
 *
 * Tests the 2026-08-16 fixes from inside the browser. This covers three things
 * the Python smoke test structurally cannot:
 *
 *   1. CORS — every request here originates from the real page origin
 *      (http://localhost:3000), so a broken CORS config fails loudly. A Python
 *      script bypasses CORS entirely because it isn't a browser.
 *   2. The browser's own streaming stack — ReadableStream + TextDecoder split
 *      the SSE bytes at arbitrary boundaries. That is precisely where the
 *      dropped-newline bug bit, and it cannot be reproduced outside a browser.
 *   3. The rendered DOM — whether academics entities actually reach the screen.
 *
 * HOW TO RUN
 * ----------
 *   1. Start the backend:   cd backend && uvicorn app.main:app --reload
 *   2. Start the frontend:  cd frontend && npm run dev
 *   3. Open http://localhost:3000/timeline in Chrome
 *   4. F12 -> Console. If Chrome blocks the paste, type   allow pasting
 *      and press Enter first.
 *   5. Paste this whole file and press Enter.
 *
 * TO TEST THE DEPLOYED STACK instead, open the Vercel URL and run these two
 * lines in the console before pasting the script:
 *
 *   window.__MV_API__  = "https://memoryverse-backend-bju3.onrender.com";
 *   window.__MV_USER__ = "<a user_id that exists in the deployed store>";
 *
 * Expect a slow first request — Render's free tier spins down after ~15 min and
 * a cold start can exceed 50s, which reads as a hang rather than a failure.
 *
 * Nothing is written or mutated — every request is a GET or a read-only POST.
 */

(async () => {
  const API = window.__MV_API__ || "http://localhost:8000";

  const results = [];
  const log = (status, name, detail) => {
    results.push({ status, check: name, detail: detail || "" });
    const colour = { PASS: "#0a7", FAIL: "#d33", WARN: "#c80", SKIP: "#888", INFO: "#369" }[status];
    console.log(`%c[${status}]%c ${name}`, `color:${colour};font-weight:bold`, "color:inherit");
    if (detail) console.log(`         ${String(detail).replace(/\n/g, "\n         ")}`);
  };
  const group = (t) => console.log(`%c\n${t}\n${"-".repeat(t.length)}`, "color:#666");

  // Every exit path goes through here, so an early abort still publishes its
  // verdict. Otherwise a dead backend prints FAIL but returns "no results",
  // which reads as success to anything inspecting the return value.
  const finish = () => {
    const tally = results.reduce((a, r) => ((a[r.status] = (a[r.status] || 0) + 1), a), {});
    console.log("%c\n" + "=".repeat(56), "color:#666");
    console.log(
      `%cSummary: ${Object.entries(tally).map(([k, v]) => `${k}=${v}`).join("  ")}`,
      "font-weight:bold"
    );
    const failed = results.filter((r) => r.status === "FAIL");
    if (failed.length) {
      console.log("%cFailed checks:", "color:#d33;font-weight:bold");
      failed.forEach((f) => console.log(`  - ${f.check}`));
    } else {
      console.log("%cAll checks passed.", "color:#0a7;font-weight:bold");
    }
    console.table(results);
    window.__MV_RESULTS__ = results;
    return `${tally.PASS || 0} passed, ${tally.FAIL || 0} failed`;
  };

  const getJSON = async (path) => {
    const res = await fetch(API + path, { mode: "cors" });
    const text = await res.text();
    let body = null;
    try { body = JSON.parse(text); } catch { /* leave null */ }
    return { status: res.status, body, text };
  };
  const postJSON = async (path, payload) => {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      mode: "cors",
    });
    const text = await res.text();
    let body = null;
    try { body = JSON.parse(text); } catch { /* leave null */ }
    return { status: res.status, body, text };
  };

  // ── The SSE parser from frontend/src/lib/api.ts, mirrored ───────────────
  const ALLOWED = ["event:", "data:", "id:", "retry:", ":"];
  const parseBlock = (block) => {
    let name = "";
    const dataLines = [];
    for (const rawLine of block.split("\n")) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) {
        const v = line.slice(5);
        dataLines.push(v.startsWith(" ") ? v.slice(1) : v);
      }
    }
    return { name, data: dataLines.join("\n") };
  };
  const wireViolations = (raw) => {
    const bad = [];
    for (const block of raw.split("\n\n")) {
      if (!block.trim()) continue;
      for (const rawLine of block.split("\n")) {
        const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
        if (line && !ALLOWED.some((p) => line.startsWith(p))) bad.push(line);
      }
    }
    return bad;
  };

  console.log("%cMemoryVerse AI — Chrome smoke test", "font-size:15px;font-weight:bold");
  console.log(`page origin : ${window.location.origin}`);
  console.log(`API base    : ${API}`);

  // ── Preflight + CORS ───────────────────────────────────────────────────
  group("0. Reachability and CORS");
  if (window.location.origin === "null" || window.location.protocol === "file:") {
    log("WARN", "running from the app origin",
      "you are not on http://localhost:3000 — CORS results below will not reflect real usage");
  }
  let health;
  try {
    health = await getJSON("/health");
  } catch (err) {
    log("FAIL", "backend reachable from the page",
      `${err.name}: ${err.message}\nA TypeError here almost always means CORS was refused or ` +
      `the backend is not running. Check the Network tab for a failed preflight.`);
    return finish();
  }
  if (health.status === 200 && health.body?.status === "healthy") {
    log("PASS", "GET /health from the page origin (CORS allows it)");
  } else {
    log("FAIL", "GET /health", `status=${health.status} body=${health.text.slice(0, 200)}`);
    return finish();
  }

  // ── Resolve the user the app is actually using ─────────────────────────
  group("1. Identify the active user");
  let userId =
    window.__MV_USER__ ||
    localStorage.getItem("memoryverse_user_id") ||   // the key lib/user.ts actually writes
    localStorage.getItem("user_id") ||
    localStorage.getItem("userId") ||
    (document.cookie.match(/(?:^|;\s*)(?:memoryverse_)?user_id=([^;]+)/) || [])[1] ||
    null;

  if (userId) {
    log("PASS", `active user_id = ${userId}`,
      "read from localStorage/cookie — the same id the UI uses");
  } else {
    userId = "default";
    log("WARN", "could not find a user_id in localStorage or cookies",
      `falling back to "default". Set one explicitly and re-run:\n` +
      `window.__MV_USER__ = "a7b3e329-1832-45a7-9f3f-428468acddff"`);
  }

  // ── Academics reachability ─────────────────────────────────────────────
  group("2. Academics reachable through the API (the defect-1 fix)");
  const timeline = await getJSON(`/api/timeline/${userId}`);
  let academics = [];
  if (timeline.status !== 200) {
    log("FAIL", "GET /api/timeline/{user}", `status=${timeline.status}`);
  } else {
    const ms = timeline.body?.milestones || [];
    academics = ms.filter((m) => m.category === "academics");
    const byCategory = ms.reduce((acc, m) => ((acc[m.category] = (acc[m.category] || 0) + 1), acc), {});
    if (academics.length > 0) {
      log("PASS", `timeline returns ${academics.length} academics milestone(s) of ${ms.length} total`,
        JSON.stringify(byCategory));
      console.table(academics.map((m) => ({ date: m.date, title: m.title })));
    } else {
      log("FAIL", "timeline returns academics milestones",
        `0 academics in ${ms.length} milestone(s): ${JSON.stringify(byCategory)}\n` +
        `If the counts above look right otherwise, the migration has not been run yet:\n` +
        `  cd backend && python scripts/migrate_academics_collection.py --apply`);
    }
  }

  const filtered = await getJSON(`/api/timeline/${userId}?category=academics`);
  if (filtered.status !== 200) {
    log("FAIL", "GET ?category=academics", `status=${filtered.status}`);
  } else if (!academics.length) {
    log("SKIP", "?category=academics is consistent with the unfiltered timeline",
      "nothing to filter to — comparing 0 against 0 would pass without proving anything");
  } else {
    const ms = filtered.body?.milestones || [];
    const leaks = ms.filter((m) => m.category !== "academics");
    if (ms.length === academics.length && leaks.length === 0) {
      log("PASS", `?category=academics returns exactly those ${ms.length} milestone(s)`);
    } else {
      log("FAIL", "?category=academics is consistent with the unfiltered timeline",
        `unfiltered had ${academics.length}, filtered returned ${ms.length}` +
        (leaks.length
          ? `, and ${leaks.length} non-academics leaked in — the builder ignores category ` +
            `values it cannot map to EntityCategory, so an unmapped value returns everything`
          : ""));
    }
  }

  // The profile page reads this endpoint, and it 404s when the total is 0.
  const identity = await getJSON(`/api/identity/${userId}`);
  if (identity.status === 404) {
    log("FAIL", "GET /api/identity/{user}",
      "404 — the route returns this when no collection yields a single record for the user, " +
      "so the profile page will render its empty state");
  } else if (identity.status !== 200) {
    log("FAIL", "GET /api/identity/{user}", `status=${identity.status}`);
  } else {
    const total = identity.body?.total_entities ?? 0;
    const unfiltered = timeline.body?.milestones?.length ?? 0;
    if (academics.length && total >= unfiltered) {
      log("PASS", `identity totals ${total} entities, consistent with ${unfiltered} milestone(s)`);
    } else if (!academics.length) {
      log("WARN", "identity total includes academics",
        `${total} entities, but academics are missing upstream so this cannot be confirmed`);
    } else {
      log("FAIL", "identity total includes academics",
        `identity says ${total} but the timeline returned ${unfiltered} milestone(s) — ` +
        `identity is reading fewer collections than the timeline is`);
    }
  }

  const facet = await postJSON("/api/search/filter", {
    user_id: userId, categories: ["academics"], top_k: 100,
  });
  if (facet.status !== 200) {
    log("FAIL", "POST /api/search/filter", `status=${facet.status}`);
  } else {
    const rows = facet.body?.results || [];
    const cols = [...new Set(rows.map((r) => r.metadata?.collection))];
    if (rows.length && cols.length === 1 && cols[0] === "academics") {
      log("PASS", `faceted search returned ${rows.length} row(s) from collection "academics"`);
    } else if (!rows.length) {
      log("FAIL", "faceted search returns academics", "total_results = 0");
    } else {
      log("FAIL", 'faceted search reads the "academics" collection',
        `collections seen: ${JSON.stringify(cols)} — "academicss" means a read path still mis-names`);
    }
  }

  // ── SSE through the browser's own streaming stack ──────────────────────
  group("3. Streaming answer through ReadableStream + TextDecoder (the defect-2 fix)");
  const question = "List my academic qualifications and degrees as bullet points.";
  let raw = "";
  let events = [];
  let boundaries = 0;
  try {
    const res = await fetch(`${API}/api/search/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question, user_id: userId, top_k: 10, stream: true }),
      mode: "cors",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const ctype = res.headers.get("Content-Type") || "";
    if (ctype.includes("text/event-stream")) {
      log("PASS", `response is text/event-stream`);
    } else {
      log("FAIL", "response is text/event-stream", `Content-Type: ${ctype}`);
    }

    // Drain exactly the way api.ts does, counting real network boundaries and
    // keeping the undecoded wire text in one pass so no second LLM call is needed.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      boundaries++;
      const text = decoder.decode(value, { stream: true });
      raw += text;
      buffer += text;
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (block.trim()) events.push(parseBlock(block));
        sep = buffer.indexOf("\n\n");
      }
    }
    const tail = decoder.decode();
    raw += tail;
    buffer += tail;
    if (buffer.trim()) events.push(parseBlock(buffer));
  } catch (err) {
    log("FAIL", "streamed query", `${err.name}: ${err.message}`);
  }

  if (events.length) {
    const counts = events.reduce((a, e) => ((a[e.name || "(unnamed)"] = (a[e.name || "(unnamed)"] || 0) + 1), a), {});
    log("INFO", `stream arrived in ${boundaries} network read(s)`, JSON.stringify(counts));

    if (counts["(unnamed)"]) {
      log("FAIL", "every event on the wire is named",
        `${counts["(unnamed)"]} block(s) had no event: field — a payload was split across ` +
        `event boundaries, so part of the answer is unroutable`);
    } else if (counts.chunk && counts.done) {
      log("PASS", "event sequence complete (chunk … sources … done)");
    } else {
      log("FAIL", "stream emits chunk and done", JSON.stringify(counts));
    }

    const violations = wireViolations(raw);
    if (violations.length) {
      log("FAIL", "wire contains only legal SSE field lines",
        `${violations.length} unprefixed line(s), e.g. ${JSON.stringify(violations.slice(0, 3))}\n` +
        `Payload newlines are being emitted raw, which truncates every event.`);
    } else {
      log("PASS", "every line on the wire is a legal SSE field");
    }

    const answer = events.filter((e) => e.name === "chunk").map((e) => e.data).join("");
    if (answer.includes("I couldn't generate an answer at this time.")) {
      log("WARN", "answer has real content",
        "backend returned its no-LLM fallback — GROQ_API_KEY is missing, empty or rejected. " +
        "Check the backend terminal for a 401. Framing checks above still hold.");
    } else {
      const nl = (answer.match(/\n/g) || []).length;
      if (nl > 0) {
        log("PASS", `answer preserved ${nl} newline(s) across ${answer.length} chars`);
        console.log("%c" + answer.split("\n").slice(0, 6).join("\n"), "color:#555");
      } else if (violations.length) {
        log("FAIL", "answer preserved newlines",
          `0 newlines in ${answer.length} chars, and the wire had ${violations.length} illegal ` +
          `line(s) — the newlines are being dropped in framing, not absent from the model output`);
      } else {
        log("WARN", "answer preserved newlines",
          `the model replied in ${answer.length} chars with no line breaks, so this run did not ` +
          `exercise multi-line framing. Ask a question that forces a list and re-run.`);
      }
    }

    const srcEvent = events.filter((e) => e.name === "sources").pop();
    if (srcEvent) {
      try {
        const sources = JSON.parse(srcEvent.data);
        const withFile = sources.filter((s) => s.file_id);
        log("PASS", `sources event parsed (${sources.length} source(s), ${withFile.length} with a file_id)`,
          JSON.stringify([...new Set(sources.map((s) => s.collection))]));

        // ── Defect-3 fix: the links the UI renders must actually resolve ──
        group("4. Source links resolve cross-origin (the defect-3 fix)");
        if (!withFile.length) {
          log("SKIP", "GET /api/files/{file_id}", "no source carried a file_id");
        } else {
          let ok = 0;
          const failedIds = [];
          for (const s of withFile.slice(0, 3)) {
            const url = `${API}/api/files/${s.file_id}`;
            try {
              const r = await fetch(url, { mode: "cors" });
              r.ok ? ok++ : failedIds.push(`${s.file_id} -> ${r.status}`);
            } catch (e) {
              failedIds.push(`${s.file_id} -> ${e.name}`);
            }
          }
          const tried = Math.min(3, withFile.length);
          if (ok === tried) {
            log("PASS", `all ${ok} sampled source link(s) load from the page origin`);
          } else {
            log("WARN", "sampled source links load",
              `${ok}/${tried} loaded; failures: ${JSON.stringify(failedIds)}\n` +
              `Originals may have been cleared from backend/uploads/, or the backend was ` +
              `started from the wrong directory so upload_dir points elsewhere.`);
          }
        }
      } catch (e) {
        log("FAIL", "sources event parses as JSON", srcEvent.data.slice(0, 200));
      }
    } else {
      log("WARN", "stream emits a sources event", "none received");
    }
  }

  // ── Does it reach the screen? ──────────────────────────────────────────
  group("5. Rendered DOM");
  const onTimeline = window.location.pathname.includes("timeline");
  if (!onTimeline) {
    log("SKIP", "academics rendered in the timeline",
      `you are on ${window.location.pathname} — open /timeline and re-run to check this`);
  } else if (!academics.length) {
    log("SKIP", "academics rendered in the timeline", "the API returned none to render");
  } else {
    const text = document.body.innerText || "";
    const shown = academics.filter((m) => m.title && text.includes(m.title.slice(0, 28)));
    if (shown.length) {
      log("PASS", `${shown.length}/${academics.length} academics milestone(s) are visible on the page`,
        `e.g. "${shown[0].title}"`);
    } else {
      log("FAIL", "academics milestones are visible on the page",
        `the API returns ${academics.length} but none of their titles appear in the DOM. ` +
        `Hard-reload (Ctrl+Shift+R) to clear a stale render, then re-run.`);
    }
    const hasFilterChip = /\bAcademics\b/.test(text);
    if (hasFilterChip) {
      log("PASS", 'an "Academics" label is present in the UI');
    } else {
      log("INFO", 'no "Academics" filter chip in the UI',
        "known gap: timeline/page.tsx hardcodes its category list and omits academics, so the " +
        "entries appear in the unfiltered view but cannot be filtered to. Two-line fix, not yet applied.");
    }
  }

  // ── Summary ────────────────────────────────────────────────────────────
  return finish();
})();
