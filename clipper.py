#!/usr/bin/env python3
"""
AI Clipper — Clipping pipeline backend (Python stdlib + ffmpeg/ffprobe)
Supports deterministic offline FAKE mode (--fake or CLIPPER_FAKE=1) and real mode.
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import subprocess
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_FILE = STATIC_DIR / "caption-templates.json"

STAGES = ["ingest", "asr", "normalize", "select", "render", "package"]

def load_dotenv():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_dotenv()

def parse_timestamp(ts) -> float:
    """Parses HH:MM:SS.mmm or MM:SS.mmm or seconds float into float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    ts = str(ts).strip().replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    except Exception:
        return 0.0

def encode_multipart_formdata(fields: list, files: list) -> tuple[bytes, str]:
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    lines = []
    for name, value in fields:
        lines.append(f"--{boundary}\r\n".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        lines.append(f"{value}\r\n".encode("utf-8"))
    for name, filename, content, content_type in files:
        lines.append(f"--{boundary}\r\n".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        lines.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        lines.append(content)
        lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"

def process_asr_response(data: dict) -> list:
    """
    Processes Groq Whisper verbose_json response and validates non-empty segments/words.
    Raises RuntimeError if transcript is missing, invalid, or empty.
    """
    if not isinstance(data, dict):
        snippet = str(data)[:300]
        raise RuntimeError(f"ASR returned invalid response structure from Groq: {snippet}")

    segments = data.get("segments")
    if segments is None or not isinstance(segments, list) or len(segments) == 0:
        snippet = json.dumps(data)[:300]
        raise RuntimeError(f"ASR returned no transcript from Groq: {snippet}")

    result = []
    has_words_or_text = False
    for seg in segments:
        text = seg.get("text", "").strip()
        words = seg.get("words", [])
        if text or words:
            has_words_or_text = True
        result.append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": text,
            "words": words
        })

    if not has_words_or_text:
        snippet = json.dumps(data)[:300]
        raise RuntimeError(f"ASR returned no transcript from Groq: {snippet}")

    return result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s[:40] if s else "clip"

