// AI Clipper - Job Detail Frontend JS

const DEFAULT_TEMPLATES = [
  { id: "bold-pop", name: "Bold Pop", sample_text: "STOP building messy pipelines", css_class: "tpl-bold-pop" },
  { id: "karaoke-classic", name: "Karaoke Classic", sample_text: "Never mutate your raw incoming stream", css_class: "tpl-karaoke-classic" },
  { id: "neon-glow", name: "Neon Glow", sample_text: "CYAN GLOW ON PRODUCTION PIPELINES", css_class: "tpl-neon-glow" },
  { id: "minimal-clean", name: "Minimal Clean", sample_text: "decouple storage format from compute engine", css_class: "tpl-minimal-clean" },
  { id: "hype-emoji", name: "Hype Emoji", sample_text: "🔥 EVERY SINGLE TRANSFORMATION DAG", css_class: "tpl-hype-emoji" },
  { id: "typewriter", name: "Typewriter", sample_text: "Idempotent", css_class: "tpl-typewriter" },
  { id: "boxed-news", name: "Boxed News", sample_text: "BREAKING: ROUTE POISON RECORDS NOW", css_class: "tpl-boxed-news" },
  { id: "gradient-influencer", name: "Gradient Influencer", sample_text: "survive any massive scale spike", css_class: "tpl-gradient-influencer" }
];

let captionTemplates = [...DEFAULT_TEMPLATES];
const activeAnimTimers = new Map();

function showToast(message, duration = 3000) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--cyan-accent); flex-shrink: 0;">
      <circle cx="12" cy="12" r="10"></circle>
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

function countWords(str) {
  if (!str) return 0;
  return str.trim().split(/\s+/).filter(Boolean).length;
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m > 0) {
    return `${m}m ${s}s (${Math.round(seconds)}s)`;
  }
  return `${Math.round(seconds)}s`;
}

function formatTimeHHMMSS(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return `[${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}]`;
}

const STAGES = ["Ingest", "ASR", "Normalize", "Select", "Render", "Package"];

function renderStageStepper(stages = {}) {
  const container = document.getElementById("stage-stepper");
  if (!container) return;

  container.innerHTML = STAGES.map((st, idx) => {
    const key = st.toLowerCase();
    const status = (stages[key] || "pending").toLowerCase();
    let stageClass = "stage-pending";
    let dotClass = "pending";

    if (status === "done") {
      stageClass = "stage-done";
      dotClass = "done";
    } else if (status === "running") {
      stageClass = "stage-running";
      dotClass = "running";
    } else if (status === "failed") {
      stageClass = "stage-failed";
      dotClass = "failed";
    }

    const stageTitle = `${idx + 1}. ${st}`;
    return `
      <div class="stepper-stage ${stageClass}">
        <span class="mini-dot ${dotClass}"></span>
        <div>
          <div class="stage-name">${stageTitle}</div>
          <div class="stage-status">${status}</div>
        </div>
      </div>
    `;
  }).join("");
}

