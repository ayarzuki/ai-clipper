#!/usr/bin/env python3
"""
AI Clipper - Thin local web server (mock-backed v1)
Python standard library only.
"""

import os
import sys
import re
import json
import threading
import subprocess
import urllib.parse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
WORK_DIR = BASE_DIR / "work"

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

def run_clipper_worker(cmd, job_dir):
    log_path = job_dir / "run.log"
    manifest_path = job_dir / "manifest.json"
    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=os.environ.copy()
        )
        proc.wait()

    if proc.returncode != 0:
        error_line = "Job failed with non-zero exit code"
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                for l in reversed(lines):
                    if any(k in l.lower() for k in ["error", "exception", "not found", "failed", "cannot", "no such"]):
                        error_line = l
                        break
                else:
                    if lines:
                        error_line = lines[-1]
            except Exception:
                pass

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    m = json.load(f)
                m["status"] = "failed"
                if not m.get("error"):
                    m["error"] = error_line
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(m, f, indent=2)
            except Exception:
                pass

def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS,mmm for SRT."""
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    sec = total_sec % 60
    total_min = total_sec // 60
    minute = total_min % 60
    hour = total_min // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"

def generate_srt(transcript: list, clip_start: float, clip_end: float) -> str:
    """Generate SRT subtitle text for a clip from transcript lines."""
    matching = []
    for item in transcript:
        t_start = item.get("start", 0.0)
        t_end = item.get("end", 0.0)
        if t_end > clip_start and t_start < clip_end:
            matching.append(item)
    
    if not matching:
        # Fallback single line
        return f"1\n00:00:00,000 --> {format_timestamp(clip_end - clip_start)}\n[No dialogue]\n"
    
    lines = []
    for idx, item in enumerate(matching, 1):
        rel_start = max(0.0, item.get("start", 0.0) - clip_start)
        rel_end = min(clip_end - clip_start, item.get("end", 0.0) - clip_start)
        if rel_end <= rel_start:
            rel_end = rel_start + 1.0
        time_str = f"{format_timestamp(rel_start)} --> {format_timestamp(rel_end)}"
        lines.append(f"{idx}\n{time_str}\n{item.get('text', '').strip()}\n")
    
    return "\n".join(lines).strip() + "\n"

class AIClipperHandler(BaseHTTPRequestHandler):
    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 404):
        self.send_json({"error": message}, status=status)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 0. API: GET /api/caption-templates
        if path == "/api/caption-templates":
            templates_file = STATIC_DIR / "caption-templates.json"
            if templates_file.exists():
                try:
                    with open(templates_file, "r", encoding="utf-8") as f:
                        templates = json.load(f)
                    self.send_json(templates)
                    return
                except Exception as e:
                    self.send_error_json(f"Error reading templates: {str(e)}", 500)
                    return
            self.send_error_json("caption-templates.json not found", 404)
            return

        # 1. API: GET /api/jobs
        if path == "/api/jobs":
            jobs = []
            if WORK_DIR.is_dir():
                for job_folder in sorted(WORK_DIR.iterdir()):
                    if not job_folder.is_dir():
                        continue
                    meta_file = job_folder / "metadata.json"
                    manifest_file = job_folder / "manifest.json"
                    if not meta_file.exists() and not manifest_file.exists():
                        continue
                    
                    manifest = {}
                    if manifest_file.exists():
                        try:
                            with open(manifest_file, "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                        except Exception:
                            pass
                    
                    meta = {}
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                        except Exception:
                            pass
                    
                    job_id = manifest.get("job_id") or meta.get("job_id") or job_folder.name
                    source = manifest.get("source") or meta.get("source") or "Unknown source"
                    status = manifest.get("status") or "done"
                    clip_count = len(meta.get("clips", [])) if "clips" in meta else manifest.get("clip_count", 0)
                    created = manifest.get("created") or "2026-09-22T00:00:00Z"
                    stages = manifest.get("stages") or {
                        "ingest": "done", "asr": "done", "normalize": "done",
                        "select": "done", "render": "done", "package": "done"
                    }
                    jobs.append({
                        "job_id": job_id,
                        "source": source,
                        "status": status,
                        "clip_count": clip_count,
                        "created": created,
                        "stages": stages
                    })
            self.send_json({"jobs": jobs})
            return

        # 2. API: GET /api/jobs/<id>/srt/<clip_id>
        if path.startswith("/api/jobs/") and "/srt/" in path:
            parts = path.strip("/").split("/")
            # parts = ["api", "jobs", "<id>", "srt", "<clip_id>"]
            if len(parts) == 5:
                job_id = parts[2]
                try:
                    clip_id = int(parts[4])
                except ValueError:
                    self.send_error_json("Invalid clip id", 400)
                    return
                
                job_dir = WORK_DIR / job_id
                meta_file = job_dir / "metadata.json"
                transcript_file = job_dir / "transcript.json"

                if not job_dir.exists() or not meta_file.exists():
                    self.send_error_json("Job not found", 404)
                    return
                
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    transcript = []
                    if transcript_file.exists():
                        with open(transcript_file, "r", encoding="utf-8") as f:
                            transcript = json.load(f)
                    
                    clip = None
                    for c in meta.get("clips", []):
                        if c.get("id") == clip_id:
                            clip = c
                            break
                    
                    if not clip:
                        self.send_error_json("Clip not found", 404)
                        return
                    
                    c_start = float(clip.get("start", 0.0))
                    c_end = float(clip.get("end", c_start + clip.get("duration", 30.0)))
                    srt_content = generate_srt(transcript, c_start, c_end)
                    srt_bytes = srt_content.encode("utf-8")

                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="clip_{clip_id}.srt"')
                    self.send_header("Content-Length", str(len(srt_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(srt_bytes)
                    return
                except Exception as e:
                    self.send_error_json(f"Error reading SRT: {str(e)}", 500)
                    return

        # 3. API: GET /api/jobs/<id>
        if path.startswith("/api/jobs/"):
            job_id = path[len("/api/jobs/"):].strip("/")
            job_dir = WORK_DIR / job_id
            if not job_dir.exists() or not job_dir.is_dir():
                self.send_error_json("not found", 404)
                return
            
            meta_file = job_dir / "metadata.json"
            manifest_file = job_dir / "manifest.json"
            transcript_file = job_dir / "transcript.json"

            if not meta_file.exists() and not manifest_file.exists():
                self.send_error_json("not found", 404)
                return

            manifest = {}
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception:
                    pass

            meta = {}
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    pass

            transcript = []
            if transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        transcript = json.load(f)
                except Exception:
                    pass

            # Make sure clips have duration & virality_score properly set
            clips = meta.get("clips", [])
            for c in clips:
                if "duration" not in c:
                    c["duration"] = int(c.get("end", 0.0) - c.get("start", 0.0))
                if "duration_s" not in c:
                    c["duration_s"] = c["duration"]
                if "virality_score" not in c and "score" in c:
                    c["virality_score"] = c["score"]
                if "score" not in c and "virality_score" in c:
                    c["score"] = c["virality_score"]
                if "caption_template" not in c:
                    c["caption_template"] = "karaoke-classic"

            response_data = {
                "job_id": job_id,
                "source": manifest.get("source") or meta.get("source", "Unknown"),
                "status": manifest.get("status") or meta.get("status", "done"),
                "error": manifest.get("error", None),
                "duration_s": manifest.get("duration_s") or meta.get("duration_s", 0),
                "stages": manifest.get("stages", {
                    "ingest": "done", "asr": "done", "normalize": "done",
                    "select": "done", "render": "done", "package": "done"
                }),
                "transcript": transcript,
                "clips": clips
            }
            self.send_json(response_data)
            return

        # 4. Static Files
        # Resolve target static file
        if path == "/" or path == "/index.html":
            file_path = STATIC_DIR / "index.html"
        elif path == "/job.html":
            file_path = STATIC_DIR / "job.html"
        elif path.startswith("/static/"):
            file_path = STATIC_DIR / path[len("/static/"):]
        else:
            file_path = STATIC_DIR / path.lstrip("/")

        # Also support serving clip videos or work artifacts if needed
        if not file_path.exists() and path.startswith("/work/"):
            file_path = WORK_DIR / path[len("/work/"):]

        if file_path.exists() and file_path.is_file():
            self.serve_static_file(file_path)
        else:
            self.send_error_json("not found", 404)

    def serve_static_file(self, file_path: Path):
        ext = file_path.suffix.lower()
        content_type_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".mp4": "video/mp4",
            ".srt": "text/plain; charset=utf-8",
        }
        content_type = content_type_map.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error_json(f"Error reading file: {str(e)}", 500)

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/jobs":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self.send_error_json("Request body required", 400)
                return

            try:
                raw_body = self.rfile.read(content_length)
                body = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self.send_error_json(f"Invalid JSON: {str(e)}", 400)
                return

            url_or_path = body.get("url_or_path") or body.get("url") or body.get("input")
            language = body.get("language") or body.get("lang") or "en"
            target_len_s = body.get("target_len_s") or body.get("target_len") or 45
            max_clips = body.get("max_clips") or 10
            mode = body.get("mode") or "fake"

            # Input validation: reject empty or NUL/newlines
            if not url_or_path or not isinstance(url_or_path, str) or not url_or_path.strip():
                self.send_error_json("url_or_path is required", 400)
                return

            if "\0" in url_or_path or "\n" in url_or_path or "\r" in url_or_path:
                self.send_error_json("invalid characters in url_or_path", 400)
                return

            # Concurrency guard: check if any job is queued/running
            running_job_id = None
            if WORK_DIR.is_dir():
                for job_folder in sorted(WORK_DIR.iterdir()):
                    if not job_folder.is_dir():
                        continue
                    mf = job_folder / "manifest.json"
                    if mf.exists():
                        try:
                            with open(mf, "r", encoding="utf-8") as f:
                                m = json.load(f)
                            if m.get("status") in ("queued", "running"):
                                running_job_id = m.get("job_id") or job_folder.name
                                break
                        except Exception:
                            pass

            if running_job_id:
                self.send_json({"error": "a job is already running", "job_id": running_job_id}, status=409)
                return

            # Generate job_id = slug of source (<= 24 chars) + "-" + YYYYMMDD-HHMMSS
            raw_slug = re.sub(r'[^a-zA-Z0-9]+', '-', url_or_path.strip()).strip('-').lower()
            slug = raw_slug[:24].strip('-') or "job"
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            job_id = f"{slug}-{timestamp}"

            job_dir = WORK_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)

            initial_manifest = {
                "job_id": job_id,
                "source": url_or_path,
                "status": "queued",
                "clip_count": 0,
                "created": datetime.now(timezone.utc).isoformat(),
                "target_len_s": int(target_len_s),
                "duration_s": 0,
                "stages": {
                    "ingest": "pending",
                    "asr": "pending",
                    "normalize": "pending",
                    "select": "pending",
                    "render": "pending",
                    "package": "pending"
                }
            }
            with open(job_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(initial_manifest, f, indent=2)

            if mode == "fake":
                cmd = [sys.executable, "clipper.py", "run", "--fake", job_id]
            else:
                cmd = [
                    sys.executable, "clipper.py", "run", url_or_path,
                    "--lang", language,
                    "--target-len", str(target_len_s),
                    "--max-clips", str(max_clips),
                    "--job-id", job_id
                ]

            t = threading.Thread(target=run_clipper_worker, args=(cmd, job_dir), daemon=True)
            t.start()

            self.send_json({"job_id": job_id, "mode": mode, "status": "queued"}, status=201)
            return

        self.send_error_json("not found", 404)

    def log_message(self, format, *args):
        """Suppress standard HTTP server request log to keep output clean."""
        # Sys log can be written to run-ui.log if needed
        pass

def run():
    port = int(os.environ.get("PORT", 8765))
    server_address = ("", port)
    httpd = HTTPServer(server_address, AIClipperHandler)
    print(f"AI Clipper server listening on http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    run()
