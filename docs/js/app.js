const issueMap = new Map();
const priorityMap = new Map();
let eventSource = null;
let lastVisibleTotal = null;

const IS_GITHUB_PAGES = location.hostname.endsWith("github.io");
const API_BASE = window.API_BASE || "";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

let filters = {
  language: "",
  status: "",
  label: "",
  bookmarked_only: false,
  show_dismissed: false,
  priority_only: false,
  difficulty: "",
};

const STATUS_LABELS = {
  pending: "Pending",
  notified: "Notified",
  extracting: "Extracting",
  triaging: "Triaging",
  complete: "Complete",
  error: "Error",
};

function removeIssueCard(id, animate = true) {
  const card = document.getElementById(`issue-${id}`);
  issueMap.delete(id);

  if (!card) {
    maybeShowEmptyState();
    return;
  }

  if (!animate) {
    card.remove();
    maybeShowEmptyState();
    return;
  }

  anime({
    targets: card,
    opacity: 0,
    translateX: 40,
    duration: 400,
    easing: "easeInOutQuad",
    complete: () => {
      card.remove();
      maybeShowEmptyState();
      loadStats();
    },
  });
}

function maybeShowEmptyState() {
  const list = document.getElementById("issue-list");
  if (issueMap.size === 0 && list && !document.getElementById("empty-state")) {
    list.innerHTML = `
      <div class="empty-state" id="empty-state">
        <p>No fresh unclaimed issues right now</p>
        <span id="empty-subtitle">Unclaimed issues from 1000+ star repos (last 7 days, sorted by activity). Click ★ to save favorites.</span>
      </div>`;
  }
}

async function markIssueViewed(id, { animate = true } = {}) {
  if (!issueMap.has(id)) return;
  try {
    await fetch(apiUrl(`/api/issues/${id}/view`), { method: "POST" });
  } catch { /* ignore */ }
  removeIssueCard(id, animate);
}

function truncate(text, max = 200) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function renderMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/gs, (m) => `<ul>${m}</ul>`)
    .replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
  return html;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function parseDifficulty(issue) {
  const d = issue.difficulty;
  if (d === "easy") return { level: "easy", label: "🟢 Easy" };
  if (d === "medium") return { level: "medium", label: "🟡 Medium" };
  if (d === "hard") return { level: "hard", label: "🔴 Hard" };
  if (issue.triage) {
    const text = issue.triage.action_plan;
    if (text.includes("🟢")) return { level: "easy", label: "🟢 Easy" };
    if (text.includes("🟡")) return { level: "medium", label: "🟡 Medium" };
    if (text.includes("🔴")) return { level: "hard", label: "🔴 Hard" };
  }
  return null;
}

