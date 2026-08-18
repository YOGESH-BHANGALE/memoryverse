# MemoryVerse AI — Demo Runbook

A tight, rehearsable path that proves the success metric:

> *Uploading a resume + certificate + project report results in an organized,
> connected, searchable digital identity — with zero manual folder/tag work.*

Everything below has been verified end-to-end against the running app.

---

## 0. One-time setup (do this before the audience is watching)

1. **Start both servers.** From the app, the launch configs are `backend`
   (uvicorn `--reload`, port **8000**) and `frontend` (Next.js, port **3001**).
   Wait until both answer:

   ```bash
   curl -s -o /dev/null -w "backend %{http_code}\n" http://localhost:8000/health
   curl -s -o /dev/null -w "frontend %{http_code}\n" http://localhost:3001
   ```

2. **Pin the demo identity — one click.** Open this URL once. The `?user=` param
   writes the id into the cookie **and** localStorage, so every page stays pinned
   to it for the rest of the session — no console, no reload:

   ```
   http://localhost:3001/dashboard?user=a7b3e329-1832-45a7-9f3f-428468acddff
   ```

   This user already holds **112 entities** across all six categories — a
   believable "finished" identity to show off before the live upload. Bookmark
   the link; clicking it is the whole setup.

   *(Need a fresh sample identity instead? Run
   `backend/venv/Scripts/python.exe scripts/seed_demo.py <uuid>` — it seeds a
   small demo user, rebuilds the graph, and prints that user's own `?user=` URL.
   It refuses the literal `default`, which the frontend ignores.)*

---

## 1. The 90-second happy path

Open pages in this order. The story is *pile of documents → organized,
connected, searchable identity* — tell it in that order.

| # | Page | What to say | What they see |
|---|---|---|---|
| 1 | **Dashboard** (`/dashboard`) | "No folders, no tags — the system sorted everything itself." | Total **112**, six category cards that sum to it: Skills **78** · Achievements **11** · Projects **10** · Certifications **5** · Internships **5** · Academics **3**. |
| 2 | **Timeline** (`/timeline`) | "The same identity, chronologically." | Year sections **2026 / 2025 / 2024**, a category badge and importance stars on every card, undated items sorted last (never faked). |
| 3 | **Knowledge Map** (`/graph`) | "Relationships, not just vector neighbours — every edge shows *why*." Click the **RiverGuard** node — the top hub, 14 connections. | 70 edges. The detail panel lists each connection with its receipts: 🛠️ tech-stack match, 🕒 temporal proximity, 📄 same-document, 🧠 skill level — confidence is the **sum of that evidence**, ordered declared-first. |
| 4 | **Ask AI** (`/search`) | "Ask in plain English." Click the four suggestion chips in turn. | See §2. |

Then the **live upload** (§3) — the actual "wow": watch a brand-new document get
sorted, scored, and connected with zero manual work.

---

## 2. The four retrieval queries (all verified)

Use the one-click suggestion chips on `/search`. Each shows an **"Understood as"**
intent chip and, where relevant, an **🗂️ Original documents** panel with working
download links.

| Query | Understood as | Result |
|---|---|---|
| `show all my certificates` | `categories=certification` | the 5 certifications, answer grounded in them |
| `show my AI projects` | `categories=project` | narrowed to the AI projects, with tech stacks |
| `show internship documents` | `categories=internship; documents` | **only the 3 files internships were actually extracted from** — the GitHub link is correctly excluded — each with a download link and an "N extracted" count |
| `show my latest resume` | `documents:resume; latest` | exactly **1** file, the newest resume, answer built from its own text |

**Best single line to say here:** *"'internship documents' returns the files the
internships came from — not every file I ever uploaded. The router inverts entity
provenance to answer it."*

**Citations are scoped to the answer.** For a document question the source panel
lists only the resolved files — "latest resume" cites just that one résumé, not
the other resumes or the GitHub-profile link elsewhere in the corpus. Same
discipline as the intent router, now applied to the receipts.

