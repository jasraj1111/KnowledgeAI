const API = "http://localhost:5000/api";

const state = {
  activeFilter: "",
  isLoading: false,
  chatHistory: [],
};

const $ = id => document.getElementById(id);
const qsa = sel => document.querySelectorAll(sel);

const els = {
  sidebar: $("sidebar"),
  sidebarToggle: $("sidebarToggle"),
  statsTotal: $("statTotal"),
  statsPdf: $("statPdf"),
  statsGmail: $("statGmail"),
  statsNotion: $("statNotion"),
  uploadZone: $("uploadZone"),
  fileInput: $("fileInput"),
  uploadBrowse: $("uploadBrowse"),
  uploadProgress: $("uploadProgress"),
  progressFill: $("progressFill"),
  progressLabel: $("progressLabel"),
  uploadedFiles: $("uploadedFiles"),
  statusDot: $("statusDot"),
  clearChatBtn: $("clearChatBtn"),
  refreshBtn: $("refreshStatsBtn"),
  chatWindow: $("chatWindow"),
  welcomeScreen: $("welcomeScreen"),
  messages: $("messages"),
  queryInput: $("queryInput"),
  sendBtn: $("sendBtn"),
  charCount: $("charCount"),
  activeFilter: $("activeFilter"),
  toastContainer: $("toastContainer"),
  // Gmail
  gmailAuthPanel: $("gmailAuthPanel"),
  gmailSyncPanel: $("gmailSyncPanel"),
  gmailAuthBtn: $("gmailAuthBtn"),
  gmailSyncBtn: $("gmailSyncBtn"),
  gmailStatusText: $("gmailStatusText"),
  gmailSyncProgress: $("gmailSyncProgress"),
  gmailProgressFill: $("gmailProgressFill"),
  gmailProgressLabel: $("gmailProgressLabel"),
  gmailSyncInfo: $("gmailSyncInfo"),
};

function toast(msg, type = "info", duration = 4000) {
  const icons = { success: "OK", error: "!", info: "i" };
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span class="toast-icon">${icons[type] ?? "i"}</span>
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

function updateSidebarToggleLabel() {
  const collapsed = els.sidebar.classList.contains("collapsed");
  els.sidebarToggle.textContent = collapsed ? "Open" : "Menu";
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
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, `<code style="font-family:'JetBrains Mono',monospace;font-size:0.85em;background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;">$1</code>`)
    .replace(/\[(\d+)\]/g, `<span style="color:var(--accent-3);font-weight:700;">[$1]</span>`)
    .replace(/\n/g, "<br>");
}

async function fetchStats() {
  try {
    const res = await fetch(`${API}/stats`);
    if (!res.ok) throw new Error("Stats fetch failed");

    const data = await res.json();
    const by = data.by_source ?? {};
    els.statsTotal.textContent = data.total ?? 0;
    els.statsPdf.textContent = by.pdf ?? 0;
    els.statsGmail.textContent = by.gmail ?? 0;
    els.statsNotion.textContent = by.notion ?? 0;
  } catch {
    // Silently fail if the server is not available yet.
  }
}

