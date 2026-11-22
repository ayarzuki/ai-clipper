# WIRING — "Start clipping" button runs clipper.py for real (one concern: UI → pipeline glue)

Follow-up to all prior TASK*.md (same project root). `clipper.py` (real CLI, FAKE mode works end-to-end), `server.py` (mock API), UI, and 3 check suites exist and pass. This brief replaces the mock `POST /api/jobs` with real pipeline execution. Everything else stays as-is.

## Behavior

### Server (`server.py`, still zero-dep stdlib only)
- `POST /api/jobs` body `{url_or_path, language, target_len_s, max_clips, mode}` where `mode` ∈ `"fake"` | `"real"` (default `"fake"`):
  - Generate `job_id` = slug of the source (≤ 24 chars) + `-` + `YYYYMMDD-HHMMSS` (always unique).
  - Launch `subprocess.Popen([sys.executable, "clipper.py", "run", ...], cwd=project root)` with **arg list, never `shell=True`**:
    - `mode="fake"` → `run --fake <job_id>` (clipper treats the name as the job id — if it currently uses the name only as label, adapt minimally so outputs land in `work/<job_id>/`).
    - `mode="real"` → `run <url_or_path> --lang <language> --target-len <target_len_s> --max-clips <max_clips>`.
  - Respond `201 {"job_id": ..., "mode": ..., "status": "queued"}` immediately; stream child stdout to `work/<job_id>/run.log`.
  - **Concurrency guard (v1):** if another job's manifest `status` is `queued`/`running`, respond `409 {"error":"a job is already running","job_id":<existing>}`. The child updates `work/<job_id>/manifest.json` (`status`: queued→running→done/failed, per-stage states) exactly as `clipper.py` already does — if clipper doesn't yet write `status` at job level, add it (small change).
  - If the child exits non-zero → manifest `status: failed`, and if clipper printed an error line, surface it as `manifest.error` (e.g. missing `GROQ_API_KEY`, `yt-dlp not installed`). Clipper already errors clearly; capture stderr into `run.log` and copy the last meaningful error line into `manifest.error`.
  - Input validation: reject empty `url_or_path`; reject strings containing NUL/newlines. `;`, `|`, `$()` etc. need NO special handling — the arg list already makes them inert (they'd be part of one filename arg and simply not exist).
- `GET /api/jobs/<id>` now also returns top-level `status` and `error` (from manifest), additive to the existing shape.

### UI (minimal edits only)
- **New Job form (index.html/app.js):** add a `mode` select — "Demo mode (fake pipeline)" (default) / "Real mode (needs API keys)". On submit → `POST /api/jobs`; success: toast with the real `job_id` + navigate to `job.html?id=<job_id>`; `409`: toast "Another job is already running — <id>"; other errors: toast the message.
- **Progress:** `job.js` polls `GET /api/jobs/<id>` every **2 s** while `status` is `queued`/`running` (stop on `done`/`failed`); the stage stepper already has pending/running/done/failed visuals — drive them from `manifest.stages`. Show `manifest.error` in a rose banner when `failed`. Jobs list on index: same 2 s polling, status chip shows running (amber, pulsing dot).
- Caption-template picker and everything else keep working untouched.

## Acceptance (FOREGROUND, paste real output; use a python script in `.tmp/` if heredocs mangle quotes)
1. Start `python server.py` (bounded: start, test, kill). `POST /api/jobs` `{"url_or_path":"fake:mytest","language":"en","target_len_s":45,"max_clips":10,"mode":"fake"}` → `201`, `job_id` matches `<slug>-<timestamp>`. Poll `GET /api/jobs/<id>` every 2 s (timeout 300 s) → `status` reaches `done`, `len(clips)==3`, clips have `srt`, and `work/<job_id>/clips/*.mp4` exist (3 files).
2. Concurrency: while that job is `running`, a second `POST /api/jobs` → `409` with `job_id` of the running one.
3. Injection safety: `POST /api/jobs` `{"url_or_path":"x; echo pwned > .tmp/pwned.txt","mode":"real"}` → response `201` or clean `4xx`, job ends `failed` (file-not-found style error surfaced in `manifest.error`), AND `.tmp/pwned.txt` does NOT exist afterwards. Assert explicitly.
4. Real-mode missing keys: `POST` `{"url_or_path":"nonexistent.mp4","mode":"real"}` (with `GROQ_API_KEY`/`DEEPSEEK_API_KEY` unset in the server env) → job `failed` with a clear `manifest.error` (file missing or key missing — whatever fails first is fine, the message must name the cause).
5. `node check-wiring.js` (NEW, Node ≥21 built-ins + CDP, same pattern as `check-captions.js`): headless Chrome on `job.html?id=<the successful fake job>` and `index.html` asserts: (a) submitting the form with mode=demo navigates/lands on a job page and a toast appears (or the new job row appears in the list); (b) while a job runs (kick one via fetch POST from the page), the job page shows a non-"done" stage state at least once and reaches "done" within 300 s of polling; (c) failed-job error banner path: set `work/<id>/manifest.json` `{"status":"failed","error":"test error 123"}` on a scratch job folder, open its job page → body contains `test error 123`. Exit 0 only if all pass.
6. Regressions: `python verify.py` ALL 8 PASS (its `POST /api/jobs` criterion now hits the REAL endpoint — if verify.py asserts the old mock response, update ONLY that assertion to accept `201` + `job_id`), `node check-captions.js` ALL PASS, `node check-overflow.js` 8 rows 0-overflow.
7. Screenshot: `.tmp/wire-job-1440.png` = `job.html?id=<successful fake job>` at 1440×2400 with server running (shows completed stages + 3 clips). List with size.

## Constraints
- `server.py` + static assets remain zero pip deps; no new npm deps (Node only for `check-wiring.js`).
- `subprocess.Popen` arg-list only, never `shell=True`; child env = `os.environ` copy (so real mode can find keys).
- All writes inside the project dir; no `/dev/null`; no subagents; no deploy; run acceptance in the FOREGROUND with bounded server start/kill.
- Do not modify `clipper.py` beyond the two small noted items (job-level `status` in manifest, `--fake <job_id>` id naming) and do not touch the render logic, `TASK*.md`, or existing check scripts' assertions except the one `verify.py` mock-response item.

## Report format
```
REPORT
- Files changed: <list>
- API contract changes: <additive fields / status values>
- Acceptance 1-7: <pass/fail with key output lines>
- Deviations: <or none>
NOTES
- <caveats>
```