function renderTranscript(transcript = []) {
  const container = document.getElementById("transcript-container");
  if (!container) return;
  if (!transcript || transcript.length === 0) {
    container.innerHTML = '<div class="empty-state">No transcript available.</div>';
    return;
  }
  container.innerHTML = transcript.map(item => `
    <div class="transcript-item">
      <span class="transcript-time">${formatTimeHHMMSS(item.start || 0)}</span>
      <span class="transcript-text">${escapeHtml(item.text || "")}</span>
    </div>
  `).join("");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function getStorageKey(jobId, clipId) {
  return `aiclipper_${jobId}_clip_${clipId}`;
}

function saveClipLocal(jobId, clipId, data) {
  try {
    const key = getStorageKey(jobId, clipId);
    const existing = JSON.parse(localStorage.getItem(key) || "{}");
    const updated = { ...existing, ...data };
    localStorage.setItem(key, JSON.stringify(updated));
  } catch (err) {
    console.warn("localStorage save failed:", err);
  }
}

function loadClipLocal(jobId, clipId) {
  try {
    const key = getStorageKey(jobId, clipId);
    return JSON.parse(localStorage.getItem(key) || "{}");
  } catch (err) {
    return {};
  }
}

function getPersistedTemplate(jobId, clipId, defaultFromJob = "karaoke-classic") {
  const directKey = localStorage.getItem(`clip.${clipId}.caption_template`);
  if (directKey) return directKey;

  const local = loadClipLocal(jobId, clipId);
  if (local.caption_template) return local.caption_template;

  const globalDef = localStorage.getItem("caption_template_default");
  if (globalDef) return globalDef;

  return defaultFromJob || "karaoke-classic";
}

function startCaptionCycle(clipId, template, textOverride = null) {
  if (activeAnimTimers.has(clipId)) {
    clearInterval(activeAnimTimers.get(clipId));
    activeAnimTimers.delete(clipId);
  }

  const overlay = document.getElementById(`caption-overlay-${clipId}`);
  if (!overlay || !template) return;

  const rawText = textOverride || template.sample_text || "";
  const words = rawText.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return;

  let currentIdx = 0;

  function renderStep(idx) {
    overlay.className = `caption-overlay ${template.css_class}`;
    const wordSpans = words.map((w, i) => {
      const activeClass = i === idx ? 'active' : '';
      return `<span class="caption-word ${activeClass}">${escapeHtml(w)}</span>`;
    }).join(" ");
    overlay.innerHTML = `<span class="caption-text">${wordSpans}</span>`;
  }

  // Render initial frame immediately (ensures full sample text is present in DOM)
  renderStep(0);

  // Cycle active word every 400ms
  const timer = setInterval(() => {
    currentIdx = (currentIdx + 1) % words.length;
    renderStep(currentIdx);
  }, 400);

  activeAnimTimers.set(clipId, timer);
}

function selectTemplateForClip(jobId, clipId, templateId) {
  const template = captionTemplates.find(t => t.id === templateId) || captionTemplates[0];

  // Update UI chips
  const chipsContainer = document.getElementById(`template-chips-${clipId}`);
  if (chipsContainer) {
    chipsContainer.querySelectorAll(".tpl-chip").forEach(btn => {
      if (btn.getAttribute("data-template-id") === templateId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  // Update active template label
  const label = document.getElementById(`active-tpl-label-${clipId}`);
  if (label) label.textContent = template.name;

  // Persist template choice
  localStorage.setItem(`clip.${clipId}.caption_template`, templateId);
  localStorage.setItem(`caption_template_clip_${clipId}`, templateId);
  saveClipLocal(jobId, clipId, { caption_template: templateId });

  // Update overlay and restart cycle
  startCaptionCycle(clipId, template);
}

function renderClips(jobId, clips = []) {
  const grid = document.getElementById("clip-grid");
  if (!grid) return;

  if (!clips || clips.length === 0) {
    grid.innerHTML = '<div class="empty-state">No clips found for this job.</div>';
    return;
  }

  grid.innerHTML = clips.map(clip => {
    const clipId = clip.id;
    const local = loadClipLocal(jobId, clipId);

    const title = local.title !== undefined ? local.title : (clip.title || `Clip ${clipId}`);
    const hook = local.hook !== undefined ? local.hook : (clip.hook || "");
    const caption = local.caption !== undefined ? local.caption : (clip.caption || "");
    const hashtags = local.hashtags !== undefined ? local.hashtags : (Array.isArray(clip.hashtags) ? clip.hashtags.join(", ") : (clip.hashtags || ""));

    const score = clip.virality_score !== undefined ? clip.virality_score : (clip.score || 50);
    let viralityClass = "virality-low";
    if (score >= 80) viralityClass = "virality-high";
    else if (score >= 50) viralityClass = "virality-med";

    const duration = clip.duration || (clip.end - clip.start) || 0;
    let durClass = "duration-emerald";
    let warningBanner = "";

    if (duration >= 20 && duration <= 59) {
      durClass = "duration-emerald";
    } else if (duration > 59 && duration <= 180) {
      durClass = "duration-amber";
      warningBanner = `<div class="warning-banner warning-amber">⚠️ Duration warning: ${duration}s exceeds recommended &lt;60s limit</div>`;
    } else {
      durClass = "duration-rose";
      if (duration < 20) {
        warningBanner = `<div class="warning-banner warning-rose">⚠️ Duration warning: ${duration}s is too short (min recommended 20s)</div>`;
      } else {
        warningBanner = `<div class="warning-banner warning-rose">⚠️ Duration warning: ${duration}s is too short (min recommended 20s)</div>`;
      }
    }

    const wordCount = countWords(hook);
    const exceeded = wordCount > 7;

    const hashtagsArray = hashtags.split(",").map(t => t.trim()).filter(Boolean);
    const hashtagChips = hashtagsArray.map(tag => `<span class="hashtag-pill">${escapeHtml(tag)}</span>`).join("");

    const activeTplId = getPersistedTemplate(jobId, clipId, clip.caption_template);
    const activeTpl = captionTemplates.find(t => t.id === activeTplId) || captionTemplates[1];

    const chipsHtml = captionTemplates.map(tpl => {
      const isActive = tpl.id === activeTpl.id;
      return `<button type="button" class="tpl-chip ${isActive ? 'active' : ''}" data-template-id="${tpl.id}" data-clip-id="${clipId}">${escapeHtml(tpl.name)}</button>`;
    }).join("");

    return `
      <div class="clip-card" data-clip-id="${clipId}">
        <div class="preview-container">
          <div class="preview-9-16">
            <span class="preview-mock-tag">9:16 Mock</span>
            <div class="preview-hook-text" id="preview-hook-${clipId}">${escapeHtml(hook)}</div>
            <div class="caption-overlay ${activeTpl.css_class}" id="caption-overlay-${clipId}">
              <span class="caption-text">${escapeHtml(activeTpl.sample_text)}</span>
            </div>
          </div>
        </div>

        <div class="badge-row">
          <span class="virality-pill ${viralityClass}">★ ${score}</span>
          <span class="duration-chip ${durClass}">⏱ ${duration}s</span>
        </div>

        <div class="warning-slot">
          ${warningBanner}
        </div>

        <div class="clip-form">
          <div class="form-group">
            <label for="title-${clipId}">Title</label>
            <input type="text" id="title-${clipId}" class="clip-title-input" data-clip-id="${clipId}" value="${escapeHtml(title)}">
          </div>

          <div class="form-group">
            <div class="field-label-row">
              <label for="hook-${clipId}">Hook (Max 7 words)</label>
              <span class="word-counter ${exceeded ? 'exceeded' : ''}" id="hook-count-${clipId}">${wordCount}/7 words</span>
            </div>
            <input type="text" id="hook-${clipId}" class="hook-input ${exceeded ? 'exceeded' : ''}" data-clip-id="${clipId}" value="${escapeHtml(hook)}">
          </div>

          <div class="form-group">
            <label for="caption-${clipId}">Caption</label>
            <textarea id="caption-${clipId}" rows="3" class="clip-caption-input" data-clip-id="${clipId}">${escapeHtml(caption)}</textarea>
          </div>

          <div class="form-group">
            <label for="hashtags-${clipId}">Hashtags</label>
            <input type="text" id="hashtags-${clipId}" class="clip-hashtags-input" data-clip-id="${clipId}" value="${escapeHtml(hashtags)}">
            <div class="hashtags-container" id="hashtag-chips-${clipId}">
              ${hashtagChips}
            </div>
          </div>

          <!-- Caption Style Presets Picker -->
          <div class="caption-style-section">
            <div class="field-label-row">
              <label>Caption Style Preset</label>
              <span class="active-tpl-label" id="active-tpl-label-${clipId}" style="font-size: 11px; color: var(--cyan-accent); font-weight: 600;">${escapeHtml(activeTpl.name)}</span>
            </div>
            <div class="template-chips-scroll" id="template-chips-${clipId}">
              ${chipsHtml}
            </div>
            <div class="caption-btn-row">
              <button type="button" class="btn btn-outline btn-sm apply-all-btn" data-clip-id="${clipId}">Apply to all clips</button>
              <button type="button" class="btn btn-outline btn-sm preview-cap-btn" data-clip-id="${clipId}">Preview caption</button>
            </div>
          </div>
        </div>

        <div class="card-actions">
          <div class="tooltip-wrapper">
            <button type="button" class="btn btn-outline btn-sm" disabled style="width: 100%;">
              Download MP4
            </button>
            <span class="tooltip-text">Mock mode: render pipeline not wired</span>
          </div>
          <a href="/api/jobs/${encodeURIComponent(jobId)}/srt/${clipId}" download="clip_${clipId}.srt" class="btn btn-outline btn-sm">
            Download SRT
          </a>
          <button type="button" class="btn btn-primary btn-sm copy-btn" data-clip-id="${clipId}">
            Copy caption
          </button>
        </div>
      </div>
    `;
  }).join("");

  attachListeners(jobId, clips);

  // Initialize caption animations for each clip
  clips.forEach(clip => {
    const activeTplId = getPersistedTemplate(jobId, clip.id, clip.caption_template);
    const activeTpl = captionTemplates.find(t => t.id === activeTplId) || captionTemplates[1];
    startCaptionCycle(clip.id, activeTpl);
  });
}

function attachListeners(jobId, clips = []) {
  // Title input
  document.querySelectorAll(".clip-title-input").forEach(input => {
    input.addEventListener("input", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      saveClipLocal(jobId, clipId, { title: e.target.value });
    });
  });

  // Hook input with max 7 words warning & preview update
  document.querySelectorAll(".hook-input").forEach(input => {
    input.addEventListener("input", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const val = e.target.value;
      const count = countWords(val);
      const counter = document.getElementById(`hook-count-${clipId}`);
      const previewHook = document.getElementById(`preview-hook-${clipId}`);

      if (previewHook) previewHook.textContent = val;

      if (counter) {
        counter.textContent = `${count}/7 words`;
        if (count > 7) {
          counter.classList.add("exceeded");
          e.target.classList.add("exceeded");
        } else {
          counter.classList.remove("exceeded");
          e.target.classList.remove("exceeded");
        }
      }

      saveClipLocal(jobId, clipId, { hook: val });
    });
  });

  // Caption input
  document.querySelectorAll(".clip-caption-input").forEach(textarea => {
    textarea.addEventListener("input", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      saveClipLocal(jobId, clipId, { caption: e.target.value });
    });
  });

  // Hashtags input
  document.querySelectorAll(".clip-hashtags-input").forEach(input => {
    input.addEventListener("input", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const val = e.target.value;
      const container = document.getElementById(`hashtag-chips-${clipId}`);
      if (container) {
        const tags = val.split(",").map(t => t.trim()).filter(Boolean);
        container.innerHTML = tags.map(tag => `<span class="hashtag-pill">${escapeHtml(tag)}</span>`).join("");
      }
      saveClipLocal(jobId, clipId, { hashtags: val });
    });
  });

  // Copy caption button
  document.querySelectorAll(".copy-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const captionEl = document.getElementById(`caption-${clipId}`);
      const hashtagsEl = document.getElementById(`hashtags-${clipId}`);
      const captionText = captionEl ? captionEl.value.trim() : "";
      const hashtagsText = hashtagsEl ? hashtagsEl.value.trim() : "";

      const fullText = hashtagsText ? `${captionText}\n\n${hashtagsText}` : captionText;

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(fullText).then(() => {
          showToast("Caption copied to clipboard!");
        }).catch(() => {
          fallbackCopy(fullText);
        });
      } else {
        fallbackCopy(fullText);
      }
    });
  });

  // Template chip click
  document.querySelectorAll(".tpl-chip").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const templateId = e.target.getAttribute("data-template-id");
      selectTemplateForClip(jobId, clipId, templateId);
    });
  });

  // Apply to all clips button
  document.querySelectorAll(".apply-all-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const activeTplId = getPersistedTemplate(jobId, clipId);
      const template = captionTemplates.find(t => t.id === activeTplId) || captionTemplates[0];

      // Query all clips present
      const allCards = document.querySelectorAll(".clip-card");
      allCards.forEach(card => {
        const cId = card.getAttribute("data-clip-id");
        selectTemplateForClip(jobId, cId, activeTplId);
      });

      showToast(`Applied "${template.name}" caption style to all clips`);
    });
  });

  // Preview caption button (replays word cycle with hook or sample text)
  document.querySelectorAll(".preview-cap-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const clipId = e.target.getAttribute("data-clip-id");
      const activeTplId = getPersistedTemplate(jobId, clipId);
      const template = captionTemplates.find(t => t.id === activeTplId) || captionTemplates[0];

      const hookInput = document.getElementById(`hook-${clipId}`);
      const hookText = hookInput ? hookInput.value.trim() : "";
      const cycleText = hookText || template.sample_text;

      startCaptionCycle(clipId, template, cycleText);
      showToast(`Playing caption preview: ${template.name}`);
    });
  });
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    showToast("Caption copied to clipboard!");
  } catch (err) {
    showToast("Failed to copy caption");
  }
  document.body.removeChild(ta);
}

