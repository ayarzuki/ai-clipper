# TASK — Build the Web UI for AI Clipper (v1, mock-backed)

You are building the front-end + thin local server for "AI Clipper", a tool that turns long videos into 9:16 shorts for Instagram Reels / TikTok / YouTube Shorts. Project root = the directory you are run in (`~/ai-clipper`). Read `ai-clipper-design.md` (pipeline design) and `ai-clipper-architecture.html` (architecture) in this directory for context. The pipeline backend (clipper.py) does NOT exist yet — the UI must run fully on MOCK data now and be ready to swap to real `work/<job_id>/` folders later.

## Scope (one concern: UI + mock API only)

1. `server.py` — Python **stdlib only** (`http.server`/`json`, NO pip installs, NO external packages). Serves static files from `static/` and a JSON API. Port 8765 (override via env `PORT`).
2. `static/` — the web UI. **No build step** (plain HTML/CSS/JS, no npm, no bundler, no CDN scripts). Google Fonts link allowed but the UI must look right without it (font-family fallback).
3. `work/demo-job/` — one mock job folder with `manifest.json`, `transcript.json`, `metadata.json` (3 clips). The server reads jobs by scanning `work/*/metadata.json` (so the real pipeline drops in later with zero UI changes).

## UI design (implement exactly; dark theme)

Global: background `#020617`, cards `rgba(15,23,42,0.5)` + border `#1e293b`, radius 12px, mono font (JetBrains Mono → `ui-monospace` fallback). Accent cyan `#22d3ee`, success emerald `#34d399`, warn amber `#fbbf24`, error rose `#fb7185`, violet `#a78bfa` for scores. Responsive 360px → 1440px. Page-level horizontal scroll is a defect.

### Page 1 — Dashboard (route `/`)
- Header: "AI Clipper" + tagline "long video → 9:16 shorts".
- **New Job card**: input "YouTube URL or file path" (text), select `language` (id/en), range slider `target length` (20–59 s, default 45), number `max clips` (default 10), button "Start clipping" → POST `/api/jobs` (mock returns the demo job; show toast "Mock mode — pipeline not wired yet").
- **Jobs list**: rows per job — job id, source name, status chip (queued/running/done/failed), clip count, created date, per-stage mini stepper (6 dots: Ingest, ASR, Normalize, Select, Render, Package), click → `/job.html?id=<job_id>`.
- Empty state text when no jobs.

### Page 2 — Job detail (`static/job.html?id=...`)
- Header: source name, duration, "≈$0.04/hr" cost chip, back link.
- **Stage stepper** (horizontal, wraps on mobile): the 6 stages with states done (emerald) / running (amber, pulsing dot) / pending (slate) / failed (rose).
- **Transcript panel** (collapsible `<details>`): timestamped lines `[HH:MM:SS] text` from `transcript.json`.
- **Clip grid** (auto-fill, min 220px): one card per clip (see below). Legend: score color and duration rules.

### Clip card
- 9:16 preview area (160×285 approx): real `<video>` if `clips/NN_slug.mp4` exists in the job folder, else a styled placeholder with the `hook` text rendered large (this is the mock case).
- Badge row: virality score pill (0–100: ≥80 emerald, 50–79 amber, <50 slate) + duration chip (**20–59 s emerald, 60–180 s amber, >180 s rose**).
- Editable fields (textarea/input, saved to localStorage only — no backend write in v1): `title`, `hook` (max 7 words enforced in UI), `caption`, `hashtags` (comma chips).
- Buttons: "Download MP4" (disabled with tooltip in mock), "Download SRT" (works — server serves generated SRT from transcript times), "Copy caption" (clipboard).

### Mock data (`work/demo-job/metadata.json`)
3 clips: `score 88, 41s` ("The 3 rules of great data pipelines"), `score 72, 75s` (amber — shows long-duration warning), `score 45, 12s` (rose — shows too-short warning). Give each realistic title/hook/caption/hashtags (topic: data engineering), and `segments.json`-style start/end times. `transcript.json`: ~12 timestamped lines that plausibly contain those clips. Duration warnings must be VISIBLE on the cards (this is the point of the demo).

## API contract (mock, stdlib server)
- `GET /api/jobs` → `{"jobs":[{job_id, source, status, clip_count, created, stages:{ingest:"done",...}}]}`
- `GET /api/jobs/<id>` → `{job_id, source, duration_s, stages:{...}, transcript:[{start,end,text}], clips:[{id, start, end, title, hook, caption, hashtags:[], virality_score, filename, srt}]}`
- `POST /api/jobs` body `{url_or_path, language, target_len_s, max_clips}` → `{"job_id":"demo-job","mock":true}` (201)
- `GET /api/jobs/<id>/srt/<clip_id>` → generated SRT text from clip start/end + transcript words
- Unknown job → 404 JSON `{"error":"not found"}`.

## Hard constraints
- ZERO external dependencies: no pip/npm installs, no CDN JS. `python server.py` on stock Python 3.11 must run it.
- Every write stays inside this project directory. Do NOT touch `/tmp`, other home dirs, or any existing project. Windows/git-bash: never redirect to `/dev/null` — use a file sink inside the repo (e.g. `.tmp/`).
- **Do all edits yourself. Do NOT delegate to a subagent** (a UI Engineer subagent will hang this run).
- No backgrounded servers inside your scripts: for acceptance, start the server in the FOREGROUND of a script step, curl it, then kill it with a bounded kill. If you must use `&`, add `wait`-bounded cleanup and a `taskkill`/`kill` fallback.
- No git commits needed. Do not deploy anything. Do not create files named like the docs already in the root (`ai-clipper-design.md` etc. are read-only inputs).
- Keep planning short — apply edits first, cap planning at ~2 minutes.

## Acceptance criteria (run these yourself in the FOREGROUND; paste real output in the report)
1. `python server.py` starts and `curl -s -o .tmp/home.html -w "%{http_code}" http://127.0.0.1:8765/` → `200`.
2. `curl -s http://127.0.0.1:8765/api/jobs` → valid JSON containing `"demo-job"` (verify with `python -c "import json,sys; ..."` — do not use jq).
3. `curl -s http://127.0.0.1:8765/api/jobs/demo-job` → JSON with `len(clips)==3`, scores `[88,72,45]`, durations `[41,75,12]`.
4. `curl -s http://127.0.0.1:8765/api/jobs/demo-job/srt/1` → SRT text starting with `1\n00:00:00`.
5. `curl -s http://127.0.0.1:8765/` body contains the exact strings `AI Clipper`, `Start clipping`, `Virality`.
6. `curl -s http://127.0.0.1:8765/job.html?id=demo-job` body contains `The 3 rules of great data pipelines`, `Download MP4`, `Copy caption`.
7. `python -c` JSON parse of step 2/3 output succeeds (no trailing garbage).
8. A `verify.sh` (or `verify.py`) in the project root runs all of the above end-to-end and exits 0.

If something cannot run on this machine, report `NOT RUN: <reason>` instead of fabricating output. Numbers in the report must come from an actual run — if a harness is unavailable, say so in NOTES.

## Report format (end of your reply)
```
REPORT
- Files created/changed: <list>
- How to run: <command>
- Acceptance 1-8: <pass/fail per item, with the key output line>
- Deviations: <or none>
NOTES
- <honest caveats>
```
