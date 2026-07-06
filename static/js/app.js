const issueMap = new Map();
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
  } catch {
    /* ignore — card still removed locally */
  }
  removeIssueCard(id, animate);
}

function truncate(text, max = 200) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function renderMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/gs, (m) => `<ul>${m}</ul>`)
    .replace(/\n\n/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
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

  const triageHtml = buildTriageHtml(issue);
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
      ${triageHtml}
      ${issue.error_message ? `<div class="error-box"><strong>Error:</strong> ${escapeHtml(issue.error_message)}</div>` : ""}
      <div class="card-actions" onclick="event.stopPropagation()">
        <button class="${saveClass}" onclick="toggleBookmark(${issue.id})" title="Save to favorites">${issue.bookmarked ? "★ Saved" : "☆ Save"}</button>
        <button class="btn-icon" onclick="dismissIssue(${issue.id})" title="Dismiss">✕</button>
        ${issue.triage ? `<button class="btn btn-secondary btn-sm" onclick="exportTriage(${issue.id})">Export MD</button>` : ""}
      </div>
    </article>
  `;
}

function buildTriageHtml(issue) {
  if (issue.status === "complete" && issue.triage) {
    return `
      <button class="triage-toggle" onclick="event.stopPropagation(); toggleTriage(${issue.id})">
        View AI Triage Report
      </button>
      <div class="triage-sections" id="triage-${issue.id}">
        <div class="triage-grid">
          <div class="triage-section">
            <h3>Architecture Context</h3>
            <div>${renderMarkdown(issue.triage.architecture_context)}</div>
          </div>
          <div class="triage-section">
            <h3>Issue Breakdown</h3>
            <div>${renderMarkdown(issue.triage.issue_breakdown)}</div>
          </div>
          <div class="triage-section">
            <h3>PR Action Plan</h3>
            <div>${renderMarkdown(issue.triage.action_plan)}</div>
          </div>
        </div>
      </div>
    `;
  }

  if (issue.status === "error") {
    return `<p class="triage-pending-msg">Triage failed — see error below.</p>`;
  }

  return `<p class="triage-pending-msg">AI triage in progress…</p>`;
}

function animateCardIn(el, delay = 0) {
  if (!el) return;
  el.style.opacity = "0";
  el.style.transform = "translateY(-20px)";
  anime({
    targets: el,
    opacity: [0, 1],
    translateY: [-20, 0],
    duration: 600,
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

function toggleTriage(id) {
  const section = document.getElementById(`triage-${id}`);
  if (!section) return;

  const isOpen = section.classList.contains("open");

  if (isOpen) {
    anime({
      targets: section,
      height: 0,
      duration: 400,
      easing: "easeInOutQuad",
      complete: () => {
        section.classList.remove("open");
      },
    });
  } else {
    section.style.height = "auto";
    const fullHeight = section.scrollHeight;
    section.style.height = "0";
    section.classList.add("open");

    anime({
      targets: section,
      height: fullHeight,
      duration: 400,
      easing: "easeInOutQuad",
      complete: () => {
        section.style.height = "auto";
      },
    });
  }
}

function handleCardClick(event, id) {
  if (event.target.closest("a, button, .triage-sections, .triage-toggle")) return;
}

function handleIssueLinkClick(event, id) {
  event.stopPropagation();
}

function buildQueryParams() {
  const params = new URLSearchParams({ limit: "50" });
  if (filters.language) params.set("language", filters.language);
  if (filters.status) params.set("status", filters.status);
  if (filters.label) params.set("label", filters.label);
  if (filters.bookmarked_only) params.set("bookmarked_only", "true");
  if (filters.show_dismissed) params.set("show_dismissed", "true");
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
    const wasOpen = document
      .getElementById(`triage-${issue.id}`)
      ?.classList.contains("open");
    card.outerHTML = buildCard(issue);
    card = document.getElementById(cardId);

    if (animate) animateCardIn(card);

    if (wasOpen && issue.status === "complete") {
      const section = document.getElementById(`triage-${issue.id}`);
      if (section) {
        section.classList.add("open");
        section.style.height = "auto";
      }
    }

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
    return;
  }

  issues.reverse().forEach((issue, i) => {
    upsertIssue(issue, false);
    const card = document.getElementById(`issue-${issue.id}`);
    if (card) animateCardIn(card, i * 60);
  });
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
  } catch {
    /* ignore */
  }
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
  } catch {
    /* ignore */
  }
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
  const issue = issueMap.get(id);
  const newVal = !issue?.bookmarked;
  const res = await fetch(apiUrl(`/api/issues/${id}/bookmark`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: newVal }),
  });
  const updated = await res.json();
  upsertIssue(updated, false);
}

async function dismissIssue(id) {
  await fetch(apiUrl(`/api/issues/${id}/dismiss`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value: true }),
  });
  removeIssueCard(id);
}

function exportTriage(id) {
  const issue = issueMap.get(id);
  if (!issue?.triage) return;

  const md = `# ${issue.title}

**Repo:** ${issue.repo_full_name}  
**URL:** ${issue.html_url}

## Codebase Architecture Context
${issue.triage.architecture_context}

## Core Issue Breakdown
${issue.triage.issue_breakdown}

## Suggested PR Action Plan
${issue.triage.action_plan}
`;

  const blob = new Blob([md], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `triage-${issue.id}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

window.toggleTriage = toggleTriage;
window.toggleBookmark = toggleBookmark;
window.dismissIssue = dismissIssue;
window.exportTriage = exportTriage;
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
  ["filter-language", "filter-status", "filter-label"].forEach((id) => {
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
}

document.addEventListener("DOMContentLoaded", () => {
  if (IS_GITHUB_PAGES) showPagesBanner();
  loadPreferences();
  loadIssues();
  loadStats();
  connectSSE();
  bindFilters();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadIssues();
    loadStats();
  });
  document.getElementById("btn-poll-now").addEventListener("click", triggerPoll);
  document.getElementById("btn-save-prefs").addEventListener("click", savePreferences);

  setInterval(loadStats, 15000);
});