**Heads-up — the demo corpus holds more than one person's resume** (it is a shared
test identity). "show my latest resume" answers from the newest resume *file* by
upload time, which happens to be **Harshal Andhale's**, not the dashboard owner.
Say *"the system surfaced and answered from the most recent resume document"* —
not *"my personal resume."* The file list and citations are correct; only the
name inside that newest file belongs to someone else.

---

## 3. Live upload — the zero-manual-work moment

1. Go to **Upload** (`/upload`).
2. Drop in **one** document. Good choices:
   - `demo_project_report.txt` (repo root) — the RiverGuard flood-warning report, or
   - any fresh resume / certificate / project PDF.
3. Narrate while it runs: *"Parse → LLM extract → categorize → embed → connect.
   I'm not choosing a folder or typing a tag."*
4. It reports the entities it found (RiverGuard yields **9**: 7 skills, 1 project,
   1 achievement) — each auto-categorized and importance-scored.
5. Jump to **Knowledge Map** and click the new project. It is already wired into
   the existing corpus with explainable edges (declared tech-stack matches at
   65–75%, the prize at 60%, inferred same-document skills at 50%).

**Prove immutability (optional, strong for technical judges).** Every result links
to `GET /api/files/{file_id}`, which streams the original bytes back untouched:

```bash
curl -s -D - -o /tmp/roundtrip.txt "http://localhost:8000/api/files/<file_id>"
# content-disposition carries the original filename; content-type matches;
# sha256 of the download equals the source file.
```

---

## 4. Watch-outs

- **Re-uploading the same file duplicates it.** A second upload gets a fresh
  `file_id` and adds its entities again alongside the originals. Fine for a
  one-shot demo; if you rehearse the live upload repeatedly, either delete the
  prior copy or upload a different file each run.
- **Don't demo on a fresh/empty user.** The rich dashboard, timeline, and graph
  all depend on the seeded UUID in §0. A blank user shows empty states.
- **Cold start is slow.** The first request loads the Sentence-Transformers model
  and warms Chroma. Hit `/health` and open one page *before* going live so the
  first click the audience sees is instant.
- **`↻ Rebuild graph`** on `/graph` is only needed after code changes to the
  relationship engine — normal uploads already rebuild the whole graph. Don't
  click it mid-demo; it recomputes the entire corpus.
- **Unconnected nodes are honest, not broken.** About half the map (53 of 114
  nodes, mostly one-off skills) has no edges. The engine draws a link only when
  there is real evidence — shared tech, same document, temporal overlap, a career
  signal — and refuses to invent one. If you click around live, click a **hub**
  (RiverGuard **14**, MemoryVerse AI **9**, Traveo **7**), not a lone skill.
- **Skip the two faint `built_during` edges** (IncidentForge ↔ the Ethara AI
  internship, **30%**). They lean on a single weak "shared technology" signal and
  are the least convincing thing on the map. Every other edge type carries
  stronger receipts — click a `used_in`, `developed`, or `recognised_by` edge if a
  judge wants the evidence breakdown.
- **A scanned/encrypted PDF or an unsupported file type fails cleanly, not
  scarily.** The upload returns a plain `400` with a readable message
  ("Could not extract enough text…" or "Unsupported file type: .xyz") instead
  of a 500 stack trace. If a judge hands you an awkward file, the app says why —
  just pick a text-bearing PDF/DOCX/TXT instead.

---

## 5. If something breaks live

- **A page is empty / spinning** → the user id isn't set. Re-open the §0 URL
  (`/dashboard?user=a7b3e329-…`); the param re-pins the identity on load.
- **Search returns nothing** → check the backend is up (`/health`); the retrieval
  path degrades gracefully but needs the server.
- **Upload hangs on "Extracting…"** → the Groq call is slow or rate-limited; there
  is a second fallback model, but if both are down, switch to showing the
  already-populated identity (§1) — the ingest is the only step that needs the LLM
  live.
