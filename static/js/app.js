const issueMap = new Map();
let eventSource = null;

const STATUS_LABELS = {
  pending: "Pending",
  notified: "Notified",
  extracting: "Extracting",
  triaging: "Triaging",
  complete: "Complete",
  error: "Error",
};

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

function buildCard(issue) {
  const labels = (issue.labels || [])
    .map((l) => `<span class="badge badge-label">${l}</span>`)
    .join("");

  const langBadge = issue.language
    ? `<span class="badge badge-language">${issue.language}</span>`
    : "";

  const triageHtml = buildTriageHtml(issue);

  return `
    <article class="issue-card" data-id="${issue.id}" id="issue-${issue.id}">
      <div class="card-header">
        <div>
          <div class="card-meta">
            <span class="repo-name">${issue.repo_full_name}</span>
            ${langBadge}
            ${labels}
          </div>
          <h2 class="issue-title">
            <a href="${issue.html_url}" target="_blank" rel="noopener">${issue.title}</a>
          </h2>
        </div>
        <span class="status-pill status-${issue.status}" data-status="${issue.status}">
          ${STATUS_LABELS[issue.status] || issue.status}
        </span>
      </div>
      <p class="issue-body-preview">${truncate(issue.body)}</p>
      ${triageHtml}
      ${issue.error_message ? `<p class="error-msg">${issue.error_message}</p>` : ""}
    </article>
  `;
}

function buildTriageHtml(issue) {
  if (issue.status === "complete" && issue.triage) {
    return `
      <button class="triage-toggle" onclick="toggleTriage(${issue.id})">
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
    return "";
  }

  return `<p class="triage-pending-msg">AI triage in progress…</p>`;
}

function animateCardIn(el, delay = 0) {
  anime({
    targets: el,
    opacity: [0, 1],
    translateY: [-20, 0],
    duration: 600,
    delay,
    easing: "spring(1, 80, 10, 0)",
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
      complete: () => section.classList.remove("open"),
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

window.toggleTriage = toggleTriage;

function upsertIssue(issue, animate = true) {
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
  const res = await fetch("/api/issues?limit=50");
  const data = await res.json();
  const issues = data.issues || [];

  if (issues.length === 0) return;

  const empty = document.getElementById("empty-state");
  if (empty) empty.remove();

  issues.reverse().forEach((issue, i) => {
    upsertIssue(issue, false);
    const card = document.getElementById(`issue-${issue.id}`);
    if (card) animateCardIn(card, i * 80);
  });
}

async function loadStats() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    document.getElementById("stat-total").textContent = data.issue_count ?? 0;
    document.getElementById("stat-pending").textContent = data.pending ?? 0;
    document.getElementById("stat-complete").textContent = data.complete ?? 0;
  } catch {
    /* ignore */
  }
}

function setConnectionStatus(connected) {
  const dot = document.getElementById("sse-dot");
  const label = document.getElementById("sse-label");
  dot.className = "status-dot " + (connected ? "connected" : "disconnected");
  label.textContent = connected ? "Live" : "Reconnecting…";
}

function connectSSE() {
  if (eventSource) eventSource.close();

  eventSource = new EventSource("/api/events");

  eventSource.addEventListener("connected", () => {
    setConnectionStatus(true);
  });

  eventSource.addEventListener("issue_update", (e) => {
    const issue = JSON.parse(e.data);
    upsertIssue(issue);
    loadStats();
  });

  eventSource.onerror = () => {
    setConnectionStatus(false);
    eventSource.close();
    setTimeout(connectSSE, 3000);
  };
}

document.addEventListener("DOMContentLoaded", () => {
  loadIssues();
  loadStats();
  connectSSE();
  setInterval(loadStats, 15000);
});
