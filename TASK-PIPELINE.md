# PIPELINE — clipper.py: real clipping backend (FAKE-mode testable), writes UI-compatible jobs

Follow-up to TASK.md / TASK-FIX.md / TASK-CAPTIONS.md (same project root). The UI + mock server are done and pass their suites. This brief builds the REAL pipeline CLI from `ai-clipper-design.md` (read it first — stage contracts §3, prompt contract §4). One concern: `clipper.py` (+ tiny glue). The UI must keep working **unchanged** (server already scans `work/*/metadata.json`).

## Deliverable: `clipper.py` (Python stdlib ONLY — `urllib`, `json`, `subprocess`, `argparse`, ...; zero pip installs) + `ffmpeg`/`ffprobe` (installed: ffmpeg 8.1.1; `yt-dlp` is NOT installed)

### CLI
```
python clipper.py run --fake <job_name> [--template <template_id>]   # deterministic offline end-to-end
python clipper.py run <youtube_url_or_file> [--template <template_id>] [--lang id|en] [--target-len 45] [--max-clips 10]
python clipper.py resume <job_id>
```
Default `--template karaoke-classic`. Jobs land in `work/<job_id>/` with `manifest.json` stage tracking (ingest|asr|normalize|select|render|package → done/failed) exactly as `ai-clipper-design.md` §2. Re-running skips stages marked done (log `skip <stage> (already done)`).