function buildCard(issue) {
  const labels = (issue.labels || [])
    .map((l) => `<span class="badge badge-label">${escapeHtml(l)}</span>`)
    .join("");

  const langBadge = issue.language
    ? `<span class="badge badge-language">${escapeHtml(issue.language)}</span>`
    : "";

  const starsBadge =
    issue.repo_stars > 0
      ? `<span class="badge badge-stars">★ ${issue.repo_stars}</span>`
      : "";

  const scoreBadge =
    issue.score > 0
      ? `<span class="badge badge-score">Score ${issue.score}</span>`
      : "";

  const diff = parseDifficulty(issue);
  const diffBadge = diff
    ? `<span class="badge badge-difficulty ${diff.level}">${diff.label}</span>`
    : "";

  const priorityBadge = issue.is_priority
    ? `<span class="badge badge-difficulty" style="background:rgba(245,200,66,0.15);color:var(--accent-yellow)">🔔 Priority</span>`
    : "";

  const triageBtn = issue.status === "complete" && issue.triage
    ? `<button class="btn-view-triage" onclick="event.stopPropagation(); openTriagePanel(${issue.id})">View Report</button>`
    : issue.status === "error"
      ? `<span class="badge badge-difficulty hard" style="background:rgba(255,94,94,0.1);color:var(--accent-red)">Error</span>`
      : `<span class="triage-pending-msg">Triaging…</span>`;

  const cardClass = issue.status === "error" ? "issue-card issue-card-error" : "issue-card";
  const saveClass = issue.bookmarked ? "btn-save active" : "btn-save";

  return `
    <article class="${cardClass}" data-id="${issue.id}" id="issue-${issue.id}" onclick="handleCardClick(event, ${issue.id})">
      <div class="card-header">
        <div>
          <div class="card-meta">
            <span class="repo-name">${escapeHtml(issue.repo_full_name)}</span>
            ${langBadge}
            ${starsBadge}
            ${scoreBadge}
            ${diffBadge}
            ${priorityBadge}
            ${labels}
          </div>
          <h2 class="issue-title">
            <a href="${issue.html_url}" target="_blank" rel="noopener" onclick="handleIssueLinkClick(event, ${issue.id})">${escapeHtml(issue.title)}</a>
          </h2>
        </div>
        <span class="status-pill status-${issue.status}" data-status="${issue.status}">
          ${STATUS_LABELS[issue.status] || issue.status}
        </span>
      </div>
      <p class="issue-body-preview">${escapeHtml(truncate(issue.body))}</p>
      ${issue.error_message ? `<div class="error-box"><strong>Error:</strong> ${escapeHtml(issue.error_message)}</div>` : ""}
      <div class="card-actions" onclick="event.stopPropagation()">
        <button class="${saveClass}" onclick="toggleBookmark(${issue.id})" title="Save to favorites">${issue.bookmarked ? "★ Saved" : "☆ Save"}</button>
        ${triageBtn}
        <button class="btn-icon" onclick="dismissIssue(${issue.id})" title="Dismiss">✕</button>
        ${issue.triage ? `<button class="btn-export" onclick="exportTriage(${issue.id})" title="Export markdown">↓</button>` : ""}
      </div>
    </article>
  `;
}

function renderPanelBody(issue) {
  const t = issue.triage;
  if (!t) return `<p class="triage-pending-msg">No triage report available.</p>`;

  const sections = [
    { title: "🧩 What This Part of the Code Does", content: t.architecture_context },
    { title: "🐛 What's Wrong and What Needs to Change", content: t.issue_breakdown },
    { title: "📝 Plan to Fix It", content: t.action_plan },
  ];

  const html = sections
    .map(
      (s) => `
      <div class="panel-section">
        <h3>${s.title}</h3>
        <div>${renderMarkdown(s.content)}</div>
      </div>`
    )
    .join("");

  const prBtn = issue.difficulty === "easy"
    ? `<div style="margin-top:16px"><button class="btn btn-primary" onclick="openPR(${issue.id})" id="btn-open-pr-${issue.id}">🤖 Open Draft PR</button></div>`
    : "";

  return html + prBtn;
}

function animateCardIn(el, delay = 0) {
  if (!el) return;
  el.style.opacity = "0";
  el.style.transform = "translateY(-16px)";
  anime({
    targets: el,
    opacity: [0, 1],
    translateY: [-16, 0],
    duration: 500,
    delay,
    easing: "spring(1, 80, 10, 0)",
    complete: () => {
      el.style.opacity = "";
      el.style.transform = "";
    },
  });
}

function animateStatusComplete(pill) {
  anime({
    targets: pill,
    scale: [1, 1.15, 1],
    duration: 600,
    easing: "easeInOutQuad",
  });
}

/* ───── Slide-out Panel ───── */

