# FIX-REALMODE — surface provider errors instead of swallowing them (one concern: real-mode error handling)

Project root as usual. Real-mode test on a tiny video found: with an INVALID `GROQ_API_KEY`, the ASR stage logs "Uploading audio.flac to Groq Whisper..." and then **returns without writing `transcript.json` and without raising** — the provider's 401 is swallowed (a `try/except` somewhere in the Groq call returns empty/partial on HTTP errors). The job then crashes misleadingly in `_run_normalize` with `FileNotFoundError: transcript.json`, and `manifest.error` shows THAT instead of the root cause.

## Required fix (clipper.py only)

1. **Never swallow provider errors.** In the real-mode ASR (Groq) and Select (DeepSeek) calls: on any non-2xx response, raise `RuntimeError(f"Groq Whisper HTTP {code}: {body_snippet}")` / `RuntimeError(f"DeepSeek HTTP {code}: {body_snippet}")` (body snippet ≤ 300 chars). Same for JSON decode failures (`...returned invalid JSON: {snippet}`). No bare `except:` that continues the pipeline.
2. **Empty-output guard:** if ASR returns zero words/segments (or the response lacks `segments`), raise `RuntimeError("ASR returned no transcript ...")` naming the provider and response snippet — do not continue to normalize.
3. **Root-cause surfacing:** when a stage raises, `manifest.error` must contain that original message (it already captures e.g. `RuntimeError` text — verify with the test below that the 401 message lands, not the downstream FileNotFoundError).
4. Real-mode ASR must send the request even with a placeholder key (it does today — the key `is set` check passing is enough) so the provider's own auth error surfaces.

## Acceptance (FOREGROUND; server started via `cmd /c start.bat` with the existing `.env` placeholder keys, then killed)
1. Create a 5 s test video (ffmpeg lavfi testsrc2+sine, `.tmp/realtest2.mp4`), then `POST /api/jobs {"url_or_path":".tmp/realtest2.mp4","mode":"real",...}` and poll until `failed`. Assert `manifest.error` contains `Groq` AND (`401` or `403` or `invalid_api_key` or `Unauthorized` — whatever the provider returns for a bad key) AND does NOT contain `FileNotFoundError`. Paste the error line.
2. Same via CLI: `python clipper.py run .tmp/realtest2.mp4` exits non-zero with a message naming Groq + HTTP status (paste it).
3. Empty-transcript guard unit-style: call the ASR result-handling path with a synthetic `{"segments": []}` response (or temporarily point at a stub) — assert it raises the "no transcript" RuntimeError. (A tiny inline python test is fine.)
4. Regressions: `python verify.py` ALL 8 PASS; `node check-wiring.js` ALL PASS (its fake-mode paths must be unaffected — fake ASR still writes transcripts); `node check-captions.js` and `node check-overflow.js` unchanged PASS.

## Constraints
Same standard set (no pip deps, no subagents, writes inside project dir, no /dev/null, no deploy). Touch ONLY the real-mode ASR/Select error paths in `clipper.py` (+ nothing in fake mode) and `server.py` only if manifest.error propagation needs it.

## Report format
```
REPORT
- Files changed / exact guards added: <list>
- Acceptance 1-4: <pass/fail with key output lines incl. the surfaced provider error>
- Deviations: <or none>
NOTES
- <caveats>
```