def format_timestamp_srt(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    sec = total_sec % 60
    total_min = total_sec // 60
    minute = total_min % 60
    hour = total_min // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"

def format_timestamp_ass(seconds: float) -> str:
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_sec = total_cs // 100
    sec = total_sec % 60
    total_min = total_sec // 60
    minute = total_min % 60
    hour = total_min // 60
    return f"{hour}:{minute:02d}:{sec:02d}.{cs:02d}"

def load_template_config(template_id: str) -> dict:
    fallback = {
        "id": "karaoke-classic",
        "name": "Karaoke Classic",
        "css_class": "tpl-karaoke-classic",
        "ass": {
            "fontname": "Arial", "fontsize": 108, "bold": True, "italic": False,
            "primary_colour": "&H00FFFFFF", "secondary_colour": "&H0099D334",
            "outline_colour": "&H00000000", "back_colour": "&H80000000",
            "outline": 4, "shadow": 1, "alignment": 2, "margin_v": 520,
            "effect": "karaoke", "uppercase": False, "words_per_cue": 3, "emoji": False
        }
    }
    if not TEMPLATES_FILE.exists():
        return fallback
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            templates = json.load(f)
        for t in templates:
            if t.get("id") == template_id:
                return t
    except Exception:
        pass
    return fallback

# ---------------------------------------------------------------------------
# Pipeline Implementation
# ---------------------------------------------------------------------------

class ClipperPipeline:
    def __init__(self, job_id: str, input_src: str, fake: bool = False,
                 template_id: str = "karaoke-classic", lang: str = "en",
                 target_len: int = 45, max_clips: int = 10, from_stage: str = None):
        self.job_id = job_id
        self.input_src = input_src
        self.fake = fake or (os.environ.get("CLIPPER_FAKE") == "1")
        self.template_id = template_id
        self.lang = lang
        self.target_len = target_len
        self.max_clips = max_clips
        self.from_stage = from_stage

        self.job_dir = WORK_DIR / self.job_id
        self.clips_dir = self.job_dir / "clips"
        self.manifest_file = self.job_dir / "manifest.json"
        self.metadata_file = self.job_dir / "metadata.json"
        self.source_file = self.job_dir / "source.mp4"
        self.audio_file = self.job_dir / "audio.flac"
        self.transcript_file = self.job_dir / "transcript.json"
        self.segments_file = self.job_dir / "segments.json"

        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "job_id": self.job_id,
            "source": self.input_src,
            "status": "running",
            "clip_count": 0,
            "created": datetime.now(timezone.utc).isoformat(),
            "target_len_s": self.target_len,
            "duration_s": 0,
            "stages": {s: "pending" for s in STAGES}
        }

    def _save_manifest(self):
        self.job_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    def _should_skip(self, stage: str) -> bool:
        stages = self.manifest.get("stages", {})
        if self.from_stage:
            # Force redo from this stage onwards
            from_idx = STAGES.index(self.from_stage) if self.from_stage in STAGES else 0
            cur_idx = STAGES.index(stage)
            if cur_idx >= from_idx:
                return False
        return stages.get(stage) == "done"

    def run(self):
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

        for stage in STAGES:
            if self._should_skip(stage):
                print(f"skip {stage} (already done)")
                continue

            self.manifest["status"] = "running"
            self.manifest["stages"][stage] = "running"
            self.manifest.pop("error", None)
            self._save_manifest()
            print(f"--> Stage: {stage}")
            try:
                if stage == "ingest":
                    self._run_ingest()
                elif stage == "asr":
                    self._run_asr()
                elif stage == "normalize":
                    self._run_normalize()
                elif stage == "select":
                    self._run_select()
                elif stage == "render":
                    self._run_render()
                elif stage == "package":
                    self._run_package()

                self.manifest["stages"][stage] = "done"
                self._save_manifest()
            except Exception as e:
                self.manifest["stages"][stage] = "failed"
                self.manifest["status"] = "failed"
                self.manifest["error"] = str(e)
                self._save_manifest()
                raise e

        self.manifest["status"] = "done"
        self._save_manifest()
        print(f"Job '{self.job_id}' completed successfully.")

    # -----------------------------------------------------------------------
    # 1. Ingest
    # -----------------------------------------------------------------------
    def _run_ingest(self):
        if self.fake:
            # Synthesize testsrc2 + sine audio, 1280x720, 30fps, 150s
            print("  [fake] Synthesizing 150s 720p source with ffmpeg...")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000",
                "-t", "150",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                str(self.source_file)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.manifest["duration_s"] = 150
        else:
            # Real ingest
            is_url = self.input_src.startswith("http://") or self.input_src.startswith("https://")
            if is_url:
                if not shutil.which("yt-dlp"):
                    raise RuntimeError("yt-dlp is not installed on PATH. Please install yt-dlp to download YouTube URLs.")
                print("  [real] Downloading source via yt-dlp...")
                cmd = [
                    "yt-dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                    "-o", str(self.source_file), self.input_src
                ]
                subprocess.run(cmd, check=True)
            else:
                src_path = Path(self.input_src)
                if not src_path.exists():
                    raise FileNotFoundError(f"Input file not found: {self.input_src}")
                print("  [real] Copying/transcoding source to source.mp4...")
                cmd = [
                    "ffmpeg", "-y", "-i", str(src_path),
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-c:a", "aac", "-b:a", "128k", str(self.source_file)
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Extract audio.flac: 16 kHz mono
        print("  Extracting audio.flac (16kHz mono)...")
        cmd_audio = [
            "ffmpeg", "-y", "-i", str(self.source_file),
            "-vn", "-ac", "1", "-ar", "16000", str(self.audio_file)
        ]
        subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -----------------------------------------------------------------------
    # 2. ASR
    # -----------------------------------------------------------------------
    def _run_asr(self):
        if self.fake:
            print("  [fake] Generating word-level transcript for 150s...")
            raw_script = [
                (0.0, 4.5, "Welcome back. Today we're diving into the fundamental rules of great data pipelines."),
                (4.5, 10.0, "Rule number one is dead simple: never mutate your raw incoming stream."),
                (10.0, 18.0, "Rule number two: every single transformation DAG must be completely idempotent."),
                (18.0, 27.0, "If a pipeline worker fails halfway through, re-running it should yield the exact same state without duplicate records."),
                (27.0, 35.0, "Follow these three rules and your pipelines will survive any massive scale spike."),
                (35.0, 40.0, "Now let's switch gears and examine what happens when things break down in production."),
                (40.0, 52.0, "It is 3 AM, PagerDuty goes off, and your ETL pipeline just choked on malformed payload data."),
                (52.0, 64.0, "Most junior engineers make the mistake of hardcoding blind retry backoff without dead letter queues."),
                (64.0, 73.0, "When an unparsed JSON payload hits the sink, the whole consumer group stalls and lag explodes into millions."),
                (73.0, 81.0, "Route poisonous records to a dead letter topic immediately to keep moving, and alert the data steward asynchronously."),
                (81.0, 85.0, "Let's touch on one final quick optimization for schema validation."),
                (85.0, 98.0, "Stop running expensive full table scans just to catch unexpected schema drift across billions of rows."),
                (98.0, 112.0, "Use an Avro schema registry with forward compatibility checks at producer time and fail fast before ingestion."),
                (112.0, 126.0, "Enforcing schemas at write time eliminates seventy percent of downstream pipeline outages entirely."),
                (126.0, 140.0, "That wraps up our architecture deep dive for today. Follow for more reliable data engineering insights."),
                (140.0, 150.0, "Check out the links in the description for sample repository code and architecture blueprints.")
            ]
            segments = []
            for s_start, s_end, text in raw_script:
                words = text.split()
                dt = (s_end - s_start) / len(words)
                word_objs = [
                    {
                        "word": w,
                        "start": round(s_start + i * dt, 2),
                        "end": round(s_start + (i + 1) * dt, 2)
                    }
                    for i, w in enumerate(words)
                ]
                segments.append({
                    "start": s_start,
                    "end": s_end,
                    "text": text,
                    "words": word_objs
                })
            with open(self.transcript_file, "w", encoding="utf-8") as f:
                json.dump(segments, f, indent=2)
        else:
            # Real ASR with Groq Whisper
            groq_key = os.environ.get("GROQ_API_KEY")
            if not groq_key:
                raise RuntimeError("GROQ_API_KEY environment variable is not set. Real ASR requires a Groq API key.")
            print("  [real] Uploading audio.flac to Groq Whisper...")
            if not self.audio_file.exists():
                raise FileNotFoundError(f"Audio file not found for ASR: {self.audio_file}")

            with open(self.audio_file, "rb") as f:
                audio_bytes = f.read()

            fields = [
                ("model", "whisper-large-v3-turbo"),
                ("response_format", "verbose_json"),
                ("timestamp_granularities[]", "word"),
                ("timestamp_granularities[]", "segment"),
                ("language", self.lang)
            ]
            files = [
                ("file", "audio.flac", audio_bytes, "audio/flac")
            ]
            body, content_type = encode_multipart_formdata(fields, files)

            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                data=body,
                method="POST"
            )
            req.add_header("Authorization", f"Bearer {groq_key}")
            req.add_header("Content-Type", content_type)

            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_bytes = resp.read()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                snippet = err_body[:300]
                raise RuntimeError(f"Groq Whisper HTTP {e.code}: {snippet}")
            except urllib.error.URLError as e:
                snippet = str(e.reason)[:300]
                raise RuntimeError(f"Groq Whisper network error: {snippet}")

            try:
                json_resp = json.loads(resp_bytes.decode("utf-8"))
            except Exception:
                snippet = resp_bytes.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"Groq Whisper returned invalid JSON: {snippet}")

            segments = process_asr_response(json_resp)
            with open(self.transcript_file, "w", encoding="utf-8") as f:
                json.dump(segments, f, indent=2)

    # -----------------------------------------------------------------------
    # 3. Normalize
    # -----------------------------------------------------------------------
    def _run_normalize(self):
        print("  Normalizing word stream into sentence-level transcripts...")
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            raw_segments = json.load(f)

        # Consumes word stream and ensures valid [{start, end, text, words}] structure
        normalized = []
        for seg in raw_segments:
            words = seg.get("words", [])
            text = seg.get("text", "").strip()
            if not text and words:
                text = " ".join(w["word"] for w in words)
            s_start = seg.get("start", words[0]["start"] if words else 0.0)
            s_end = seg.get("end", words[-1]["end"] if words else s_start + 1.0)
            normalized.append({
                "start": round(float(s_start), 2),
                "end": round(float(s_end), 2),
                "text": text,
                "words": words
            })

        with open(self.transcript_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

    # -----------------------------------------------------------------------
    # 4. Select
    # -----------------------------------------------------------------------
    def _run_select(self):
        if self.fake:
            print("  [fake] Generating 3 candidate clips (35s, 41s, 55s)...")
            clips = [
                {
                    "id": 1,
                    "start": "00:00:00.000",
                    "end": "00:00:35.000",
                    "start_s": 0.0,
                    "end_s": 35.0,
                    "duration": 35,
                    "duration_s": 35,
                    "title": "The 3 rules of great data pipelines",
                    "hook": "Stop building messy data pipelines today",
                    "caption": "Mastering modern data engineering comes down to 3 core principles. Are you following all 3? #dataengineering #bigdata",
                    "hashtags": ["#dataengineering", "#bigdata", "#python", "#coding"],
                    "virality_score": 88,
                    "score": 88,
                    "reason": "Clear listicle setup with actionable payoffs and strong hook."
                },
                {
                    "id": 2,
                    "start": "00:00:40.000",
                    "end": "00:01:21.000",
                    "start_s": 40.0,
                    "end_s": 81.0,
                    "duration": 41,
                    "duration_s": 41,
                    "title": "Why your ETL jobs fail at 3 AM",
                    "hook": "Every data engineer makes this fatal mistake",
                    "caption": "Why does PagerDuty always ring at 3 AM? Dead letter queues will save your sleep schedule. #dataengineering #cloud",
                    "hashtags": ["#dataengineering", "#cloud", "#softwaredeveloper", "#devops"],
                    "virality_score": 72,
                    "score": 72,
                    "reason": "Relatable developer pain point with concrete architectural solution."
                },
                {
                    "id": 3,
                    "start": "00:01:25.000",
                    "end": "00:02:20.000",
                    "start_s": 85.0,
                    "end_s": 140.0,
                    "duration": 55,
                    "duration_s": 55,
                    "title": "Never run full table scans for schema drift",
                    "hook": "Fix schema drift with one simple check",
                    "caption": "Stop running expensive full table scans just to catch schema drift. Enforce compatibility at the producer! #dataengineering",
                    "hashtags": ["#dataengineering", "#tech", "#sql", "#programming"],
                    "virality_score": 45,
                    "score": 45,
                    "reason": "High-signal performance optimization eliminating production outages."
                }
            ]
            with open(self.segments_file, "w", encoding="utf-8") as f:
                json.dump(clips, f, indent=2)
        else:
            # Real selection via DeepSeek V4.1 Flash
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
            if not deepseek_key:
                raise RuntimeError("DEEPSEEK_API_KEY environment variable is not set. Real selection requires a DeepSeek API key.")
            print("  [real] Calling DeepSeek V4.1 Flash JSON mode...")

            if not self.transcript_file.exists():
                raise FileNotFoundError(f"Transcript file not found for selection: {self.transcript_file}")

            with open(self.transcript_file, "r", encoding="utf-8") as f:
                raw_segments = json.load(f)

            formatted_lines = []
            for s in raw_segments:
                t_str = format_timestamp_ass(s.get("start", 0.0))
                text = s.get("text", "").strip()
                if text:
                    formatted_lines.append(f"[{t_str}] {text}")
            transcript_text = "\n".join(formatted_lines)

            system_prompt = (
                "You are a short-form video editor. Given a timestamped transcript, select the best "
                "self-contained moments for vertical shorts. Return strict JSON: "
                "{\"clips\":[{\"start\":\"HH:MM:SS.mmm\",\"end\":\"HH:MM:SS.mmm\",\"title\":str,\"hook\":str (≤7 words, shown first 3s),\"caption\":str (post caption),\"hashtags\":[str],\"virality_score\":int 0-100,\"reason\":str}]}. "
                "Rules: duration 20–59 s (hard max 180 s); cut on sentence boundaries only, add 0.2 s padding; "
                "each clip must work without context (setup → payoff); no overlaps; return 6–12 clips ordered by virality_score."
            )

            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript_text}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3
            }
            body = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=body,
                method="POST"
            )
            req.add_header("Authorization", f"Bearer {deepseek_key}")
            req.add_header("Content-Type", "application/json")

            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    resp_bytes = resp.read()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                snippet = err_body[:300]
                raise RuntimeError(f"DeepSeek HTTP {e.code}: {snippet}")
            except urllib.error.URLError as e:
                snippet = str(e.reason)[:300]
                raise RuntimeError(f"DeepSeek network error: {snippet}")

            try:
                json_resp = json.loads(resp_bytes.decode("utf-8"))
            except Exception:
                snippet = resp_bytes.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"DeepSeek returned invalid JSON: {snippet}")

            choices = json_resp.get("choices", [])
            if not choices:
                snippet = json.dumps(json_resp)[:300]
                raise RuntimeError(f"DeepSeek returned no choices: {snippet}")

            content_str = choices[0].get("message", {}).get("content", "")
            try:
                parsed_content = json.loads(content_str)
            except Exception:
                snippet = content_str[:300]
                raise RuntimeError(f"DeepSeek returned invalid JSON: {snippet}")

            clips = parsed_content.get("clips", [])
            if not clips or not isinstance(clips, list):
                snippet = content_str[:300]
                raise RuntimeError(f"DeepSeek returned no clips: {snippet}")

            normalized_clips = []
            for idx, c in enumerate(clips[:self.max_clips], 1):
                start_s = parse_timestamp(c.get("start", "00:00:00.000"))
                end_s = parse_timestamp(c.get("end", "00:00:30.000"))
                dur = max(1.0, end_s - start_s)
                normalized_clips.append({
                    "id": idx,
                    "start": c.get("start", format_timestamp_ass(start_s)),
                    "end": c.get("end", format_timestamp_ass(end_s)),
                    "start_s": round(start_s, 2),
                    "end_s": round(end_s, 2),
                    "duration": int(round(dur)),
                    "duration_s": round(dur, 2),
                    "title": c.get("title", f"Clip {idx}"),
                    "hook": c.get("hook", ""),
                    "caption": c.get("caption", ""),
                    "hashtags": c.get("hashtags", []),
                    "virality_score": int(c.get("virality_score", 50)),
                    "score": int(c.get("virality_score", 50)),
                    "reason": c.get("reason", "")
                })

            with open(self.segments_file, "w", encoding="utf-8") as f:
                json.dump(normalized_clips, f, indent=2)

    # -----------------------------------------------------------------------
    # 5. Render
    # -----------------------------------------------------------------------
    def _build_ass(self, clip: dict, transcript: list, template: dict) -> str:
        tpl_ass = template.get("ass", {})
        fontname = tpl_ass.get("fontname", "Arial")
        fontsize = tpl_ass.get("fontsize", 70)
        bold = -1 if tpl_ass.get("bold") else 0
        italic = -1 if tpl_ass.get("italic") else 0
        primary = tpl_ass.get("primary_colour", "&H00FFFFFF")
        secondary = tpl_ass.get("secondary_colour", "&H0000D7FF")
        outline_colour = tpl_ass.get("outline_colour", "&H00000000")
        back_colour = tpl_ass.get("back_colour", "&H80000000")
        outline = tpl_ass.get("outline", 3)
        shadow = tpl_ass.get("shadow", 1)
        alignment = tpl_ass.get("alignment", 2)
        margin_v = tpl_ass.get("margin_v", 520)
        effect = tpl_ass.get("effect", "karaoke")
        uppercase = tpl_ass.get("uppercase", False)
        words_per_cue = tpl_ass.get("words_per_cue", 2)
        has_emoji = tpl_ass.get("emoji", False)

        c_start = float(clip["start_s"])
        c_end = float(clip["end_s"])
        clip_dur = c_end - c_start

        # Extract overlapping words
        matching_words = []
        for seg in transcript:
            for w in seg.get("words", []):
                w_s = float(w["start"])
                w_e = float(w["end"])
                if w_e > c_start and w_s < c_end:
                    rel_s = max(0.0, w_s - c_start)
                    rel_e = min(clip_dur, w_e - c_start)
                    matching_words.append({
                        "word": w["word"],
                        "rel_start": rel_s,
                        "rel_end": rel_e
                    })

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},{primary},{secondary},{outline_colour},{back_colour},{bold},{italic},0,0,100,100,0,0,1,{outline},{shadow},{alignment},40,40,{margin_v},1
Style: Hook,Arial,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,8,60,60,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        # 1. Hook overlay line (first 3s)
        hook_text = clip.get("hook", "").strip()
        if uppercase:
            hook_text = hook_text.upper()
        if hook_text:
            events.append(f"Dialogue: 1,0:00:00.00,0:00:03.00,Hook,,0,0,0,,{{\\fade(200,300)}}{hook_text}")

        # 2. Captions from word stream
        # Sentence-safe cue chunking: never cross sentence-ending punctuation (.?!)
        cues = []
        current_cue = []
        for w in matching_words:
            current_cue.append(w)
            w_text = w["word"].strip()
            # If word ends with sentence-ending punctuation or reached max words_per_cue
            is_sentence_end = bool(re.search(r'[.?!]["\']?$', w_text))
            if is_sentence_end or len(current_cue) >= words_per_cue:
                cues.append(current_cue)
                current_cue = []
        if current_cue:
            cues.append(current_cue)

        for cue_idx, chunk in enumerate(cues):
            if not chunk:
                continue
            cue_start = chunk[0]["rel_start"]
            cue_end = chunk[-1]["rel_end"]
            if cue_end <= cue_start:
                cue_end = cue_start + 1.0

            start_ass = format_timestamp_ass(cue_start)
            end_ass = format_timestamp_ass(cue_end)

            if effect in ["karaoke", "pop", "bounce", "glow"]:
                # Karaoke sweep tags
                parts = []
                for w in chunk:
                    dur_cs = max(10, int((w["rel_end"] - w["rel_start"]) * 100))
                    text_word = w["word"]
                    if uppercase:
                        text_word = text_word.upper()
                    parts.append(f"{{\\k{dur_cs}}}{text_word}")
                cue_text = " ".join(parts)
                if has_emoji and cue_idx == 0:
                    cue_text = f"🔥 {cue_text}"
            elif effect == "clean":
                text_words = [w["word"].upper() if uppercase else w["word"] for w in chunk]
                cue_text = f"{{\\fad(150,150)}}{' '.join(text_words)}"
            elif effect == "typewriter":
                w = chunk[0]
                text_word = w["word"].upper() if uppercase else w["word"]
                cue_text = f"{text_word}|"
            elif effect == "ticker":
                text_words = [w["word"].upper() for w in chunk]
                cue_text = f"{{\\an2\\bord2}}{' '.join(text_words)}"
            else:
                text_words = [w["word"] for w in chunk]
                cue_text = " ".join(text_words)

            events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{cue_text}")

        return header + "\n".join(events) + "\n"

    def _run_render(self):
        print(f"  Rendering clips using template '{self.template_id}'...")
        with open(self.segments_file, "r", encoding="utf-8") as f:
            clips = json.load(f)
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            transcript = json.load(f)

        template = load_template_config(self.template_id)

        for clip in clips:
            c_id = clip["id"]
            slug = slugify(clip["title"])
            c_start = float(clip["start_s"])
            c_end = float(clip["end_s"])

            # 1. Build .ass file
            ass_path = self.clips_dir / f"{c_id:02d}.ass"
            ass_content = self._build_ass(clip, transcript, template)
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

            # 2. Render 9:16 clip video
            out_mp4 = self.clips_dir / f"{c_id:02d}_{slug}.mp4"
            print(f"    Rendering clip {c_id}: {out_mp4.name}...")
            # Forward slashes for ffmpeg filter
            ass_rel = f"clips/{c_id:02d}.ass"
            cmd_render = [
                "ffmpeg", "-y",
                "-ss", str(c_start), "-to", str(c_end),
                "-i", str(self.source_file.resolve()),
                "-vf", f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,fps=30,ass={ass_rel}",
                "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                str(out_mp4.resolve())
            ]
            # Run in job_dir so ass=clips/NN.ass works cleanly
            subprocess.run(cmd_render, cwd=str(self.job_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 3. Render poster frame (1.0s into rendered 9:16 clip)
            poster_path = self.clips_dir / f"{c_id:02d}_poster.jpg"
            cmd_poster = [
                "ffmpeg", "-y",
                "-ss", "1.0",
                "-i", str(out_mp4.resolve()),
                "-frames:v", "1", "-q:v", "2",
                str(poster_path.resolve())
            ]
            subprocess.run(cmd_poster, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 4. Generate standalone SRT
            srt_path = self.clips_dir / f"{c_id:02d}.srt"
            srt_lines = []
            matching_idx = 1
            for seg in transcript:
                s = float(seg["start"])
                e = float(seg["end"])
                if e > c_start and s < c_end:
                    rel_s = max(0.0, s - c_start)
                    rel_e = min(c_end - c_start, e - c_start)
                    srt_lines.append(f"{matching_idx}\n{format_timestamp_srt(rel_s)} --> {format_timestamp_srt(rel_e)}\n{seg['text']}\n")
                    matching_idx += 1
            if not srt_lines:
                srt_lines.append(f"1\n00:00:00,000 --> {format_timestamp_srt(c_end - c_start)}\n[No dialogue]\n")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines).strip() + "\n")

    # -----------------------------------------------------------------------
    # 6. Package
    # -----------------------------------------------------------------------
    def _run_package(self):
        print("  Packaging metadata.json and updating manifest.json...")
        with open(self.segments_file, "r", encoding="utf-8") as f:
            clips = json.load(f)

        final_clips = []
        for clip in clips:
            c_id = clip["id"]
            slug = slugify(clip["title"])
            filename = f"clips/{c_id:02d}_{slug}.mp4"
            dur = int(round(float(clip["end_s"]) - float(clip["start_s"])))
            final_clips.append({
                "id": c_id,
                "start": float(clip["start_s"]),
                "end": float(clip["end_s"]),
                "duration": dur,
                "duration_s": dur,
                "virality_score": clip.get("virality_score", 50),
                "score": clip.get("virality_score", 50),
                "caption_template": self.template_id,
                "title": clip["title"],
                "hook": clip["hook"],
                "caption": clip["caption"],
                "hashtags": clip.get("hashtags", []),
                "filename": filename,
                "srt": f"/api/jobs/{self.job_id}/srt/{c_id}"
            })

        metadata = {
            "job_id": self.job_id,
            "source": self.input_src,
            "duration_s": self.manifest.get("duration_s", 150),
            "clips": final_clips
        }

        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        self.manifest["clip_count"] = len(final_clips)
        self.manifest["status"] = "done"
        self._save_manifest()


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AI Clipper pipeline backend")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run clipping pipeline on URL, file, or fake job")
    run_parser.add_argument("input", nargs="?", default="demo-job", help="YouTube URL, file path, or job ID for fake")
    run_parser.add_argument("--fake", action="store_true", help="Run deterministic offline fake pipeline")
    run_parser.add_argument("--template", default="karaoke-classic", help="Caption template preset ID")
    run_parser.add_argument("--lang", default="en", choices=["en", "id"], help="Language code")
    run_parser.add_argument("--target-len", type=int, default=45, help="Target clip length in seconds")
    run_parser.add_argument("--max-clips", type=int, default=10, help="Maximum number of clips")
    run_parser.add_argument("--job-id", help="Explicit job ID to use")
    run_parser.add_argument("--from-stage", choices=STAGES, help="Force redo starting from stage")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume an existing job")
    resume_parser.add_argument("job_id", help="Job ID to resume")
    resume_parser.add_argument("--from-stage", choices=STAGES, help="Force redo starting from stage")

    args = parser.parse_args()

    if args.command == "run":
        if args.job_id:
            job_id = args.job_id
        elif args.fake:
            job_id = args.input
        else:
            # If real mode, sanitize input into job_id if necessary
            if args.input.startswith("http://") or args.input.startswith("https://"):
                job_id = "job_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                job_id = Path(args.input).stem
        pipeline = ClipperPipeline(
            job_id=job_id,
            input_src=args.input,
            fake=args.fake,
            template_id=args.template,
            lang=args.lang,
            target_len=args.target_len,
            max_clips=args.max_clips,
            from_stage=args.from_stage
        )
        pipeline.run()

    elif args.command == "resume":
        manifest_file = WORK_DIR / args.job_id / "manifest.json"
        if not manifest_file.exists():
            print(f"Error: Job '{args.job_id}' not found.", file=sys.stderr)
            sys.exit(1)
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        pipeline = ClipperPipeline(
            job_id=args.job_id,
            input_src=manifest.get("source", args.job_id),
            fake=True,
            from_stage=args.from_stage
        )
        pipeline.run()

if __name__ == "__main__":
    main()