function openTriagePanel(id) {
  const issue = issueMap.get(id) || priorityMap.get(id);
  if (!issue || !issue.triage) return;

  document.getElementById("panel-title").textContent = issue.title;
  document.getElementById("panel-repo").textContent = issue.repo_full_name;
  document.getElementById("panel-body").innerHTML = renderPanelBody(issue);
  document.getElementById("triage-panel").classList.add("open");
  document.getElementById("panel-overlay").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeTriagePanel() {
  document.getElementById("triage-panel").classList.remove("open");
  document.getElementById("panel-overlay").classList.remove("open");
  document.body.style.overflow = "";
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeTriagePanel();
});

function handleCardClick(event, id) {
  if (event.target.closest("a, button, .triage-panel, .panel-overlay")) return;
}

function handleIssueLinkClick(event, id) {
  event.stopPropagation();
}

function buildQueryParams() {
  const params = new URLSearchParams({ limit: "50" });
  if (filters.language) params.set("language", filters.language);
  if (filters.status) params.set("status", filters.status);
  if (filters.label) params.set("label", filters.label);
  if (filters.difficulty) params.set("difficulty", filters.difficulty);
  if (filters.bookmarked_only) params.set("bookmarked_only", "true");
  if (filters.show_dismissed) params.set("show_dismissed", "true");
  if (filters.priority_only) params.set("is_priority", "true");
  return params.toString();
}

function upsertIssue(issue, animate = true) {
  if (issue.dismissed && !filters.show_dismissed) {
    const existing = document.getElementById(`issue-${issue.id}`);
    if (existing) existing.remove();
    issueMap.delete(issue.id);
    return;
  }

  const existing = issueMap.get(issue.id);
  const prevStatus = existing?.status;

  issueMap.set(issue.id, issue);

  const list = document.getElementById("issue-list");
  const empty = document.getElementById("empty-state");
  if (empty) empty.remove();

  const cardId = `issue-${issue.id}`;
  let card = document.getElementById(cardId);

  if (card) {
    const wasOpen = document.getElementById("triage-panel")?.classList.contains("open")
      && document.getElementById("panel-title")?.textContent === issue.title;
    card.outerHTML = buildCard(issue);
    card = document.getElementById(cardId);
    if (animate) animateCardIn(card);

    if (prevStatus !== "complete" && issue.status === "complete") {
      const pill = card.querySelector(".status-pill");
      if (pill) animateStatusComplete(pill);
    }
  } else {
    list.insertAdjacentHTML("afterbegin", buildCard(issue));
    card = document.getElementById(cardId);
    if (animate) animateCardIn(card);
  }
}

async function loadIssues() {
  const res = await fetch(apiUrl(`/api/issues?${buildQueryParams()}`));
  const data = await res.json();
  const issues = data.issues || [];

  issueMap.clear();
  document.getElementById("issue-list").innerHTML = "";

  if (issues.length === 0) {
    document.getElementById("issue-list").innerHTML = `
      <div class="empty-state" id="empty-state">
        <p>No fresh unclaimed issues right now</p>
        <span id="empty-subtitle">Unclaimed issues from 1000+ star repos (last 7 days, sorted by activity). Click ★ to save favorites.</span>
      </div>`;
  } else {
    issues.reverse().forEach((issue, i) => {
      upsertIssue(issue, false);
      const card = document.getElementById(`issue-${issue.id}`);
      if (card) animateCardIn(card, i * 60);
    });
  }

  await loadPriorityIssues();
}

const DEFAULT_EMPTY_SUBTITLE =
  "Unclaimed issues from 1000+ star repos (last 7 days, sorted by activity). Click ★ to save favorites.";

function updateEmptySubtitle(message) {
  const subtitle = document.getElementById("empty-subtitle");
  if (!subtitle) return;
  subtitle.textContent = message || DEFAULT_EMPTY_SUBTITLE;
}

