# FIX — Responsive overflow + label defects (one concern: layout correctness)

Follow-up to TASK.md (same project root, UI already built: `server.py`, `static/`, `verify.py`). Independent visual review of headless screenshots found the following DEFECTS against the original constraint "Responsive 360px → 1440px. Page-level horizontal scroll is a defect."

## Evidence (screenshots in `.tmp/`: home-360.png, home-1440.png, job-360.png, job-1440.png)

1. **`job.html` @360px — page-level horizontal overflow (DEFECT).** The job source string is an unbreakable YouTube URL token; it forces the content column wider than the viewport. Observed: card right edges and the cost pill's right border are cut off at the screen edge; the metadata line "3 candida…" is clipped. Also the header flex row (badge `demo-job` + title) has no `min-width: 0` on the shrinking child, so the badge and heading collide with zero gutter.
2. **`index.html` @360px — overflow in the jobs card header.** The "6-Stage Engine: Ingest · ASR · Normalize · Select · Render · Package" line is clipped mid-word ("Packag…") at the right edge instead of wrapping.
3. **Stage label renders "Asr", must render "ASR".** A capitalize/text-transform or title-case formatter is mangling acronyms. Render stage labels verbatim: `Ingest, ASR, Normalize, Select, Render, Package` (also fix the jobs-card stepper tooltips/aria-labels if they use the same formatter).
4. **Clip cards visually uneven (`job.html` @1440px, cosmetic).** Cards 2 and 3 have warning banners and card 1 does not, so `TITLE` sections start at different heights. Make cards equal-height flex columns (badge row and warning slot always reserved or banner area fixed-height) so fields align across the grid.
5. **`index.html` @1440px (cosmetic).** In the jobs table, the SOURCE VIDEO cell's ellipsized URL has zero gutter against the STATUS column and starts a few px left of its column header. Give the cell `padding-right` + `text-overflow: ellipsis; overflow: hidden; white-space: nowrap;` and align it to the header.

## Required fixes (mechanism, not just the symptom)

- Long unbreakable strings (URLs) must wrap: `overflow-wrap: anywhere` (or `word-break: break-word`) on the title/source containers, **and** `min-width: 0` on flex children in the header row. Truncation via `text-overflow: ellipsis` + `title="<full url>"` attribute is allowed ONLY for the jobs-table SOURCE VIDEO cell, never for the page headline (it must wrap, not get cut).
- Do NOT hide the defect with `overflow-x: hidden` on `body`/`html` as the primary fix — the content column itself must fit. A container-level `max-width: 100%` safety net is fine IN ADDITION to real wrapping.
- Fix the "Asr" formatter: stage display strings come from a single `STAGES` constant in JS (`["Ingest","ASR","Normalize","Select","Render","Package"]`) used verbatim everywhere; no `text-transform: capitalize` on stage names (remove the CSS rule if present).

## New acceptance artifact: `check-overflow.js` (Node ≥ 21, ZERO npm deps)

Write `check-overflow.js` using only Node built-ins (global `fetch` + global `WebSocket`, `child_process.spawn` of the local Chrome at `C:/Program Files/Google/Chrome/Application/chrome.exe` with `--headless=new --remote-debugging-port=9333`, or attach to `http://127.0.0.1:9333/json`). For each page `http://127.0.0.1:8765/` and `http://127.0.0.1:8765/job.html?id=demo-job`, for each width **360, 390, 768, 1440** (height 800):
- `Emulation.setDeviceMetricsOverride`, evaluate `document.documentElement.scrollWidth - document.documentElement.clientWidth` and `document.body.scrollWidth - document.body.clientWidth`.
- Print one line per (page,width): `page width overflow_doc overflow_body` and exit **0 only if all values ≤ 0** (page-level overflow is the defect; element-level rects inside `overflow-x:auto` containers are fine).
- Also assert `document.body.innerText` contains `ASR` and does NOT contain ` Asr` on the job page.
- Kill Chrome it spawned before exit (bounded, no orphan processes).

## Acceptance criteria (run ALL in the FOREGROUND, paste real output)

1. `node check-overflow.js` → all 8 (page × width) rows with overflow ≤ 0, `ASR` assertion passes, exit code 0.
2. `python verify.py` → still "ALL 8 ACCEPTANCE CRITERIA PASSED!", exit 0 (no regressions).
3. Fresh headless screenshots (`chrome.exe --headless=new --screenshot=... --window-size=360,740` and `1440,900`, both pages) saved as `.tmp/fix-home-360.png`, `.tmp/fix-home-1440.png`, `.tmp/fix-job-360.png`, `.tmp/fix-job-1440.png`, listed with sizes.

If Node's WebSocket cannot drive CDP on this machine, report `NOT RUN: <reason>` for criterion 1 and instead add a CSS-level unit check — but try the CDP route first.

## Constraints
- Same as TASK.md: stdlib/zero-dep for `server.py` and static assets (Node is allowed ONLY for `check-overflow.js`), all writes inside the project dir, no `/dev/null`, no subagents (do the edits yourself), no backgrounded servers, no deploy, planning short — fix first.

## Report format
```
REPORT
- Files changed: <list>
- Root cause per defect 1-5: <one line each, with the CSS/JS line changed>
- Acceptance 1-3: <pass/fail with key output lines>
- Deviations: <or none>
NOTES
- <caveats>
```
