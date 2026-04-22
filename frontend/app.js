/* ═══════════════════════════════════════════════════════════════════
   KnowledgeAI – Frontend JavaScript
   ═══════════════════════════════════════════════════════════════════ */

const API = "http://localhost:5000/api";

/* ── State ────────────────────────────────────────────────────────── */
const state = {
  activeFilter: "",      // "" | "pdf" | "gmail" | "notion"
  isLoading: false,
  chatHistory: [],       // [{role, content}]
};

/* ── Element refs ─────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const qsa = sel => document.querySelectorAll(sel);

const els = {
  sidebar:       $("sidebar"),
  sidebarToggle: $("sidebarToggle"),
  statsTotal:    $("statTotal"),
  statsPdf:      $("statPdf"),
  statsGmail:    $("statGmail"),
  statsNotion:   $("statNotion"),
  uploadZone:    $("uploadZone"),
  fileInput:     $("fileInput"),
  uploadBrowse:  $("uploadBrowse"),
  uploadProgress:$("uploadProgress"),
  progressFill:  $("progressFill"),
  progressLabel: $("progressLabel"),
  uploadedFiles: $("uploadedFiles"),
  filterPills:   qsa(".pill"),
  statusDot:     $("statusDot"),
  clearChatBtn:  $("clearChatBtn"),
  refreshBtn:    $("refreshStatsBtn"),
  chatWindow:    $("chatWindow"),
  welcomeScreen: $("welcomeScreen"),
  messages:      $("messages"),
  queryInput:    $("queryInput"),
  sendBtn:       $("sendBtn"),
  charCount:     $("charCount"),
  activeFilter:  $("activeFilter"),
  toastContainer:$("toastContainer"),
};

/* ════════════════════════════════════════════
   UTILITIES
   ════════════════════════════════════════════ */

function toast(msg, type = "info", duration = 4000) {
  const icons = { success: "✅", error: "❌", info: "ℹ️" };
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span class="toast-icon">${icons[type] ?? "ℹ️"}</span>
                 <span class="toast-msg">${msg}</span>`;
  els.toastContainer.appendChild(t);
  setTimeout(() => {
    t.style.animation = "toastOut 0.3s ease forwards";
    setTimeout(() => t.remove(), 300);
  }, duration);
}

function setLoading(loading) {
  state.isLoading = loading;
  els.sendBtn.disabled = loading;
  els.queryInput.disabled = loading;
}

function hideWelcome() {
  if (!els.welcomeScreen.classList.contains("hidden")) {
    els.welcomeScreen.classList.add("hidden");
  }
}

function scrollChatToBottom() {
  requestAnimationFrame(() => {
    els.chatWindow.scrollTop = els.chatWindow.scrollHeight;
  });
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatAnswer(text) {
  // Basic markdown-like formatting
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, `<code style="font-family:'JetBrains Mono',monospace;font-size:0.85em;background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;">$1</code>`)
    .replace(/\[(\d+)\]/g, `<span style="color:var(--accent-1);font-weight:600;">[$1]</span>`)
    .replace(/\n/g, "<br>");
}

/* ════════════════════════════════════════════
   STATS
   ════════════════════════════════════════════ */

async function fetchStats() {
  try {
    const res = await fetch(`${API}/stats`);
    if (!res.ok) throw new Error("Stats fetch failed");
    const data = await res.json();
    const by = data.by_source ?? {};
    els.statsTotal.textContent  = data.total ?? 0;
    els.statsPdf.textContent    = by.pdf    ?? 0;
    els.statsGmail.textContent  = by.gmail  ?? 0;
    els.statsNotion.textContent = by.notion ?? 0;
  } catch {
    // silently fail – server may not be up yet
  }
}

async function checkHealth() {
  try {
    const res = await fetch(`${API}/health`);
    if (res.ok) {
      els.statusDot.className = "status-dot ok";
      els.statusDot.title = "Server online";
    } else throw new Error();
  } catch {
    els.statusDot.className = "status-dot error";
    els.statusDot.title = "Server offline";
  }
}

/* ════════════════════════════════════════════
   UPLOAD
   ════════════════════════════════════════════ */

function showProgress(label, pct) {
  els.uploadProgress.classList.remove("hidden");
  els.progressFill.style.width = `${pct}%`;
  els.progressLabel.textContent = label;
}

function hideProgress() {
  els.uploadProgress.classList.add("hidden");
  els.progressFill.style.width = "0%";
}

function addFileChip(name, chunks) {
  const chip = document.createElement("div");
  chip.className = "file-chip";
  chip.innerHTML = `
    <span class="fc-icon">📄</span>
    <span class="fc-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
    <span class="fc-chunks">+${chunks}</span>
  `;
  els.uploadedFiles.prepend(chip);
}

async function uploadFile(file) {
  if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
    toast("Please select a PDF file.", "error");
    return;
  }

  showProgress("Uploading…", 20);
  const formData = new FormData();
  formData.append("file", file);

  try {
    showProgress("Processing & embedding…", 60);
    const res = await fetch(`${API}/upload`, { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok || data.error) {
      toast(data.error ?? "Upload failed", "error");
      hideProgress();
      return;
    }

    showProgress("Done!", 100);
    setTimeout(hideProgress, 1000);

    addFileChip(data.file_name, data.chunks_added);
    toast(`✨ Added ${data.chunks_added} chunks from "${data.file_name}"`, "success");
    fetchStats();

  } catch (err) {
    toast("Network error during upload.", "error");
    hideProgress();
  }
}

/* ════════════════════════════════════════════
   CHAT
   ════════════════════════════════════════════ */

function appendMessage(role, content, citations = null) {
  hideWelcome();

  const msgEl = document.createElement("div");
  msgEl.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "msg-label";
  label.textContent = role === "user" ? "You" : "Assistant";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = role === "user" ? escapeHtml(content) : formatAnswer(content);

  msgEl.appendChild(label);
  msgEl.appendChild(bubble);

  if (citations && citations.length > 0) {
    const citSection = buildCitationsEl(citations);
    msgEl.appendChild(citSection);
  }

  els.messages.appendChild(msgEl);
  scrollChatToBottom();
  return msgEl;
}

function buildCitationsEl(citations) {
  const section = document.createElement("div");
  section.className = "citations-section";

  const header = document.createElement("div");
  header.className = "citations-header";
  header.textContent = `📎 Sources (${citations.length})`;
  section.appendChild(header);

  citations.forEach(cit => {
    const card = document.createElement("div");
    card.className = "citation-card";
    card.title = "Click to see excerpt";

    const sourceCls = `source-${cit.source}`;

    card.innerHTML = `
      <div class="citation-top">
        <span class="citation-index">[${cit.index}]</span>
        <span class="citation-source-badge ${sourceCls}">${cit.source}</span>
        <span class="citation-label">${escapeHtml(cit.citation)}</span>
        <span class="citation-score">${cit.score.toFixed(3)}</span>
      </div>
      <div class="citation-excerpt">${escapeHtml(cit.excerpt)}</div>
    `;

    // Toggle full excerpt on click
    let expanded = false;
    card.addEventListener("click", () => {
      expanded = !expanded;
      card.querySelector(".citation-excerpt").style["-webkit-line-clamp"] = expanded ? "unset" : "2";
    });

    section.appendChild(card);
  });

  return section;
}

function appendThinking() {
  hideWelcome();
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";
  wrapper.id = "thinkingMsg";

  const label = document.createElement("div");
  label.className = "msg-label";
  label.textContent = "Assistant";

  const thinking = document.createElement("div");
  thinking.className = "thinking";
  thinking.innerHTML = `
    <div class="thinking-dot"></div>
    <div class="thinking-dot"></div>
    <div class="thinking-dot"></div>
  `;

  wrapper.appendChild(label);
  wrapper.appendChild(thinking);
  els.messages.appendChild(wrapper);
  scrollChatToBottom();
  return wrapper;
}

async function sendQuery() {
  const query = els.queryInput.value.trim();
  if (!query || state.isLoading) return;

  setLoading(true);
  appendMessage("user", query);
  els.queryInput.value = "";
  els.charCount.textContent = "0 / 2000";
  autoResize();

  const thinkingEl = appendThinking();

  const body = { query, top_k: 5 };
  if (state.activeFilter) body.filters = { source: state.activeFilter };

  try {
    const res = await fetch(`${API}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    thinkingEl.remove();

    if (data.error) {
      appendMessage("assistant", `⚠️ Error: ${data.error}`);
      toast(data.error, "error");
    } else {
      appendMessage("assistant", data.answer, data.citations);
    }
  } catch (err) {
    thinkingEl.remove();
    appendMessage("assistant", "⚠️ Could not reach the server. Is Flask running?");
    toast("Network error", "error");
  } finally {
    setLoading(false);
    scrollChatToBottom();
  }
}

