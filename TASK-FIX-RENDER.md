# FIX-RENDER — 3 render polish items (one concern: output quality of clips/ + posters)

Follow-up to TASK-PIPELINE.md (same project root; `clipper.py` renders correctly — captions are burned and karaoke active-word colouring works). Independent visual frame review found 3 defects:

1. **Poster bug (functional):** `clips/NN_poster.jpg` is 1280×720 — it is extracted from `source.mp4`, NOT from the rendered clip. Fix: extract the poster from the final rendered `clips/NN_slug.mp4` at `start+1s` (i.e. 1 s into the clip) so it is 1080×1920 and shows the burned caption. Acceptance checks dimensions.
2. **Caption size too small for shorts (quality):** at PlayResY 1920 the current sizes (68/72) render ~40–60 px cap height ≈ 3% of frame height — real shorts captions are far bigger. Scale up all 8 templates' `ass.fontsize` in `static/caption-templates.json` by ~1.6× (karaoke-classic 68→108, bold-pop 72→115, keep each template's relative proportions; typewriter/ minimal-clean may stay relatively smaller but still ×1.4 minimum) and bump the outline accordingly (outline ×1.3, rounded). Keep `margin_v: 520`. Also apply the same scale in the CSS preview overlay on job.html so UI preview ≈ rendered size (visual parity, keep no-overflow: it must still pass `node check-overflow.js`).
3. **Caption cue chunking crosses sentence boundaries (quality):** a cue showed `pipelines. Rule number` — a chunk spanning a period. Fix the words_per_cue grouping in `clipper.py` to never cross sentence-ending punctuation (`.?!`) — end the cue at the sentence boundary even if fewer than `words_per_cue` words; start the next cue at the new sentence.

## Acceptance (FOREGROUND, paste real output)
1. Re-render: `python clipper.py run --fake demo2` is idempotent, so force a render re-run by deleting `work/demo2/clips/` and clearing the `render`+`package` stages in `work/demo2/manifest.json` (or add/use a `--from-stage render` flag — your choice, document it), then re-run → exit 0, 3 clips + 3 posters + 3 srt + ass regenerated.
2. `ffprobe` on every `work/demo2/clips/NN_poster.jpg` → `width==1080`, `height==1920` (python parse, print each).
3. Clip mp4s still 1080×1920, durations in [20,59], h264/aac (same check as TASK-PIPELINE criterion 2).
4. Sentence-safe chunking: `python` scan of `work/demo2/clips/*.ass` Dialogue texts → assert NO cue text contains `. `, `? `, `! ` in the middle of a cue (a cue may END with punctuation; print all cue texts as evidence). (If a template's typewriter effect is word-per-cue by design, exempt `typewriter` from words_per_cue grouping but still keep sentence-safe boundaries for the others.)
5. Re-render `demo2b --template bold-pop` the same way (delete clips, re-run) → its `.ass` Style line shows the new larger Fontsize; `python` diff vs `demo2` karaoke `.ass` still shows differences.
6. No regressions: `python verify.py` ALL 8 PASS; `node check-captions.js` ALL PASS (it asserts template distinctness — sizes changed but still distinct); `node check-overflow.js` 8 rows 0-overflow.
7. Frames for visual review: extract `.tmp/fix2-frame-karaoke.png` (frame at 5 s of demo2 clip 1) and `.tmp/fix2-frame-boldpop.png` (frame at 5 s of demo2b clip 1) with ffmpeg; also regenerate `.tmp/pipe-job-1440.png` (job.html?id=demo2 at 1440×2400). List with sizes.

## Constraints
Same as TASK-PIPELINE (zero pip deps, writes inside project dir, no /dev/null, no subagents, no deploy, foreground acceptance). Do not change clip durations, segments.json, or the API shapes. `static/caption-templates.json` `ass.fontsize` values change ONLY as specified (note old→new values in the report).

## Report format
```
REPORT
- Files changed: <list>
- fontsize old→new per template: <8 lines>
- Acceptance 1-7: <pass/fail with key output lines>
- Deviations: <or none>
NOTES
- <caveats>
```
