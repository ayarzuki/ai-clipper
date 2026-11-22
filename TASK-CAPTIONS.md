# FEATURE — Caption template system: 8 style presets + live preview + picker

Follow-up to TASK.md / TASK-FIX.md (same project root; `server.py`, `static/`, `work/demo-job/`, `check-overflow.js`, `verify.py` exist and pass). One concern only: **caption templates**. The pipeline later burns these captions into the video with ffmpeg/ASS, so every template must carry BOTH a browser-preview style and a machine-readable ASS spec.

## Design: 8 caption templates

Create `static/caption-templates.json` — array of 8 templates. Schema per template:

```json
{
  "id": "bold-pop",
  "name": "Bold Pop",
  "sample_text": "STOP building messy pipelines",
  "css_class": "tpl-bold-pop",
  "ass": {
    "fontname": "Arial", "fontsize": 72, "bold": true, "italic": false,
    "primary_colour": "&H00FFFFFF", "secondary_colour": "&H0000D7FF",
    "outline_colour": "&H00000000", "back_colour": "&H80000000",
    "outline": 4, "shadow": 1, "alignment": 2, "margin_v": 520,
    "effect": "pop", "uppercase": true, "words_per_cue": 2, "emoji": false
  }
}
```

The 8 (implement visual character exactly; `effect` ∈ `karaoke|pop|glow|fade|typewriter|ticker|bounce|clean`):

1. `bold-pop` **Bold Pop** — HUGE uppercase heavy sans, white with thick black outline, active word scales up 1.2× and turns yellow `#fbbf24`, 2 words/cue, punchy. Effect `pop`.
2. `karaoke-classic` **Karaoke Classic** — 2–4 words/cue, white text, active word fills emerald `#34d399` progressively (classic karaoke). Subtle dark outline. Effect `karaoke`. (This is the default / baseline look.)
3. `neon-glow` **Neon Glow** — uppercase, cyan `#22d3ee` text with layered glow (text-shadow bloom), active word switches to magenta `#f472b6` with pulse animation, 2 words/cue. Effect `glow`.
4. `minimal-clean` **Minimal Clean** — lowercase-friendly, small (≈48px), weight 500, white 90%, soft translucent pill background (`rgba(0,0,0,0.55)`, rounded), no outline, no emoji, whole short phrase per cue (4 words/cue). Effect `clean`.
5. `hype-emoji` **Hype Emoji** — bold uppercase with auto-emoji prefix on keyword (sample text starts with 🔥), yellow active word, emoji does a small bounce, 2 words/cue. `"emoji": true`. Effect `bounce`.
6. `typewriter` **Typewriter** — ONE word at a time, centered, monospace font, white with blinking `|` cursor after the word, no outline. `"words_per_cue": 1`. Effect `typewriter`.
7. `boxed-news` **Boxed News** — lower-third solid black bar (full-width-ish, ~85% width, sits above MarginV zone), amber `#fbbf24` uppercase text, 3 words/cue, active word white — news-ticker vibe. Effect `ticker`.
8. `gradient-influencer` **Gradient Influencer** — rounded white-outline pill, text with horizontal gradient (cyan→violet, `background-clip: text` in preview), active word slightly scales (1.1×), mixed-case allowed, 2 words/cue. Effect `pop`.

All templates: previews must keep text INSIDE the TikTok safe zone (bottom ~484px and right ~86px of the 1080×1920 frame are clear of UI overlays — captions live above that). `margin_v: 520` in every ASS spec.

## UI changes

1. **Clip card** (`static/job.html` + `static/job.js`): under the existing fields, a **Caption style** section:
   - Template picker: a row of 8 chips (template `name`) — horizontally scrollable on mobile; selected chip = cyan filled.
   - **Live preview**: the card's 9:16 preview area gains a caption overlay band rendering the template's `sample_text` with that template's CSS class + per-word animation cycling through the clip's `hook` text as real words (re-render words every ~400ms like burned captions would). Preview updates instantly when a different chip is selected.
   - Buttons row gains "Apply to all clips" (sets the same template on every clip) and "Preview caption" (replays the word cycle).
