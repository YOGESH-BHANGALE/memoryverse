# MemoryVerse AI — Deploy From Scratch

This guide deploys the whole app from zero. There are **two separate pieces**:

| Piece | Tech | Host |
|-------|------|------|
| **Backend** (API) | FastAPI + Groq + ChromaDB | **Render** (Docker) |
| **Frontend** (UI) | Next.js 14 | **Vercel** |

They deploy separately. The frontend needs the backend's URL, so **always deploy the backend first, the frontend second.**

> Your backend is **already live** at `https://memoryverse-backend-bju3.onrender.com` with `GROQ_API_KEY` set and working. If you're reusing it, skip to **Step 3** and use that URL. The steps below are for a clean, from-scratch setup.

---

## Prerequisites (one-time)

1. **GitHub** repo with the code pushed — yours is `YOGESH-BHANGALE/memoryverse`, branch `main`. ✅ done.
2. **Groq API key** — free at <https://console.groq.com/keys> → *Create API Key* → copy it (starts with `gsk_...`). Keep it secret.
3. **Render account** — <https://render.com> (sign in with GitHub).
4. **Vercel account** — <https://vercel.com> (sign in with GitHub).

---

## Step 1 — Code on GitHub (already done)

Your code is on `main`. Whenever you change something later, redeploy by pushing — Render **and** Vercel auto-redeploy on every push to `main`:

```bash
cd "E:/MEMORYVERSE HAKATHPN/memoryverse-ai"
git add -A
git commit -m "your message"
git push origin main
```

---

## Step 2 — Deploy the BACKEND to Render

1. Render dashboard → **New +** → **Web Service**.
2. **Connect GitHub** → select the `memoryverse` repo.
3. Configure:
   - **Name:** `memoryverse-backend` (anything)
   - **Language / Runtime:** **Docker**
   - **Root Directory:** `backend`  ← **important** (the repo holds backend *and* frontend)
   - **Branch:** `main`
   - **Instance Type:** Free
   - Render auto-detects `backend/Dockerfile`.
4. **Environment Variables** → Add:
   - `GROQ_API_KEY` = your `gsk_...` key  ← **the only required secret**
   - *(optional)* `GROQ_MODEL` = `openai/gpt-oss-120b` (leave unset to use the built-in default)
   - ⚠️ **Do NOT add `PORT`** — Render injects its own; the Dockerfile reads it via `${PORT}`. Setting it breaks the health check.
5. Click **Create Web Service**. First build takes **~3–5 min** (pure-Python deps plus a one-time bake of the ~80 MB ONNX embedding model — no PyTorch).
6. Copy the live URL, e.g. `https://memoryverse-backend-xxxx.onrender.com`.
7. Test: open `https://<your-backend-url>/health` in a browser → returns a **200** healthy response. (First hit after idle can take ~60s to wake.)

---

## Step 3 — Deploy the FRONTEND to Vercel

1. Vercel dashboard → **Add New… → Project**.
2. **Import** the `memoryverse` repo.
3. Configure:
   - **Framework Preset:** Next.js (auto-detected)
   - **Root Directory:** click **Edit** → set to `frontend`  ← **important**
4. **Environment Variables** → Add:
   - **Name:** `NEXT_PUBLIC_API_URL`
   - **Value:** your backend URL from Step 2, e.g. `https://memoryverse-backend-bju3.onrender.com` (no trailing slash)
   - ⚠️ This is **just a URL, not a secret**. **Never** put `GROQ_API_KEY` on Vercel — `NEXT_PUBLIC_*` variables are baked into the browser bundle and would leak the key publicly.
5. Click **Deploy** (~2 min). You get a URL like `https://memoryverse-xxxx.vercel.app` — that's your live app.

---

## Step 4 — Verify

1. Open your Vercel URL.
2. **Warm up the backend first:** the free Render server sleeps after ~15 min idle, so the *first* request after it wakes takes ~30–60s while the container starts. The upload page now retries automatically across that window (you'll see "Waking the server…"), so just wait — you no longer need to upload twice.
3. Upload a resume → it extracts skills/projects/certs with zero manual tagging → check **Dashboard**, **Graph**, **Timeline**, **Search**.

---

## Free-tier realities (important for demos)

- **Data is temporary.** Render's free tier wipes uploaded data on restart/sleep. Upload fresh right before demoing. To persist data, add a paid Render **Disk** or a hosted vector DB.
- **Cold starts.** First request after idle takes ~30–60s while the server wakes.
- **CORS** is already open (`*`) on the backend, so any Vercel domain can call it — no extra config.
- **512 MB is the real constraint.** The container is memory-capped, and a worker that exceeds it is OOM-killed rather than returning an error — which shows up as a **502 with an empty body**, and takes the whole service down until Render restarts it. A caught application error would be a 500 with JSON, so an empty 502 always means "the process died," not "the code raised." This is why the runtime ships without PyTorch and bounds the embedding batch size.

---

## Diagnosing the live backend

The free tier gives no shell, no metrics and no retained logs, and `/` returns a
hardcoded `1.0.0` — so you cannot tell from outside which image is running. Two
endpoints exist for that:

```bash
curl -s https://memoryverse-backend-bju3.onrender.com/api/diag
```

Reports `build_marker` (bump it in `backend/app/api/routes/diag.py` on each
deploy — this is how you confirm a push actually replaced the running image,
since **a failed Render build silently keeps serving the previous one**), plus
the cgroup memory limit/current/peak, RSS, CPU count vs. granted affinity,
thread caps, and whether torch is installed or loaded. Credentials appear only
as `groq_key_present: true/false` — never as values.

```bash
curl -s -X POST https://memoryverse-backend-bju3.onrender.com/api/diag/probe -F "file=@resume.docx"
```

Walks the ingest pipeline one stage at a time (parse → extract → categorize →
embed → store → graph), reporting memory and elapsed time after each, so you can
see *which* stage consumes the headroom. It writes under a separate
`__diag_probe__` user, so it never pollutes the demo identity.

---

## Optional — Run locally instead (no cloud)

With **Docker Desktop** running, from the repo root:

```bash
# 1) put your key in backend/.env  (copy the template first)
cp backend/.env.example backend/.env   # then edit GROQ_API_KEY

# 2) start both services
docker-compose up --build
```

- Backend → <http://localhost:8000>
- Frontend → <http://localhost:3000>