function formatPollTime(isoOrSql) {
  if (!isoOrSql) return "Never";
  const d = new Date(isoOrSql.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return isoOrSql;
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "Just now";
  if (mins === 1) return "1 min ago";
  return `${mins} min ago`;
}

async function loadStats() {
  try {
    const res = await fetch(apiUrl("/api/health"));
    const data = await res.json();
    document.getElementById("stat-total").textContent = data.total ?? 0;
    document.getElementById("stat-pending").textContent = data.pending ?? 0;
    document.getElementById("stat-complete").textContent = data.complete ?? 0;

    if (lastVisibleTotal !== null && data.total < lastVisibleTotal) {
      await loadIssues();
    }
    lastVisibleTotal = data.total ?? 0;

    const pollParts = [];
    pollParts.push(formatPollTime(data.last_poll_at));
    if (data.last_poll_fetched != null) {
      pollParts.push(`${data.last_poll_fetched} fetched`);
    }
    if (data.last_poll_new != null) {
      pollParts.push(`${data.last_poll_new} new`);
    }
    if (data.last_poll_total_count) {
      pollParts.push(`${data.last_poll_total_count} on GitHub`);
    }
    document.getElementById("last-poll-text").textContent = pollParts.join(" · ");

    updateEmptySubtitle(data.last_poll_message);
  } catch { /* ignore */ }
}

async function loadPreferences() {
  try {
    const res = await fetch(apiUrl("/api/preferences"));
    const prefs = await res.json();
    document.getElementById("pref-languages").value = (prefs.languages || []).join(",");
    document.getElementById("pref-labels").value = (prefs.labels || []).join(",");
    document.getElementById("pref-min-stars").value = prefs.min_stars ?? 10;
    document.getElementById("pref-show-dismissed").checked = !!prefs.show_dismissed;
    filters.show_dismissed = !!prefs.show_dismissed;
  } catch { /* ignore */ }
}

async function savePreferences() {
  const body = {
    languages: document.getElementById("pref-languages").value.split(",").map((s) => s.trim()).filter(Boolean),
    labels: document.getElementById("pref-labels").value.split(",").map((s) => s.trim()).filter(Boolean),
    min_stars: parseInt(document.getElementById("pref-min-stars").value, 10) || 0,
    show_dismissed: document.getElementById("pref-show-dismissed").checked,
  };
  await fetch(apiUrl("/api/preferences"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  filters.show_dismissed = body.show_dismissed;
  await loadIssues();
}

async function triggerPoll() {
  const btn = document.getElementById("btn-poll-now");
  btn.disabled = true;
  btn.textContent = "Polling…";
  try {
    await fetch(apiUrl("/api/trigger-poll"), { method: "POST" });
    document.getElementById("last-poll-text").textContent = "Poll requested…";
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = "Poll Now";
    }, 2000);
  }
}

async function toggleBookmark(id) {
  const issue = issueMap.get(id) || priorityMap.get(id);
  const newVal = !issue?.bookmarked;
  const res = await fetch(apiUrl(`/api/issues/${id}/bookmark`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: newVal }),
  });
  const updated = await res.json();
  upsertIssue(updated, false);
  if (newVal && updated.status !== "complete") {
    setTimeout(loadIssues, 2000);
  }
}

async function dismissIssue(id) {
  await fetch(apiUrl(`/api/issues/${id}/dismiss`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: true }),
  });
  removeIssueCard(id);
  removePriorityCard(id);
}

// ── Priority Repos ────────────────────────────────────────

async function loadPriorityRepos() {
  try {
    const res = await fetch(apiUrl("/api/priority-repos"));
    const data = await res.json();
    const list = document.getElementById("priority-repo-list");
    list.innerHTML = (data.repos || []).map((r) =>
      `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 4px 2px 0;padding:2px 8px;background:rgba(245,200,66,0.1);border-radius:4px;font-size:0.78rem">
        ${r.full_name}
        <button onclick="removePriorityRepo(${r.id})" style="background:none;border:none;color:var(--accent-red);cursor:pointer;font-size:0.85rem;padding:0;line-height:1">✕</button>
      </span>`
    ).join("") || "<span style='color:var(--text-muted)'>No repos added yet</span>";
  } catch { /* ignore */ }
}