2. **Template gallery modal or section on `index.html`** (pick one; keep it simple): "Caption styles" — shows all 8 rendered on a shared sample line so the user compares looks side by side before opening a job. Clicking a template there sets it as the global default for new jobs.
3. **Persistence** (localStorage, same as other fields): per-clip `caption_template` + global default. On job load, clip cards initialize to the clip's saved template or the global default (fallback `karaoke-classic`).
4. Each template's `ass` block must be exposed in `GET /api/jobs/<id>` clip objects as `"caption_template": "<id>"` and the server must serve `GET /api/caption-templates` → the JSON array (read from `static/caption-templates.json`), so the future ffmpeg pipeline consumes exactly this file.

## CSS/animation requirements
- All 8 preview styles + keyframe animations live in `static/styles.css` (or a new `static/captions.css` linked from both pages). Pure CSS animation, no JS animation libs.
- Animations must respect `@media (prefers-reduced-motion: reduce)` (fall back to static highlight of the active word).
- The caption overlay band must not overflow the preview area at any card width (`max-width: 100%`, wrap, `overflow-wrap: anywhere` for long words).

## Acceptance criteria (run ALL in the FOREGROUND; paste real output)

1. `curl -s http://127.0.0.1:8765/api/caption-templates` → JSON array, `len == 8`, ids exactly `[bold-pop, karaoke-classic, neon-glow, minimal-clean, hype-emoji, typewriter, boxed-news, gradient-influencer]`, every object has `ass.effect` and `ass.margin_v == 520` (verify with `python -c` JSON parse; strict).
2. `curl -s http://127.0.0.1:8765/api/jobs/demo-job` → every clip object contains `"caption_template"` (value `karaoke-classic` or a saved id).
3. `node check-captions.js` (NEW, Node ≥21 built-in `fetch`/`WebSocket`/CDP — same pattern as `check-overflow.js`, zero npm deps): for the job page at 1440×900 it must assert, and exit 0 only if all hold:
   - exactly 8 picker chips rendered;
   - for EACH of the 8 chips: click it → the preview overlay element contains that template's `css_class` AND its computed `font-size` or `color` or `text-transform` differs from at least one other template (i.e. styles are genuinely distinct, not all the same);
   - sample text of the active template is visible in the preview overlay;
   - after clicking `boxed-news`, localStorage `clip.<id>.caption_template` equals `boxed-news` (or however persistence keys are shaped — assert the persisted value, and print the key shape);
   - "Apply to all clips" sets all 3 clip cards' persisted template to the same id (assert via localStorage).
4. `node check-overflow.js` → still 8 rows overflow ≤ 0 (the overlay must not break the no-overflow guarantee), exit 0.
5. `python verify.py` → still ALL 8 PASS, exit 0.
6. Fresh screenshots: `.tmp/caps-job-1440.png` (job page, one clip card showing `neon-glow` selected), `.tmp/caps-gallery-1440.png` (the 8-template gallery), `.tmp/caps-job-360.png`. List with sizes.

If CDP clicking cannot be automated, criterion 3 degrades to: DOM-source assertion (`curl` + `python` checks that all 8 css classes, chips and handler wiring exist) — report which route ran.

## Constraints
- Same as before: `server.py` + static assets zero external deps (Node only for check scripts), all writes inside project dir, no `/dev/null`, no subagents (do edits yourself), no backgrounded servers, no deploy, no changes to existing API response shapes except the additive `caption_template` field. Planning short — implement first.

## Report format
```
REPORT
- Files created/changed: <list>
- Template list: <id — name — effect> (8 lines)
- Acceptance 1-6: <pass/fail with key output lines>
- Deviations: <or none>
NOTES
- <caveats>
```
