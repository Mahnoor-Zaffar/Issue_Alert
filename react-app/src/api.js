const BASE = import.meta.env.PROD ? "" : "";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function put(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function del(path) {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function fetchIssues(params = {}) {
  const q = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([_, v]) => v != null && v !== ""))
  ).toString();
  return get(`/api/issues?${q}`);
}

export function fetchIssue(id) {
  return get(`/api/issues/${id}`);
}

export function reTriage(id) {
  return post(`/api/issues/${id}/re-triage`);
}

export function openPR(id) {
  return post(`/api/issues/${id}/open-pr`);
}

export function setDifficulty(id, difficulty) {
  return post(`/api/issues/${id}/difficulty`, { difficulty });
}

export function setBookmark(id, bookmarked) {
  return post(`/api/issues/${id}/bookmark`, { value: bookmarked });
}

export function dismissIssue(id) {
  return post(`/api/issues/${id}/dismiss`, { value: true });
}

export function fetchPRDetails(prUrl) {
  return get(`/api/pr-details?pr_url=${encodeURIComponent(prUrl)}`);
}

export function fetchStats() {
  return get("/api/health");
}

export function fetchStatsHistory() {
  return get("/api/stats/history?days=14");
}

export function triggerPoll() {
  return post("/api/trigger-poll");
}

export function fetchPreferences() {
  return get("/api/preferences");
}

export function savePreferences(prefs) {
  return put("/api/preferences", prefs);
}

export function fetchPriorityRepos() {
  return get("/api/priority-repos");
}

export function addPriorityRepo(fullName) {
  return post("/api/priority-repos", { full_name: fullName });
}

export function removePriorityRepo(id) {
  return del(`/api/priority-repos/${id}`);
}

export function fetchRateLimit() {
  return get("/api/rate-limit");
}

export function fetchDaemonLog(lines = 50) {
  return get(`/api/daemon-log?lines=${lines}`);
}