async function loadPriorityIssues() {
  try {
    const res = await fetch(apiUrl("/api/issues/priority"));
    const data = await res.json();
    const section = document.getElementById("priority-section");
    const list = document.getElementById("priority-list");
    priorityMap.clear();
    if (!data.issues || data.issues.length === 0) {
      section.style.display = "none";
      return;
    }
    section.style.display = "block";
    list.innerHTML = "";
    data.issues.reverse().forEach((issue, i) => {
      priorityMap.set(issue.id, issue);
      list.insertAdjacentHTML("afterbegin", buildCard(issue));
      const card = document.getElementById(`issue-${issue.id}`);
      if (card) animateCardIn(card, i * 60);
    });
  } catch { section.style.display = "none"; }
}

function removePriorityCard(id) {
  const card = document.getElementById(`issue-${id}`);
  if (card && card.closest("#priority-list")) {
    card.remove();
    priorityMap.delete(id);
    if (priorityMap.size === 0) document.getElementById("priority-section").style.display = "none";
  }
}

async function addPriorityRepo() {
  const input = document.getElementById("input-priority-repo");
  const name = input.value.trim();
  if (!name) return;
  input.value = "";
  try {
    await fetch(apiUrl("/api/priority-repos"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: name }),
    });
    await loadPriorityRepos();
  } catch { /* ignore */ }
}

async function removePriorityRepo(id) {
  await fetch(apiUrl(`/api/priority-repos/${id}`), { method: "DELETE" });
  await loadPriorityRepos();
}

// ── Open PR ───────────────────────────────────────────────

