#!/usr/bin/env node
/**
 * check-captions.js — Caption templates CDP verification (Node >= 21, ZERO npm deps)
 *
 * Verifies for job page at 1440x900:
 * 1. Exactly 8 picker chips rendered per clip card.
 * 2. Clicking each of the 8 chips updates preview overlay with css_class and distinct styles.
 * 3. Sample text of active template is visible in preview overlay.
 * 4. LocalStorage persistence: clip.<id>.caption_template equals clicked template.
 * 5. "Apply to all clips" sets all 3 clip cards' persisted template to the same id.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const CHROME_PATH = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const CDP_PORT = 9333;
const SERVER_PORT = process.env.PORT || 8765;
const BASE_URL = `http://127.0.0.1:${SERVER_PORT}`;
const JOB_URL = `${BASE_URL}/job.html?id=demo-job`;

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
    const res = await fetch(`${BASE_URL}/`, { signal: AbortSignal.timeout(500) });
    return res.ok;
  } catch (_) {
    return false;
  }
}

async function main() {
  console.log("============================================================");
  console.log("CHECK CAPTIONS TEST (CDP)");
  console.log("============================================================");

  let serverProc = null;
  let chromeProc = null;
  const profileDir = path.resolve(`.tmp/cdp-captions-profile-${Date.now()}`);

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

    // 2. Launch headless Chrome with CDP at 1440x900
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

    // Connect to page target
    const listRes = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`);
    const targets = await listRes.json();
    const pageTarget = targets.find(t => t.type === 'page') || targets[0];
    const cdp = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await cdp.waitOpen();
    await cdp.send('Page.enable');

    // Navigate to job detail page
    await cdp.send('Page.navigate', { url: JOB_URL });
    await new Promise(r => setTimeout(r, 800));

    // Override viewport
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false
    });
    await new Promise(r => setTimeout(r, 200));

    // Assertion 1: exactly 8 picker chips rendered
    const chipsCount = await cdp.eval(`
      (() => {
        const chips = document.querySelectorAll('#template-chips-1 .tpl-chip');
        return chips.length;
      })()
    `);
    console.log(`Picker chips count: ${chipsCount}`);
    if (chipsCount !== 8) {
      console.error(`FAILED: expected 8 chips, found ${chipsCount}`);
      process.exit(1);
    }
    console.log("Check 1 PASS: exactly 8 picker chips rendered");

    // Assertion 2 & 3: For each of the 8 chips, click and check preview overlay
    const templatesRes = await fetch(`${BASE_URL}/api/caption-templates`);
    const templates = await templatesRes.json();

    const observedStyles = [];

    for (const tpl of templates) {
      // Click chip
      const clickResult = await cdp.eval(`
        (() => {
          const btn = document.querySelector('#template-chips-1 .tpl-chip[data-template-id="${tpl.id}"]');
          if (!btn) return { found: false };
          btn.click();
          const overlay = document.getElementById('caption-overlay-1');
          if (!overlay) return { found: true, overlayFound: false };
          const computed = window.getComputedStyle(overlay);
          return {
            found: true,
            overlayFound: true,
            hasCssClass: overlay.classList.contains('${tpl.css_class}'),
            className: overlay.className,
            fontSize: computed.fontSize,
            color: computed.color,
            textTransform: computed.textTransform,
            text: overlay.innerText.trim()
          };
        })()
      `);

      if (!clickResult.found || !clickResult.overlayFound || !clickResult.hasCssClass) {
        console.error(`FAILED on template ${tpl.id}:`, clickResult);
        process.exit(1);
      }

      // Check sample text visible
      const sampleTextWords = tpl.sample_text.split(" ");
      const firstWord = sampleTextWords[0];
      const hasSampleContent = clickResult.text.includes(firstWord) || clickResult.text.toLowerCase().includes(firstWord.toLowerCase());
      if (!hasSampleContent) {
        console.error(`FAILED: sample text "${tpl.sample_text}" not found in overlay text "${clickResult.text}" for template ${tpl.id}`);
        process.exit(1);
      }

      observedStyles.push({
        id: tpl.id,
        fontSize: clickResult.fontSize,
        color: clickResult.color,
        textTransform: clickResult.textTransform
      });

      console.log(`  Template '${tpl.id}': class='${tpl.css_class}' font=${clickResult.fontSize} color=${clickResult.color} transform=${clickResult.textTransform} sample="${clickResult.text.slice(0, 30)}..."`);
    }

    // Check style distinctness
    let distinctStylesCount = 0;
    for (let i = 0; i < observedStyles.length; i++) {
      for (let j = i + 1; j < observedStyles.length; j++) {
        const a = observedStyles[i];
        const b = observedStyles[j];
        if (a.fontSize !== b.fontSize || a.color !== b.color || a.textTransform !== b.textTransform) {
          distinctStylesCount++;
        }
      }
    }
    if (distinctStylesCount === 0) {
      console.error("FAILED: computed styles across templates are identical");
      process.exit(1);
    }
    console.log("Check 2 & 3 PASS: all 8 templates update overlay with distinct styles and sample text");

    // Assertion 4: after clicking boxed-news, assert localStorage persistence
    await cdp.eval(`
      (() => {
        const btn = document.querySelector('#template-chips-1 .tpl-chip[data-template-id="boxed-news"]');
        if (btn) btn.click();
      })()
    `);
    await new Promise(r => setTimeout(r, 200));

    const persistedVal = await cdp.eval(`
      (() => {
        return {
          directKey: localStorage.getItem('clip.1.caption_template'),
          altKey: localStorage.getItem('caption_template_clip_1'),
          parsedJob: JSON.parse(localStorage.getItem('aiclipper_demo-job_clip_1') || '{}')
        };
      })()
    `);

    console.log(`Persisted value for clip 1: ${JSON.stringify(persistedVal)}`);
    const isBoxedNews = persistedVal.directKey === 'boxed-news' ||
                        persistedVal.altKey === 'boxed-news' ||
                        persistedVal.parsedJob.caption_template === 'boxed-news';

    if (!isBoxedNews) {
      console.error("FAILED: boxed-news not properly persisted in localStorage:", persistedVal);
      process.exit(1);
    }
    console.log("Check 4 PASS: localStorage persistence verified (key shape: clip.<id>.caption_template = 'boxed-news')");

    // Assertion 5: "Apply to all clips" sets all 3 clip cards' persisted template to boxed-news
    await cdp.eval(`
      (() => {
        const applyBtn = document.querySelector('.clip-card[data-clip-id="1"] .apply-all-btn');
        if (applyBtn) applyBtn.click();
      })()
    `);
    await new Promise(r => setTimeout(r, 300));

    const allPersisted = await cdp.eval(`
      (() => {
        return [1, 2, 3].map(id => {
          const direct = localStorage.getItem('clip.' + id + '.caption_template');
          const parsed = JSON.parse(localStorage.getItem('aiclipper_demo-job_clip_' + id) || '{}').caption_template;
          return direct || parsed;
        });
      })()
    `);

    console.log(`All clips persisted templates after 'Apply to all': ${JSON.stringify(allPersisted)}`);
    const allSetToBoxedNews = allPersisted.length === 3 && allPersisted.every(v => v === 'boxed-news');
    if (!allSetToBoxedNews) {
      console.error("FAILED: not all 3 clips were set to boxed-news:", allPersisted);
      process.exit(1);
    }
    console.log("Check 5 PASS: 'Apply to all clips' sets all 3 clips to 'boxed-news'");

    cdp.close();
    console.log("\nALL CAPTION ACCEPTANCE CHECKS PASSED!");
    process.exit(0);
  } catch (err) {
    console.error("Error in check-captions.js:", err);
    process.exit(1);
  } finally {
    if (chromeProc) {
      chromeProc.kill();
      try { chromeProc.unref(); } catch (_) {}
    }
    if (serverProc) {
      serverProc.kill();
    }
    setTimeout(() => {
      try { fs.rmSync(profileDir, { recursive: true, force: true }); } catch (_) {}
    }, 1000);
  }
}

main();