let jobPollTimer = null;

async function loadJobDetail() {
  const urlParams = new URLSearchParams(window.location.search);
  const jobId = urlParams.get("id") || "demo-job";

  try {
    // Try to load caption templates from server first
    try {
      const tplRes = await fetch("/api/caption-templates");
      if (tplRes.ok) {
        const fetchedTpls = await tplRes.json();
        if (Array.isArray(fetchedTpls) && fetchedTpls.length === 8) {
          captionTemplates = fetchedTpls;
        }
      }
    } catch (_) {}

    const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (!res.ok) {
      showToast(`Job "${jobId}" not found`);
      return;
    }

    const job = await res.json();

    const idBadge = document.getElementById("job-id-badge");
    if (idBadge) idBadge.textContent = job.job_id;

    const sourceTitle = document.getElementById("job-source-title");
    if (sourceTitle) sourceTitle.textContent = job.source;

    const durLine = document.getElementById("job-duration-line");
    if (durLine) {
      const durText = formatDuration(job.duration_s || 0);
      const clipCount = (job.clips || []).length;
      durLine.textContent = `Source Duration: ~${durText} • ${clipCount} candidate clips generated`;
    }

    // Error banner for failed jobs
    const errorBanner = document.getElementById("job-error-banner");
    if (errorBanner) {
      if (job.status === "failed" && job.error) {
        errorBanner.style.display = "block";
        errorBanner.textContent = job.error;
      } else {
        errorBanner.style.display = "none";
      }
    }

    renderStageStepper(job.stages || {});
    renderTranscript(job.transcript || []);

    const clipGrid = document.getElementById("clip-grid");
    if (job.clips && job.clips.length > 0) {
      renderClips(job.job_id, job.clips);
    } else if (job.status === "queued" || job.status === "running") {
      if (clipGrid) {
        clipGrid.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1; padding: 48px 24px; text-align: center; color: var(--text-muted);">
            <p>Job is ${job.status}... Candidate clips will appear here once rendering is complete.</p>
          </div>
        `;
      }
    } else {
      if (clipGrid) {
        clipGrid.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1; padding: 48px 24px; text-align: center; color: var(--text-muted);">
            <p>No clips generated.</p>
          </div>
        `;
      }
    }

    // Polling control: poll every 2s while queued/running
    if (job.status === "queued" || job.status === "running") {
      if (!jobPollTimer) {
        jobPollTimer = setInterval(loadJobDetail, 2000);
      }
    } else {
      if (jobPollTimer) {
        clearInterval(jobPollTimer);
        jobPollTimer = null;
      }
    }
  } catch (err) {
    console.error("Error loading job details:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const jobId = urlParams.get("id") || "demo-job";
  
  // Attach listeners to static HTML fallback if present
  attachListeners(jobId, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  loadJobDetail();
});