/* ════════════════════════════════════════════
   INIT & EVENT LISTENERS
   ════════════════════════════════════════════ */

function autoResize() {
  const ta = els.queryInput;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
}

function initEventListeners() {

  // Sidebar toggle
  els.sidebarToggle.addEventListener("click", () => {
    els.sidebar.classList.toggle("collapsed");
  });

  // Upload zone drag & drop
  els.uploadZone.addEventListener("click", () => els.fileInput.click());
  els.uploadBrowse.addEventListener("click", e => { e.stopPropagation(); els.fileInput.click(); });

  els.uploadZone.addEventListener("dragover", e => {
    e.preventDefault();
    els.uploadZone.classList.add("dragover");
  });
  els.uploadZone.addEventListener("dragleave", () => els.uploadZone.classList.remove("dragover"));
  els.uploadZone.addEventListener("drop", e => {
    e.preventDefault();
    els.uploadZone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  els.fileInput.addEventListener("change", () => {
    const file = els.fileInput.files[0];
    if (file) { uploadFile(file); els.fileInput.value = ""; }
  });

  // Filter pills
  qsa(".pill").forEach(pill => {
    pill.addEventListener("click", () => {
      qsa(".pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.dataset.source;
      els.activeFilter.textContent = state.activeFilter
        ? `Filtering: ${state.activeFilter}`
        : "";
    });
  });

  // Send / Enter
  els.sendBtn.addEventListener("click", sendQuery);
  els.queryInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });

  // Char count & auto-resize
  els.queryInput.addEventListener("input", () => {
    const len = els.queryInput.value.length;
    els.charCount.textContent = `${len} / 2000`;
    autoResize();
  });

  // Suggestion chips
  qsa(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      els.queryInput.value = chip.dataset.query;
      autoResize();
      sendQuery();
    });
  });

  // Clear chat
  els.clearChatBtn.addEventListener("click", () => {
    els.messages.innerHTML = "";
    els.welcomeScreen.classList.remove("hidden");
    state.chatHistory = [];
  });

  // Refresh stats
  els.refreshBtn.addEventListener("click", () => {
    fetchStats();
    checkHealth();
    toast("Stats refreshed", "info", 2000);
  });
}

// Boot
initEventListeners();
checkHealth();
fetchStats();
setInterval(fetchStats, 30_000);   // refresh stats every 30 s
