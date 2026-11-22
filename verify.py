#!/usr/bin/env python3
"""
End-to-end verification script for AI Clipper (v1, mock-backed).
Checks acceptance criteria 1 through 8.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

PORT = int(os.environ.get("PORT", 8765))
BASE_URL = f"http://127.0.0.1:{PORT}"

def wait_for_server(port, timeout=5.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False

def run_tests():
    print("=" * 60)
    print("AI CLIPPER ACCEPTANCE TESTS")
    print("=" * 60)

    # Ensure .tmp exists
    os.makedirs(".tmp", exist_ok=True)

    # Start server in foreground of python test process
    server_proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).resolve().parent)
    )

    try:
        if not wait_for_server(PORT, timeout=5.0):
            print(f"FAILED: Server failed to start on port {PORT}")
            return 1

        all_passed = True

        # 1. python server.py starts and curl -s -o .tmp/home.html -w "%{http_code}" http://127.0.0.1:8765/ -> 200
        print("\n--- Criteria 1: Server start & root status 200 ---")
        curl_cmd_1 = ["curl", "-s", "-o", ".tmp/home.html", "-w", "%{http_code}", f"{BASE_URL}/"]
        res_1 = subprocess.run(curl_cmd_1, capture_output=True, text=True)
        http_code_1 = res_1.stdout.strip()
        print(f"Output: {http_code_1}")
        if http_code_1 == "200":
            print("Criteria 1: PASS")
        else:
            print(f"Criteria 1: FAIL (expected 200, got {http_code_1})")
            all_passed = False

        # 2. curl -s http://127.0.0.1:8765/api/jobs -> valid JSON containing "demo-job"
        print("\n--- Criteria 2: GET /api/jobs returns valid JSON with 'demo-job' ---")
        curl_cmd_2 = ["curl", "-s", f"{BASE_URL}/api/jobs"]
        res_2 = subprocess.run(curl_cmd_2, capture_output=True, text=True)
        jobs_json_raw = res_2.stdout
        try:
            jobs_data = json.loads(jobs_json_raw)
            has_demo = any(j.get("job_id") == "demo-job" for j in jobs_data.get("jobs", []))
            print(f"Output: Found 'demo-job' = {has_demo}, Total jobs: {len(jobs_data.get('jobs', []))}")
            if has_demo:
                print("Criteria 2: PASS")
            else:
                print("Criteria 2: FAIL ('demo-job' not found in jobs)")
                all_passed = False
        except Exception as e:
            print(f"Criteria 2: FAIL (JSON parse error: {e})")
            all_passed = False

        # 3. curl -s http://127.0.0.1:8765/api/jobs/demo-job -> JSON with len(clips)==3, scores [88,72,45], durations [41,75,12]
        print("\n--- Criteria 3: GET /api/jobs/demo-job clips, scores, durations ---")
        curl_cmd_3 = ["curl", "-s", f"{BASE_URL}/api/jobs/demo-job"]
        res_3 = subprocess.run(curl_cmd_3, capture_output=True, text=True)
        demo_json_raw = res_3.stdout
        try:
            demo_data = json.loads(demo_json_raw)
            clips = demo_data.get("clips", [])
            scores = [c.get("virality_score", c.get("score")) for c in clips]
            durations = [c.get("duration", c.get("duration_s")) for c in clips]
            print(f"Output: len(clips)={len(clips)}, scores={scores}, durations={durations}")
            if len(clips) == 3 and scores == [88, 72, 45] and durations == [41, 75, 12]:
                print("Criteria 3: PASS")
            else:
                print(f"Criteria 3: FAIL (expected len=3, scores=[88,72,45], durations=[41,75,12])")
                all_passed = False
        except Exception as e:
            print(f"Criteria 3: FAIL (JSON parse error: {e})")
            all_passed = False

        # 4. curl -s http://127.0.0.1:8765/api/jobs/demo-job/srt/1 -> SRT text starting with 1\n00:00:00
        print("\n--- Criteria 4: GET /api/jobs/demo-job/srt/1 starts with 1\\n00:00:00 ---")
        curl_cmd_4 = ["curl", "-s", f"{BASE_URL}/api/jobs/demo-job/srt/1"]
        res_4 = subprocess.run(curl_cmd_4, capture_output=True, text=True)
        srt_raw = res_4.stdout
        # Normalize carriage returns
        srt_normalized = srt_raw.replace("\r\n", "\n")
        first_line_and_time = "\n".join(srt_normalized.split("\n")[:2])
        print(f"Output preview:\n{first_line_and_time}")
        if srt_normalized.startswith("1\n00:00:00"):
            print("Criteria 4: PASS")
        else:
            print(f"Criteria 4: FAIL (SRT did not start with 1\\n00:00:00)")
            all_passed = False

        # 5. curl -s http://127.0.0.1:8765/ body contains 'AI Clipper', 'Start clipping', 'Virality'
        print("\n--- Criteria 5: Root body contains required strings ---")
        curl_cmd_5 = ["curl", "-s", f"{BASE_URL}/"]
        res_5 = subprocess.run(curl_cmd_5, capture_output=True, text=True)
        body_5 = res_5.stdout
        req_5 = ["AI Clipper", "Start clipping", "Virality"]
        found_5 = [s in body_5 for s in req_5]
        print(f"Output: 'AI Clipper': {found_5[0]}, 'Start clipping': {found_5[1]}, 'Virality': {found_5[2]}")
        if all(found_5):
            print("Criteria 5: PASS")
        else:
            print(f"Criteria 5: FAIL (Missing strings: {[s for s, f in zip(req_5, found_5) if not f]})")
            all_passed = False

        # 6. curl -s http://127.0.0.1:8765/job.html?id=demo-job body contains 'The 3 rules of great data pipelines', 'Download MP4', 'Copy caption'
        print("\n--- Criteria 6: Job detail body contains required strings ---")
        curl_cmd_6 = ["curl", "-s", f"{BASE_URL}/job.html?id=demo-job"]
        res_6 = subprocess.run(curl_cmd_6, capture_output=True, text=True)
        body_6 = res_6.stdout
        req_6 = ["The 3 rules of great data pipelines", "Download MP4", "Copy caption"]
        found_6 = [s in body_6 for s in req_6]
        print(f"Output: 'The 3 rules...': {found_6[0]}, 'Download MP4': {found_6[1]}, 'Copy caption': {found_6[2]}")
        if all(found_6):
            print("Criteria 6: PASS")
        else:
            print(f"Criteria 6: FAIL (Missing strings: {[s for s, f in zip(req_6, found_6) if not f]})")
            all_passed = False

        # 7. python -c JSON parse of step 2/3 output succeeds (no trailing garbage)
        print("\n--- Criteria 7: Strict JSON parse of step 2 and 3 output ---")
        parse_cmd_2 = [sys.executable, "-c", "import json, sys; json.loads(sys.stdin.read()); sys.exit(0)"]
        p2 = subprocess.run(parse_cmd_2, input=jobs_json_raw, text=True, capture_output=True)
        p3 = subprocess.run(parse_cmd_2, input=demo_json_raw, text=True, capture_output=True)
        print(f"Output: step 2 exit code={p2.returncode}, step 3 exit code={p3.returncode}")
        if p2.returncode == 0 and p3.returncode == 0:
            print("Criteria 7: PASS")
        else:
            print(f"Criteria 7: FAIL (p2: {p2.stderr}, p3: {p3.stderr})")
            all_passed = False

        # 8. All criteria pass -> exit 0
        print("\n--- Criteria 8: End-to-end verification result ---")
        if all_passed:
            print("ALL 8 ACCEPTANCE CRITERIA PASSED!")
            return 0
        else:
            print("SOME ACCEPTANCE CRITERIA FAILED.")
            return 1

    finally:
        # Bounded cleanup of server process
        server_proc.terminate()
        try:
            server_proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            server_proc.kill()

if __name__ == "__main__":
    sys.exit(run_tests())
