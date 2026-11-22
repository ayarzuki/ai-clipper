# AI Clipper — System Design (cheapest stack: Groq Whisper + DeepSeek V4.1 Flash)

Goal: long video (file / YouTube URL) → N ready-to-post 9:16 shorts (Reels / TikTok / Shorts), ~$0.04 per hour of source video, runs entirely on the laptop, resumable.

## 1. Pipeline overview

```
input (URL/file)
  → [1 INGEST]     yt-dlp + ffmpeg        → source.mp4, audio.flac (16kHz mono)
  → [2 ASR]        Groq whisper-large-v3-turbo (verbose_json, word timestamps)
  → [3 NORMALIZE]  merge words → sentences → transcript.json [{start,end,text}]
  → [4 SELECT]     DeepSeek V4.1 Flash (JSON mode)  → segments.json [clips]
  → [5 RENDER]     ffmpeg (cut, crop 9:16, burn ASS captions, hook overlay)
  → [6 PACKAGE]    clips/*.mp4 + *.srt + metadata.json + poster.jpg
```

## 2. Job workspace (idempotency / resume)

```
work/<job_id>/
  manifest.json      # stage status: ingest|asr|normalize|select|render|package → done/failed
  source.mp4         # normalized container
  audio.flac         # 16kHz mono, 64kbps (small upload to Groq)
  transcript.json    # word-level + sentence-level with timestamps
  segments.json      # LLM clip selection output
  clips/NN_slug.mp4, clips/NN.srt, clips/NN_poster.jpg
  metadata.json      # final index: title/hook/caption/hashtags/score per clip
```

Each stage checks `manifest.json` before running → re-running a job skips completed stages. `--from-stage X` to force redo.

## 3. Stage contracts

### 1. Ingest
- URL → `yt-dlp -f "bv*+ba/b" --merge-output-format mp4`; local file → `ffmpeg -c copy` into `source.mp4` if codec is H.264, else transcode H.264 CRF 18.
- `ffprobe` → duration, resolution, fps, aspect. If source is already 9:16 → flag `vertical_source=true` (renderer skips crop).
- Extract audio: `ffmpeg -vn -ac 1 -ar 16000 audio.flac`.

### 2. ASR — Groq Whisper
- Model `whisper-large-v3-turbo`, `response_format=verbose_json`, `timestamp_granularities=["word","segment"]`.
- **Chunking:** Groq request body limit ~25 MB. flac 64kbps ≈ 0.5 MB/min → chunk at 10 min with 3 s overlap, cut on silence when possible (`ffmpeg -af silencedetect`). Add chunk offset to all returned timestamps; drop words inside the overlap window to dedupe.
- Retry: 3× exponential backoff on 429/5xx (Groq free tier rate-limits — pace chunk uploads).

### 3. Normalize
- Group words into sentences (punctuation from Whisper segments, max ~15 words per line) → `[{start, end, text}]`.
- Keep word timings separately for karaoke-style captions.

### 4. Clip selection — DeepSeek V4.1 Flash (`deepseek-flash`, JSON output, temp 0.3)
Prompt contract (system):
> You are a short-form video editor. Given a timestamped transcript, select the best self-contained moments for vertical shorts. Return strict JSON: `{"clips":[{"start":"HH:MM:SS.mmm","end":"HH:MM:SS.mmm","title":str,"hook":str (≤7 words, shown first 3s),"caption":str (post caption),"hashtags":[str],"virality_score":int 0-100,"reason":str}]}`. Rules: duration 20–59 s (hard max 180 s); cut on sentence boundaries only, add 0.2 s padding; each clip must work without context (setup → payoff); no overlaps; return 6–12 clips ordered by virality_score.

- Input format: `[HH:MM:SS.mmm] sentence` lines.
- **Long videos:** transcript > ~4 hours (≈60k tokens) → map-reduce: per-hour candidate pass (8 candidates each) then one reduce call to rank/dedupe to final 6–12. Under that, single call (DeepSeek context is 1M — one call easily fits 8+ hours).
- Validation after response: clamp timestamps to video bounds, snap to nearest sentence boundary, drop clips < 15 s or overlapping > 30%.

### 5. Render — ffmpeg (parallel, `min(cores//2, 4)` workers)
Per clip:
```
ffmpeg -ss <start> -to <end> -i source.mp4
  -vf "crop='min(iw,ih*9/16)':ih:(iw-min(iw,ih*9/16))/2:0,scale=1080:1920,fps=30,ass=NN.ass"
  -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 128k clips/NN_slug.mp4
```
- **Captions:** build `.ass` from word timings — 2–4 words per cue, active word highlighted (karaoke `{\k}`), font size ~72 at PlayResY 1920, `MarginV≈520` (TikTok safe zone: bottom 484 px + right 86 px kept clear).
- **Hook overlay:** `drawtext` of `hook` (first 3 s, top third).
- Vertical source → skip crop, just `scale=1080:1920`.
- v1 keeps punch-in/zoom out of scope (static crop); add `zoompan` step later.

### 6. Package
- `NN_slug.mp4`, matching `.srt`, poster (`-ss <start+1> -frames:v 1`), `metadata.json` with everything needed to post (title, hook, caption incl. hashtags, score, duration).

## 4. CLI & config

```
python clipper.py run <url|file> [--lang id|en] [--target-len 45] [--max-clips 10] [--from-stage asr]
python clipper.py resume <job_id>
```
- Env: `GROQ_API_KEY`, `DEEPSEEK_API_KEY` (never committed; read from env or `.env`).
- `config.yaml`: duration policy per platform (universal default: 20–59 s, hard max 180 s — passes Reels/TikTok/Shorts), brand fonts/colors, hashtag style.

## 5. Cost model (per 1 h of source)

| Stage | Model | Cost |
|---|---|---|
| ASR | Groq whisper-large-v3-turbo (~$0.0006/min) | $0.036 |
| Selection | DeepSeek V4.1 Flash, ≈12k in / 2k out tokens ($0.15–0.30 / $0.60–1.20 per 1M) | ~$0.003–0.006 |
| Render/package | ffmpeg local | $0 |
| **Total** | | **≈ $0.04** |

30 × 1-hour videos/month ≈ **$1.2/month**. Batch mode (50% off) and prompt caching (80–98% off input) shrink the LLM share further.

## 6. Pitfalls & guards
- Groq rate limits on free tier → pace + backoff; chunk uploads sequentially with jitter.
- Timestamp drift after chunking → always add chunk offset; dedupe 3 s overlap.
- LLM returning out-of-range or mid-sentence cuts → post-validate + snap (stage 4 contract above).
- TikTok mobile upload caps at 287.6 MB → clips are tiny, but if ever uploading source, use web/TikTok Studio (4 GB).
- Shorts > 1 min with Content ID claim get blocked → prefer ≤ 59 s default.
- Sora 2 Videos API shuts down 24 Sep 2026 → not used anywhere in this design (only noted for B-roll options).

## 7. Future phases (not in v1)
- Auto-post: TikTok Content Posting API + YouTube resumable upload (vertical ≤ 3 min auto-classifies as Shorts) + IG Graph Reels API (business account).
- Speaker-tracking reframe (face tracking instead of center crop) — e.g. `auto-editor` / OpenCV tracker.
- Optional AI B-roll via Veo 3.1 Lite ($0.03/s) per cut point.
- CF Pages dashboard reading `metadata.json` exports.