async function openPR(id) {
  const btn = document.getElementById(`btn-open-pr-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = "Opening PR…"; }
  try {
    const res = await fetch(apiUrl(`/api/issues/${id}/open-pr`), { method: "POST" });
    const data = await res.json();
    if (res.ok && data.pr_url) {
      window.open(data.pr_url, "_blank");
    } else {
      alert(data.detail || "Failed to open PR");
    }
  } catch {
    alert("Failed to open PR — check daemon logs");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🤖 Open Draft PR"; }
  }
}

// ── Stats History + Sparkline ─────────────────────────────

async function loadStatsHistory() {
  try {
    const res = await fetch(apiUrl("/api/stats/history?days=14"));
    const data = await res.json();
    const history = data.history || [];
    const card = document.getElementById("history-card");
    if (history.length < 2) { card.style.display = "none"; return; }
    card.style.display = "block";
    renderSparkline(history);
  } catch { document.getElementById("history-card").style.display = "none"; }
}

function renderSparkline(history) {
  const svg = document.getElementById("sparkline");
  const w = 200, h = 28;
  const values = history.map((d) => d.triaged);
  const max = Math.max(...values, 1);
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - (v / max) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(" ");
  svg.innerHTML = `
    <defs>
      <linearGradient id="spark-gradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(91,192,235,0.3)" />
        <stop offset="100%" stop-color="rgba(91,192,235,0)" />
      </linearGradient>
    </defs>
    <polyline fill="url(#spark-gradient)" stroke="none"
      points="0,${h} ${points} ${w},${h}" />
    <polyline fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
      points="${points}" />
  `;
}

function exportTriage(id) {
  const issue = issueMap.get(id);
  if (!issue?.triage) return;

  const md = `# ${issue.title}

**Repo:** ${issue.repo_full_name}  
**URL:** ${issue.html_url}

## 🧩 What This Part of the Code Does
${issue.triage.architecture_context}

## 🐛 What's Wrong and What Needs to Change
${issue.triage.issue_breakdown}

## 📝 Plan to Fix It
${issue.triage.action_plan}
`;

  const blob = new Blob([md], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `triage-${issue.id}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

window.openTriagePanel = openTriagePanel;
window.closeTriagePanel = closeTriagePanel;
window.toggleBookmark = toggleBookmark;
window.dismissIssue = dismissIssue;
window.exportTriage = exportTriage;
window.openPR = openPR;
window.handleCardClick = handleCardClick;
window.handleIssueLinkClick = handleIssueLinkClick;

function showPagesBanner() {
  const banner = document.createElement("div");
  banner.className = "pages-banner";
  banner.innerHTML =
    "<strong>GitHub Pages preview</strong> — This is the static UI only. " +
    "Run the app locally (<code>./run.sh</code>) and open " +
    "<a href=\"http://127.0.0.1:8000\">http://127.0.0.1:8000</a> for the live dashboard with API.";
  document.body.prepend(banner);
}

function setConnectionStatus(connected) {
  const dot = document.getElementById("sse-dot");
  const label = document.getElementById("sse-label");
  dot.className = "status-dot " + (connected ? "connected" : "disconnected");
  label.textContent = connected ? "Live" : "Reconnecting…";
}

function connectSSE() {
  if (eventSource) eventSource.close();

  eventSource = new EventSource(apiUrl("/api/events"));

  eventSource.addEventListener("connected", () => {
    setConnectionStatus(true);
  });

  eventSource.addEventListener("issue_update", (e) => {
    const issue = JSON.parse(e.data);
    upsertIssue(issue);
    loadStats();
  });

  eventSource.addEventListener("stats_update", (e) => {
    const stats = JSON.parse(e.data);
    document.getElementById("stat-total").textContent = stats.total ?? 0;
    document.getElementById("stat-pending").textContent = stats.pending ?? 0;
    document.getElementById("stat-complete").textContent = stats.complete ?? 0;
    if (lastVisibleTotal !== null && stats.total < lastVisibleTotal) {
      loadIssues();
    }
    lastVisibleTotal = stats.total ?? 0;
    const pollParts = [
      formatPollTime(stats.last_poll_at),
      `${stats.last_poll_fetched ?? 0} fetched`,
      `${stats.last_poll_new ?? 0} new`,
    ];
    if (stats.last_poll_total_count) pollParts.push(`${stats.last_poll_total_count} on GitHub`);
    document.getElementById("last-poll-text").textContent = pollParts.join(" · ");
    updateEmptySubtitle(stats.last_poll_message);
  });

  eventSource.onerror = () => {
    setConnectionStatus(false);
    eventSource.close();
    setTimeout(connectSSE, 3000);
  };
}

function bindFilters() {
  ["filter-language", "filter-status", "filter-label", "filter-difficulty"].forEach((id) => {
    document.getElementById(id).addEventListener("change", (e) => {
      const key = id.replace("filter-", "");
      filters[key === "bookmarked" ? "bookmarked_only" : key] = e.target.value;
      loadIssues();
    });
  });

  document.getElementById("filter-bookmarked").addEventListener("change", (e) => {
    filters.bookmarked_only = e.target.checked;
    loadIssues();
  });

  document.getElementById("filter-priority").addEventListener("change", (e) => {
    filters.priority_only = e.target.checked;
    loadIssues();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (IS_GITHUB_PAGES) showPagesBanner();
  loadPreferences();
  loadIssues();
  loadStats();
  loadStatsHistory();
  loadPriorityRepos();
  connectSSE();
  bindFilters();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadIssues();
    loadStats();
    loadStatsHistory();
    loadPriorityRepos();
  });
  document.getElementById("btn-poll-now").addEventListener("click", triggerPoll);
  document.getElementById("btn-save-prefs").addEventListener("click", savePreferences);
  document.getElementById("panel-close").addEventListener("click", closeTriagePanel);
  document.getElementById("panel-overlay").addEventListener("click", closeTriagePanel);
  document.getElementById("btn-add-priority-repo").addEventListener("click", addPriorityRepo);
  document.getElementById("input-priority-repo").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addPriorityRepo();
  });

  setInterval(loadStats, 15000);
});