async function checkHealth() {
  try {
    const res = await fetch(`${API}/health`);
    if (!res.ok) throw new Error("Health check failed");

    els.statusDot.className = "status-dot ok";
    els.statusDot.title = "Server online";
  } catch {
    els.statusDot.className = "status-dot error";
    els.statusDot.title = "Server offline";
  }
}

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
    <span class="fc-icon">PDF</span>
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

  showProgress("Uploading...", 20);

  const formData = new FormData();
  formData.append("file", file);

  try {
    showProgress("Processing and indexing...", 60);
    const res = await fetch(`${API}/upload`, { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok || data.error) {
      toast(data.error ?? "Upload failed", "error");
      hideProgress();
      return;
    }

    showProgress("Done", 100);
    setTimeout(hideProgress, 900);

    addFileChip(data.file_name, data.chunks_added);
    toast(`Added ${data.chunks_added} chunks from "${data.file_name}"`, "success");
    fetchStats();
  } catch {
    toast("Network error during upload.", "error");
    hideProgress();
  }
}

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
    msgEl.appendChild(buildCitationsEl(citations));
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
  header.textContent = `Sources (${citations.length})`;
  section.appendChild(header);

  citations.forEach(cit => {
    const card = document.createElement("div");
    card.className = "citation-card";
    card.title = "Click to expand excerpt";

    const sourceCls = `source-${cit.source}`;
    const score = Number.isFinite(cit.score) ? cit.score.toFixed(3) : "--";

    card.innerHTML = `
      <div class="citation-top">
        <span class="citation-index">[${cit.index}]</span>
        <span class="citation-source-badge ${sourceCls}">${cit.source}</span>
        <span class="citation-label">${escapeHtml(cit.citation)}</span>
        <span class="citation-score">${score}</span>
      </div>
      <div class="citation-excerpt">${escapeHtml(cit.excerpt)}</div>
    `;

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
  const body = { query, top_k: 5, stream: true };

  if (state.activeFilter) {
    body.filters = { source: state.activeFilter };
  }

  try {
    const res = await fetch(`${API}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const contentType = res.headers.get("content-type") || "";

    if (contentType.includes("text/event-stream")) {
      thinkingEl.remove();

      const msgEl = document.createElement("div");
      msgEl.className = "message assistant";

      const label = document.createElement("div");
      label.className = "msg-label";
      label.textContent = "Assistant";

      const bubble = document.createElement("div");
      bubble.className = "msg-bubble";

      msgEl.appendChild(label);
      msgEl.appendChild(bubble);
      els.messages.appendChild(msgEl);
      scrollChatToBottom();

      let fullAnswer = "";
      let citations = null;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);

            if (event.error) {
              bubble.innerHTML = formatAnswer(`Error: ${event.error}`);
              toast(event.error, "error");
              break;
            }

            if (event.token) {
              fullAnswer += event.token;
              bubble.innerHTML = formatAnswer(fullAnswer);
              scrollChatToBottom();
            }

            if (event.done && event.citations) {
              citations = event.citations;
            }
          } catch {
            // Skip malformed event payloads.
          }
        }
      }

      if (citations && citations.length > 0) {
        msgEl.appendChild(buildCitationsEl(citations));
        scrollChatToBottom();
      }
    } else {
      const data = await res.json();
      thinkingEl.remove();

      if (data.error) {
        appendMessage("assistant", `Error: ${data.error}`);
        toast(data.error, "error");
      } else {
        appendMessage("assistant", data.answer, data.citations);
      }
    }
  } catch {
    thinkingEl.remove();
    appendMessage("assistant", "Could not reach the server. Is Flask running?");
    toast("Network error", "error");
  } finally {
    setLoading(false);
    scrollChatToBottom();
  }
}

function autoResize() {
  const ta = els.queryInput;
  ta.style.height = "auto";
  ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
}

function initEventListeners() {
  els.sidebarToggle.addEventListener("click", () => {
    els.sidebar.classList.toggle("collapsed");
    updateSidebarToggleLabel();
  });

  els.uploadZone.addEventListener("click", () => els.fileInput.click());
  els.uploadBrowse.addEventListener("click", event => {
    event.stopPropagation();
    els.fileInput.click();
  });

  els.uploadZone.addEventListener("dragover", event => {
    event.preventDefault();
    els.uploadZone.classList.add("dragover");
  });

  els.uploadZone.addEventListener("dragleave", () => {
    els.uploadZone.classList.remove("dragover");
  });

  els.uploadZone.addEventListener("drop", event => {
    event.preventDefault();
    els.uploadZone.classList.remove("dragover");
    const file = event.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  els.fileInput.addEventListener("change", () => {
    const file = els.fileInput.files[0];
    if (file) {
      uploadFile(file);
      els.fileInput.value = "";
    }
  });

  qsa(".pill").forEach(pill => {
    pill.addEventListener("click", () => {
      qsa(".pill").forEach(node => node.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.dataset.source;
      els.activeFilter.textContent = state.activeFilter ? `Filter: ${state.activeFilter}` : "";
    });
  });

  els.sendBtn.addEventListener("click", sendQuery);
  els.queryInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendQuery();
    }
  });

  els.queryInput.addEventListener("input", () => {
    const len = els.queryInput.value.length;
    els.charCount.textContent = `${len} / 2000`;
    autoResize();
  });

  qsa(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      els.queryInput.value = chip.dataset.query;
      autoResize();
      sendQuery();
    });
  });

  els.clearChatBtn.addEventListener("click", () => {
    els.messages.innerHTML = "";
    els.welcomeScreen.classList.remove("hidden");
    state.chatHistory = [];
  });

  els.refreshBtn.addEventListener("click", () => {
    fetchStats();
    checkHealth();
    toast("Stats refreshed", "info", 2000);
  });

  // Gmail buttons
  if (els.gmailAuthBtn) {
    els.gmailAuthBtn.addEventListener("click", startGmailAuth);
  }
  if (els.gmailSyncBtn) {
    els.gmailSyncBtn.addEventListener("click", syncGmail);
  }
}

/* ════════════════════════════════════════════
   GMAIL
   ════════════════════════════════════════════ */

async function checkGmailAuth() {
  try {
    const res = await fetch(`${API}/gmail/status`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.authenticated) {
      els.gmailAuthPanel.classList.add("hidden");
      els.gmailSyncPanel.classList.remove("hidden");
    } else {
      els.gmailAuthPanel.classList.remove("hidden");
      els.gmailSyncPanel.classList.add("hidden");
    }
  } catch {
    // server may not be up yet
  }
}

async function startGmailAuth() {
  els.gmailAuthBtn.disabled = true;
  els.gmailAuthBtn.textContent = "Opening browser…";

  try {
    const res = await fetch(`${API}/gmail/auth`, { method: "POST" });
    const data = await res.json();

    if (data.success) {
      toast("Check your browser to authorise Gmail.", "info", 6000);
      // Poll for auth completion
      const poll = setInterval(async () => {
        const check = await fetch(`${API}/gmail/status`);
        const status = await check.json();
        if (status.authenticated) {
          clearInterval(poll);
          els.gmailAuthPanel.classList.add("hidden");
          els.gmailSyncPanel.classList.remove("hidden");
          toast("Gmail connected successfully!", "success");
        }
      }, 2000);
      // Stop polling after 2 minutes
      setTimeout(() => clearInterval(poll), 120_000);
    } else {
      toast(data.error || "Gmail auth failed", "error");
    }
  } catch {
    toast("Could not start Gmail auth.", "error");
  } finally {
    els.gmailAuthBtn.disabled = false;
    els.gmailAuthBtn.innerHTML = '<span class="gmail-btn-icon">📧</span> Connect Gmail';
  }
}

async function syncGmail() {
  els.gmailSyncBtn.disabled = true;
  els.gmailSyncProgress.classList.remove("hidden");
  els.gmailProgressFill.style.width = "30%";
  els.gmailProgressLabel.textContent = "Fetching emails…";

  try {
    els.gmailProgressFill.style.width = "50%";
    els.gmailProgressLabel.textContent = "Embedding & storing…";

    const res = await fetch(`${API}/gmail/sync`, { method: "POST" });
    const data = await res.json();

    if (data.success) {
      els.gmailProgressFill.style.width = "100%";
      els.gmailProgressLabel.textContent = "Done!";

      if (data.chunks_added > 0) {
        toast(`✨ Synced ${data.emails_processed} emails (${data.chunks_added} chunks)`, "success");
        els.gmailSyncInfo.textContent = `Last sync: ${data.emails_processed} emails, ${data.chunks_added} chunks`;
      } else {
        toast(data.message || "No new emails to sync.", "info");
        els.gmailSyncInfo.textContent = "All emails up to date";
      }

      fetchStats();
      setTimeout(() => els.gmailSyncProgress.classList.add("hidden"), 1500);
    } else {
      toast(data.error || "Sync failed", "error");
      els.gmailSyncProgress.classList.add("hidden");
    }
  } catch {
    toast("Gmail sync failed. Is the server running?", "error");
    els.gmailSyncProgress.classList.add("hidden");
  } finally {
    els.gmailSyncBtn.disabled = false;
  }
}

initEventListeners();
updateSidebarToggleLabel();
checkHealth();
fetchStats();
checkGmailAuth();
setInterval(fetchStats, 30_000);

