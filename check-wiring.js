#!/usr/bin/env node
/**
 * check-wiring.js — UI -> Pipeline glue CDP verification (Node >= 21, ZERO npm deps)
 *
 * Asserts:
 * (a) Submitting the form with mode=demo navigates/lands on a job page and a toast appears (or new job row appears).
 * (b) While a job runs, the job page shows a non-"done" stage state at least once and reaches "done" within 300s.
 * (c) Failed-job error banner path: set work/<id>/manifest.json {"status":"failed","error":"test error 123"}
 *     on a scratch job folder, open its job page -> body contains "test error 123".
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CHROME_PATH = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const CDP_PORT = 9333;
const SERVER_PORT = process.env.PORT || 8765;
const BASE_URL = `http://127.0.0.1:${SERVER_PORT}`;

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.msgId = 1;
    this.callbacks = new Map();
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id && this.callbacks.has(data.id)) {
        const { resolve, reject } = this.callbacks.get(data.id);
        this.callbacks.delete(data.id);
        if (data.error) {
          reject(new Error(data.error.message || JSON.stringify(data.error)));
        } else {
          resolve(data.result);
        }
      }
    };
  }

  async waitOpen() {
    if (this.ws.readyState === WebSocket.OPEN) return;
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.msgId++;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression: expression,
      returnByValue: true
    });
    return res.result ? res.result.value : undefined;
  }

  close() {
    try {
      this.ws.close();
    } catch (_) {}
  }
}

async function isPortOpen(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(500) });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function isServerRunning() {
  try {
    const res = await fetch(`${BASE_URL}/api/jobs`, { signal: AbortSignal.timeout(500) });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function main() {
  console.log("============================================================");
  console.log("CHECK WIRING TEST (CDP)");
  console.log("============================================================");

  let serverProc = null;
  let chromeProc = null;
  const profileDir = path.resolve(`.tmp/cdp-wiring-profile-${Date.now()}`);
  const scratchDir = path.resolve("work/test-failed-scratch");

  try {
    // 1. Ensure server is running
    if (!(await isServerRunning())) {
      const pyCmd = process.platform === 'win32' ? 'python' : 'python3';
      serverProc = spawn(pyCmd, ['server.py'], { cwd: process.cwd() });
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 200));
        if (await isServerRunning()) break;
      }
      if (!(await isServerRunning())) {
        console.error('FAILED: could not start server.py');
        process.exit(1);
      }
    }

    // 2. Launch headless Chrome with CDP
    chromeProc = spawn(CHROME_PATH, [
      '--headless=new',
      `--remote-debugging-port=${CDP_PORT}`,
      '--remote-allow-origins=*',
      `--user-data-dir=${profileDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-gpu',
      '--window-size=1440,900'
    ]);

    let cdpReady = false;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 200));
      if (await isPortOpen(CDP_PORT)) {
        cdpReady = true;
        break;
      }
    }

    if (!cdpReady) {
      console.error('FAILED: Chrome CDP port not ready');
      process.exit(1);
    }

    const listRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const targets = await listRes.json();
    const pageTarget = targets.find(t => t.type === 'page') || targets[0];
    const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await cdp.waitOpen();
    await cdp.send('Page.enable');

    // -------------------------------------------------------------
    // Assertion (c): Failed-job error banner path
    // -------------------------------------------------------------
    console.log("\n--- Checking (c): Failed-job error banner ---");
    fs.mkdirSync(scratchDir, { recursive: true });
    const scratchManifest = {
      job_id: "test-failed-scratch",
      source: "scratch-test-source",
      status: "failed",
      error: "test error 123",
      stages: { ingest: "failed" }
    };
    fs.writeFileSync(path.join(scratchDir, "manifest.json"), JSON.stringify(scratchManifest, null, 2), "utf-8");

    await cdp.send('Page.navigate', { url: `${BASE_URL}/job.html?id=test-failed-scratch` });
    await new Promise(r => setTimeout(r, 1000));

    const bodyText = await cdp.eval(`document.body.innerText`);
    console.log(`Page contains "test error 123": ${bodyText.includes("test error 123")}`);
    if (!bodyText.includes("test error 123")) {
      console.error("FAILED: 'test error 123' not found in job page body for failed job");
      process.exit(1);
    }
    console.log("Check (c) PASS: failed-job error banner correctly rendered 'test error 123'");

    // -------------------------------------------------------------
    // Assertion (a): Submit form with mode=demo navigates to job page
    // -------------------------------------------------------------
    console.log("\n--- Checking (a): Form submission & navigation ---");
    await cdp.send('Page.navigate', { url: `${BASE_URL}/` });
    await new Promise(r => setTimeout(r, 1000));

    // Fill form and submit
    const submitResult = await cdp.eval(`
      (() => {
        const input = document.getElementById("url_or_path");
        const mode = document.getElementById("mode");
        const btn = document.getElementById("start-btn");
        if (!input || !btn) return { error: "Form inputs not found" };
        input.value = "fake:wiretest";
        if (mode) mode.value = "fake";
        btn.click();
        return { success: true };
      })()
    `);
    console.log("Form submit click result:", submitResult);

    // Wait for navigation / landing on job.html
    let currentUrl = "";
    let landedJobId = "";
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 200));
      currentUrl = await cdp.eval(`window.location.href`);
      if (currentUrl.includes("job.html?id=")) {
        const match = currentUrl.match(/job\.html\?id=([^&]+)/);
        if (match) landedJobId = decodeURIComponent(match[1]);
        break;
      }
    }

    console.log(`Current URL after submission: ${currentUrl}`);
    console.log(`Landed Job ID: ${landedJobId}`);
    if (!landedJobId || !landedJobId.startsWith("fake-wiretest")) {
      console.error(`FAILED: did not navigate to job.html with job_id starting with fake-wiretest (got ${currentUrl})`);
      process.exit(1);
    }
    console.log("Check (a) PASS: Submitting form navigated to job page for", landedJobId);

    // -------------------------------------------------------------
    // Assertion (b): Shows non-'done' stage state and reaches 'done'
    // -------------------------------------------------------------
    console.log("\n--- Checking (b): Non-'done' stage observation and reach 'done' ---");
    let sawNonDone = false;
    let isDone = false;
    const startTime = Date.now();

    while (Date.now() - startTime < 300000) { // 300s timeout
      const pageState = await cdp.eval(`
        (() => {
          const dots = Array.from(document.querySelectorAll("#stage-stepper .mini-dot"));
          const dotClasses = dots.map(d => d.className);
          const hasNonDone = dotClasses.some(c => c.includes("running") || c.includes("pending"));
          const allDone = dotClasses.length === 6 && dotClasses.every(c => c.includes("done"));
          const cards = document.querySelectorAll(".clip-card").length;
          return { dotClasses, hasNonDone, allDone, cards };
        })()
      `);

      if (pageState.hasNonDone) {
        sawNonDone = true;
      }

      console.log(`  [${Math.round((Date.now() - startTime) / 1000)}s] sawNonDone=${sawNonDone}, allDone=${pageState.allDone}, cards=${pageState.cards}, dots=${JSON.stringify(pageState.dotClasses)}`);

      if (pageState.allDone && pageState.cards === 3) {
        isDone = true;
        break;
      }

      await new Promise(r => setTimeout(r, 2000));
    }

    if (!sawNonDone) {
      console.error("FAILED: did not observe non-'done' stage state during job execution");
      process.exit(1);
    }
    if (!isDone) {
      console.error("FAILED: job did not reach 'done' state with 3 clip cards within 300s");
      process.exit(1);
    }

    console.log("Check (b) PASS: Job observed in active processing state and reached 'done' with 3 clips!");

    cdp.close();
    console.log("\nALL CHECK-WIRING ASSERTIONS PASSED!");
    process.exit(0);

  } catch (err) {
    console.error("Error in check-wiring.js:", err);
    process.exit(1);
  } finally {
    if (chromeProc) {
      chromeProc.kill();
      try { chromeProc.unref(); } catch (_) {}
    }
    if (serverProc) {
      serverProc.kill();
    }
    try {
      fs.rmSync(profileDir, { recursive: true, force: true });
    } catch (_) {}
    try {
      fs.rmSync(scratchDir, { recursive: true, force: true });
    } catch (_) {}
  }
}

main();
