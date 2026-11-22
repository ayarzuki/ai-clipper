// AI Clipper - Dashboard Frontend JS

function showToast(message, duration = 3500) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--cyan-accent); flex-shrink: 0;">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="16" x2="12" y2="12"></line>
      <line x1="12" y1="8" x2="12.01" y2="8"></line>
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

const STAGES = ["Ingest", "ASR", "Normalize", "Select", "Render", "Package"];

function renderStageDots(stages = {}) {
  return STAGES.map(stage => {
    const key = stage.toLowerCase();
    const status = (stages[key] || "pending").toLowerCase();
    let dotClass = "pending";
    if (status === "done") dotClass = "done";
    else if (status === "running") dotClass = "running";
    else if (status === "failed") dotClass = "failed";
    return `<span class="mini-dot ${dotClass}" title="${stage}: ${status}"></span>`;
  }).join("");
}

function getStatusChip(status = "done") {
  const s = status.toLowerCase();
  let chipClass = "chip-queued";
  if (s === "done") chipClass = "chip-done";
  else if (s === "running") chipClass = "chip-running";
  else if (s === "failed") chipClass = "chip-failed";
  return `<span class="chip ${chipClass}">${s}</span>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

async function loadJobs() {
  const tbody = document.getElementById("jobs-tbody");
  const emptyState = document.getElementById("empty-state");
  try {
    const res = await fetch("/api/jobs");
    if (!res.ok) throw new Error("Failed to fetch jobs");
    const data = await res.json();
    const jobs = data.jobs || [];

    if (jobs.length === 0) {
      if (emptyState) emptyState.style.display = "block";
      if (tbody) tbody.innerHTML = "";
      return;
    }

    if (emptyState) emptyState.style.display = "none";
    if (!tbody) return;

    tbody.innerHTML = jobs.map(job => {
      const createdDate = job.created ? job.created.split("T")[0] : "—";
      const sourceEscaped = escapeHtml(job.source);
      return `
        <tr class="job-row" onclick="window.location.href='/job.html?id=${encodeURIComponent(job.job_id)}'">
          <td><span style="color: var(--cyan-accent); font-weight: 600;">${job.job_id}</span></td>
          <td class="col-source" title="${sourceEscaped}">${sourceEscaped}</td>
          <td>${getStatusChip(job.status)}</td>
          <td>${job.clip_count} ${job.clip_count === 1 ? 'clip' : 'clips'}</td>
          <td>${createdDate}</td>
          <td>
            <div class="mini-stepper">
              ${renderStageDots(job.stages)}
            </div>
          </td>
          <td>
            <a href="/job.html?id=${encodeURIComponent(job.job_id)}" class="btn btn-outline btn-sm" onclick="event.stopPropagation()">View Clips →</a>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading jobs:", err);
  }
}

async function loadGallery() {
  const grid = document.getElementById("gallery-grid");
  if (!grid) return;

  try {
    const res = await fetch("/api/caption-templates");
    if (!res.ok) return;
    const templates = await res.json();
    const defaultTpl = localStorage.getItem("caption_template_default") || "karaoke-classic";

    grid.innerHTML = templates.map(tpl => {
      const isDefault = tpl.id === defaultTpl;
      const words = tpl.sample_text.split(" ");
      const sampleHtml = words.map((w, idx) => `<span class="caption-word ${idx === 0 ? 'active' : ''}">${escapeHtml(w)}</span>`).join(" ");

      return `
        <div class="gallery-card ${isDefault ? 'default-preset' : ''}" data-template-id="${tpl.id}">
          <div class="gallery-card-header">
            <span class="gallery-card-title">${escapeHtml(tpl.name)}</span>
            <span class="chip ${isDefault ? 'chip-done' : 'chip-queued'} default-tag">
              ${isDefault ? 'Default' : 'Set as default'}
            </span>
          </div>
          <div class="gallery-sample-box ${tpl.css_class}">
            <span class="caption-text">${sampleHtml}</span>
          </div>
        </div>
      `;
    }).join("");

    // Attach click listeners to set global default
    grid.querySelectorAll(".gallery-card").forEach(card => {
      card.addEventListener("click", () => {
        const tplId = card.getAttribute("data-template-id");
        localStorage.setItem("caption_template_default", tplId);
        localStorage.setItem("default_caption_template", tplId);
        showToast(`Default caption style set to "${tplId}"`);
        loadGallery();
      });
    });
  } catch (err) {
    console.warn("Could not load caption templates gallery:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Target length slider
  const rangeInput = document.getElementById("target_len_s");
  const rangeVal = document.getElementById("target-len-val");
  if (rangeInput && rangeVal) {
    rangeInput.addEventListener("input", (e) => {
      rangeVal.textContent = `${e.target.value}s`;
    });
  }

  // Form submission
  const form = document.getElementById("new-job-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const urlOrPath = document.getElementById("url_or_path").value.trim();
      const language = document.getElementById("language").value;
      const targetLen = parseInt(document.getElementById("target_len_s").value, 10);
      const maxClips = parseInt(document.getElementById("max_clips").value, 10);

      const mode = document.getElementById("mode") ? document.getElementById("mode").value : "fake";

      const submitBtn = document.getElementById("start-btn");
      if (submitBtn) submitBtn.disabled = true;

      try {
        const res = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url_or_path: urlOrPath,
            language: language,
            target_len_s: targetLen,
            max_clips: maxClips,
            mode: mode
          })
        });

        if (res.status === 201) {
          const data = await res.json();
          showToast(`Job started: ${data.job_id}`);
          setTimeout(() => {
            window.location.href = `/job.html?id=${encodeURIComponent(data.job_id)}`;
          }, 400);
        } else if (res.status === 409) {
          const data = await res.json();
          showToast(`Another job is already running — ${data.job_id}`);
        } else {
          const data = await res.json().catch(() => ({}));
          showToast(data.error || "Failed to create job");
        }
      } catch (err) {
        showToast("Error connecting to server");
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  loadJobs();
  loadGallery();
  // Poll jobs list every 2s
  setInterval(loadJobs, 2000);
});