### FAKE mode (`--fake`, CLIPPER_FAKE=1 equivalent) — deterministic, offline, must exercise the REAL mechanics
- **Ingest REAL:** synthesize source with ffmpeg: `testsrc2` + `sine` tone, 1280×720, 30fps, **150 s**, → `work/<id>/source.mp4` (H.264+AAC). Extract `audio.flac` (16 kHz mono) exactly like the real path.
- **ASR FAKE:** write `transcript.json` from a built-in deterministic script (data-engineering sentences with word-level timestamps spread across the 150 s) — same schema as the real Groq path (words + sentence segments with start/end).
- **Normalize REAL:** the real sentence-grouping code consumes the fake word stream (don't bypass the stage).
- **Select FAKE:** deterministic `segments.json` with **3 clips: 35 s, 41 s, 55 s** (all inside 20–59 s), cut at sentence boundaries, with title/hook/caption/hashtags/virality_score (e.g. 88/72/45) matching the schema in `ai-clipper-design.md` §4.
- **Render REAL:** actual ffmpeg per clip — crop 9:16 (source is 720p landscape → real crop+scale to 1080×1920), 30 fps, libx264 CRF 20, AAC 128k, **burned captions**: generate `clips/NN.ass` from word timestamps using the chosen template's `ass` block from `static/caption-templates.json` (map: fontname/fontsize/bold/colours as `&HAABBGGRR`/`&HBBGGRR`, outline, shadow, alignment, MarginV, uppercase, words_per_cue; effects `karaoke`/`pop`/... map to at least: karaoke `{\k}` tags for `karaoke`+`pop`+`bounce`+`glow`, `{\fad}` fade for `clean`, per-word cue for `typewriter`, `{\an2\bord}` bar look for `ticker` — a faithful static approximation is fine; note mapping choices in NOTES) → `ffmpeg ... -vf "crop=...,scale=1080:1920,fps=30,ass=NN.ass"`. Hook text overlay first 3 s via `drawtext` or an ASS intro line (your choice; document it).
- **Package REAL:** `clips/NN_slug.mp4`, `clips/NN.srt`, `clips/NN_poster.jpg` (frame at clip start +1 s), `metadata.json`.

### Real mode — implemented but NOT testable here (no keys yet)
- Ingest: file → `source.mp4` (copy if H.264, else transcode); URL → `yt-dlp` if on PATH else exit with clear `yt-dlp not installed` message.
- ASR: Groq `whisper-large-v3-turbo` via `urllib` (multipart upload, `response_format=verbose_json`, word timestamps; 10-min chunking + 3 s overlap offsetting per design doc).
- Select: DeepSeek `deepseek-flash` chat completions, JSON output, the exact prompt contract from `ai-clipper-design.md` §4 (20–59 s, sentence boundaries + 0.2 s pad, no overlaps, validate + snap output).
- Keys `GROQ_API_KEY` / `DEEPSEEK_API_KEY` from env; missing key → clear error naming the key. Real-mode calls are NOT part of acceptance — report `NOT RUN (no API keys)` honestly.

### UI compatibility contract (hard)
`work/<job_id>/metadata.json` MUST use the same keys/shape as `work/demo-job/metadata.json` (read that file first; it is the contract) plus additive fields only: `filename`, `srt` (per clip), `caption_template` (default from `--template`). The UI's jobs list reads `work/*/metadata.json` + `manifest.json` — a new job must appear in `GET /api/jobs` and render on `job.html?id=<job_id>` **with zero UI changes**. If a server change is strictly required (e.g. video streaming route for `<video>` playback of `clips/NN_slug.mp4` — check how `server.py` serves job files today), the minimal additive route is allowed; no other server/UI edits.

## Acceptance criteria (ALL in the FOREGROUND, FAKE mode, paste real output)
1. `python clipper.py run --fake demo2` → exit 0. `work/demo2/` contains `source.mp4`, `audio.flac`, `transcript.json`, `segments.json`, `metadata.json`, `manifest.json` (all 6 stages `done`), `clips/` with 3× `NN_slug.mp4`, 3× `NN.srt`, 3× `NN_poster.jpg`, ≥1 `NN.ass`.
2. `ffprobe -print_format json` (parsed with `python -c`) on each clip mp4: `width==1080`, `height==1920`, duration in **[20, 59]**, video codec h264, audio codec aac.
3. With `python server.py` running (start, test, then kill it — bounded): `GET /api/jobs` contains `demo2`; `GET /api/jobs/demo2` → `len(clips)==3`, every clip has `caption_template` and `srt`; `GET /api/jobs/demo2/srt/1` returns SRT starting `1\n00:00:00` (or clip-relative `00:00:00`).
4. Template wiring: `python clipper.py run --fake demo2b --template bold-pop` (fresh job) → its generated `.ass` differs from `demo2`'s karaoke `.ass` (assert: `python` diff shows different `FontSize` and/or `PrimaryColour` lines) and its 3 mp4s exist.
5. Idempotency: re-run `python clipper.py run --fake demo2` → exit 0, stdout contains 6× `skip`, no file corruption (`python verify.py`-style JSON parse of `work/demo2/metadata.json` succeeds).
6. No regressions: `python verify.py` → ALL 8 PASS; `node check-overflow.js` → 8 rows 0-overflow, exit 0.
7. Screenshots with the project's Chrome (`C:/Program Files/Google/Chrome/Application/chrome.exe --headless=new --virtual-time-budget=6000`, server running): `.tmp/pipe-job-1440.png` = `job.html?id=demo2` at 1440×2400 (must show the 3 real clips with scores/durations), `.tmp/pipe-clip-1440.png` = a 1440×900 crop/full of clip 1's card. List with sizes.

## Constraints
- Zero pip deps anywhere; Node only for the existing check scripts (do not modify them).
- All writes inside the project dir; no `/dev/null` (use `.tmp/` file sinks); no `&`-backgrounded servers without bounded kill; run acceptance in the FOREGROUND.
- No subagents — do all edits yourself. No deploy. Planning short — implement first.
- Do not break `verify.py` / `check-overflow.js` / `check-captions.js` (they gate acceptance). Do not edit `TASK*.md` or `ai-clipper-design.md`.
- Windows note: pass ffmpeg filters with proper quoting (`ass=...`, `crop=...`); native tools need forward-slash paths.

## Report format
```
REPORT
- Files created/changed: <list>
- ASS effect mapping: <effect → ffmpeg/ASS technique used>
- Acceptance 1-7: <pass/fail with key output lines>
- Real mode: NOT RUN (no API keys) — list the exact curl/request shape each call would make
- Deviations: <or none>
NOTES
- <caveats>
```
