#!/usr/bin/env node
/**
 * check-overflow.js — Headless CDP overflow test (Node >= 21, ZERO npm deps)
 *
 * For each page (home, job) and width (360, 390, 768, 1440):
 * - Emulation.setDeviceMetricsOverride
 * - Evaluates document.documentElement.scrollWidth - document.documentElement.clientWidth
 *   and document.body.scrollWidth - document.body.clientWidth
 * - Prints: page width overflow_doc overflow_body
 * - Exits 0 only if all values <= 0 and ASR assertion passes.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CHROME_PATH = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const CDP_PORT = 9333;
const SERVER_PORT = process.env.PORT || 8765;
const BASE_URL = `http://127.0.0.1:${SERVER_PORT}`;

const PAGES = [
  `${BASE_URL}/`,
  `${BASE_URL}/job.html?id=demo-job`
];

const WIDTHS = [360, 390, 768, 1440];
const HEIGHT = 800;

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
    const res = await fetch(`${BASE_URL}/`, { signal: AbortSignal.timeout(500) });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function main() {
  let serverProc = null;
  let chromeProc = null;
  const profileDir = path.resolve(`.tmp/cdp-profile-${Date.now()}`);

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
        console.error('Failed to start server.py');
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

    // Poll until CDP is available
    let cdpReady = false;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 200));
      if (await isPortOpen(CDP_PORT)) {
        cdpReady = true;
        break;
      }
    }

    if (!cdpReady) {
      console.error('Chrome CDP did not become ready in time');
      process.exit(1);
    }

    // Get page target
    const listRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const targets = await listRes.json();
    const pageTarget = targets.find(t => t.type === 'page') || targets[0];
    if (!pageTarget || !pageTarget.webSocketDebuggerUrl) {
      console.error('No page target found');
      process.exit(1);
    }

    const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await cdp.waitOpen();
    await cdp.send('Page.enable');

    let allPassed = true;
    let asrAssertionPassed = true;

    for (const pageUrl of PAGES) {
      await cdp.send('Page.navigate', { url: pageUrl });
      // Wait for page load and hydration
      await new Promise(r => setTimeout(r, 500));

      for (const width of WIDTHS) {
        await cdp.send('Emulation.setDeviceMetricsOverride', {
          width: width,
          height: HEIGHT,
          deviceScaleFactor: 1,
          mobile: width < 768
        });

        // Small wait for responsive styles to take effect
        await new Promise(r => setTimeout(r, 100));

        const evalRes = await cdp.send('Runtime.evaluate', {
          expression: `JSON.stringify({
            docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            bodyOverflow: document.body.scrollWidth - document.body.clientWidth,
            text: document.body.innerText
          })`,
          returnByValue: true
        });

        const data = JSON.parse(evalRes.result.value);
        const overflowDoc = data.docOverflow;
        const overflowBody = data.bodyOverflow;

        // Print: page width overflow_doc overflow_body
        console.log(`${pageUrl} ${width} ${overflowDoc} ${overflowBody}`);

        if (overflowDoc > 0 || overflowBody > 0) {
          allPassed = false;
        }

        // On job page, assert ASR verbatim and not " Asr"
        if (pageUrl.includes('job.html')) {
          const hasASR = data.text.includes('ASR');
          const hasAsr = data.text.includes(' Asr') || data.text.includes('\nAsr') || data.text.includes('. Asr');
          if (!hasASR || hasAsr) {
            asrAssertionPassed = false;
          }
        }
      }
    }

    cdp.close();

    if (asrAssertionPassed) {
      console.log('ASR assertion: PASS (contains "ASR", does not contain " Asr")');
    } else {
      console.log('ASR assertion: FAIL');
      allPassed = false;
    }

    if (allPassed) {
      process.exit(0);
    } else {
      process.exit(1);
    }
  } catch (err) {
    console.error('Error in check-overflow:', err);
    process.exit(1);
  } finally {
    if (chromeProc) {
      chromeProc.kill();
      try {
        chromeProc.unref();
      } catch (_) {}
    }
    if (serverProc) {
      serverProc.kill();
    }
    // Clean temp profile if possible
    setTimeout(() => {
      try {
        fs.rmSync(profileDir, { recursive: true, force: true });
      } catch (_) {}
    }, 1000);
  }
}

main();
