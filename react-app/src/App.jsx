import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Sidebar from "./components/Sidebar";
import IssueCard from "./components/IssueCard";
import PrCard from "./components/PrCard";
import PrReviewPanel from "./components/PrReviewPanel";
import TriagePanel from "./components/TriagePanel";
import Toast from "./components/Toast";
import BountyPopup from "./components/BountyPopup";
import { useSSE } from "./useSSE";
import { usePaginatedIssues, PAGE_SIZE } from "./usePaginatedIssues";
import { fetchIssues, fetchStats, fetchStatsHistory, triggerPoll, setBookmark, dismissIssue, fetchTopPicks, fetchResume, fetchPRs } from "./api";

const DIFFICULTY_OPTIONS = [
  { value: "", label: "All difficulties" },
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "complete", label: "Complete" },
  { value: "triaging", label: "Triaging" },
  { value: "extracting", label: "Extracting" },
  { value: "error", label: "Error" },
  { value: "pending", label: "Pending" },
];

const LABEL_OPTIONS = [
  { value: "", label: "All labels" },
  { value: "help wanted", label: "help wanted" },
  { value: "good first issue", label: "good first issue" },
  { value: "open source", label: "open source" },
];

const LANG_OPTIONS = [
  { value: "", label: "All languages" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "python", label: "Python" },
];

const SORT_OPTIONS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "stars_desc", label: "Most Stars" },
  { value: "stars_asc", label: "Least Stars" },
  { value: "repo", label: "Repo A-Z" },
  { value: "saved", label: "Similar to Saved" },
];

function playPriorityChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(523.25, ctx.currentTime); // C5
    osc.frequency.setValueAtTime(659.25, ctx.currentTime + 0.1); // E5
    osc.frequency.setValueAtTime(783.99, ctx.currentTime + 0.2); // G5
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch {}
}

function readFilters() {
  const p = new URLSearchParams(location.search);
  return {
    filterLang: p.get("lang") || "",
    filterStatus: p.get("status") || "",
    filterDiff: p.get("diff") || "",
    filterLabel: p.get("label") || "",
    filterSaved: p.get("saved") === "1",
    filterPriority: p.get("priority") === "1",
    filterClaimed: p.get("claimed") === "1",
    filterBounty: p.get("bounty") === "1",
    searchQuery: p.get("q") || "",
    sortBy: p.get("sort") || "newest",
  };
}

function writeFilters(filters) {
  const p = new URLSearchParams();
  if (filters.filterLang) p.set("lang", filters.filterLang);
  if (filters.filterStatus) p.set("status", filters.filterStatus);
  if (filters.filterDiff) p.set("diff", filters.filterDiff);
  if (filters.filterLabel) p.set("label", filters.filterLabel);
  if (filters.filterSaved) p.set("saved", "1");
  if (filters.filterPriority) p.set("priority", "1");
  if (filters.filterClaimed) p.set("claimed", "1");
  if (filters.filterBounty) p.set("bounty", "1");
  if (filters.searchQuery) p.set("q", filters.searchQuery);
  if (filters.sortBy && filters.sortBy !== "newest") p.set("sort", filters.sortBy);
  const q = p.toString();
  const url = q ? `?${q}` : location.pathname;
  history.replaceState(null, "", url);
}

function sortIssues(list, sortBy) {
  const sorted = [...list];
  switch (sortBy) {
    case "oldest":
      sorted.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      break;
    case "stars_desc":
      sorted.sort((a, b) => (b.repo_stars || 0) - (a.repo_stars || 0));
      break;
    case "stars_asc":
      sorted.sort((a, b) => (a.repo_stars || 0) - (b.repo_stars || 0));
      break;
    case "repo":
      sorted.sort((a, b) => (a.repo_full_name || "").localeCompare(b.repo_full_name || ""));
      break;
    default:
      sorted.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }
  return sorted;
}

function ToggleChip({ checked, onChange, label, live = false }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`cursor-pointer select-none shrink-0 inline-flex items-center gap-[6px] text-xs font-medium px-2.5 py-[7px] rounded-xl border transition-colors ${
        checked
          ? live
            ? "text-success border-success/40 bg-success/10"
            : "text-primary border-primary/40 bg-primary/10"
          : "text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
      }`}
    >
      <span
        className={`w-[6px] h-[6px] rounded-full transition-colors ${
          live ? (checked ? "bg-success live-dot" : "bg-ink-tertiary") : checked ? "bg-primary" : "bg-ink-tertiary"
        }`}
      />
      {label}
    </button>
  );
}

export default function App() {
  const initial = readFilters();
  const [issues, setIssues] = useState([]);
  const [priorityIssues, setPriorityIssues] = useState([]);
  const [panelPr, setPanelPr] = useState(null);
  const [prs, setPrs] = useState([]);
  const [stats, setStats] = useState(null);
  const [statsHistory, setStatsHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const [panelIssue, setPanelIssue] = useState(null);
  const [toast, setToast] = useState({ message: "", type: "info", action: null });

  const [filterLang, setFilterLang] = useState(initial.filterLang);
  const [filterStatus, setFilterStatus] = useState(initial.filterStatus);
  const [filterDiff, setFilterDiff] = useState(initial.filterDiff);
  const [filterLabel, setFilterLabel] = useState(initial.filterLabel);
  const [filterSaved, setFilterSaved] = useState(initial.filterSaved);
  const [filterClaimed, setFilterClaimed] = useState(initial.filterClaimed);
  const [filterBounty, setFilterBounty] = useState(initial.filterBounty);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [desktopNotif, setDesktopNotif] = useState(false);
  const [filterPriority, setFilterPriority] = useState(initial.filterPriority);
  const [searchQuery, setSearchQuery] = useState(initial.searchQuery);
  const [sortBy, setSortBy] = useState(initial.sortBy);
  const [topPicks, setTopPicks] = useState([]);
  const [resumeMd, setResumeMd] = useState("");
  const [showResume, setShowResume] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bountyPopups, setBountyPopups] = useState([]);
  const [selectMode, setSelectMode] = useState(false);
  const [savedSearches, setSavedSearches] = useState(() => {
    try { return JSON.parse(localStorage.getItem("savedSearches") || "[]"); } catch { return []; }
  });

  const knownIds = useRef(new Set());

  const showToast = useCallback((message, type = "info", action = null) => {
    setToast({ message, type, action });
  }, []);

  const requestNotifPerm = useCallback(async () => {
    if (!("Notification" in window)) { showToast("Desktop notifications not supported", "error"); return; }
    const perm = await Notification.requestPermission();
    if (perm === "granted") { setDesktopNotif(true); showToast("Notifications enabled", "success"); }
    else { showToast("Notification permission denied", "error"); }
  }, [showToast]);

  const sendDesktopNotif = useCallback((title, body, url) => {
    if (!desktopNotif || !("Notification" in window) || Notification.permission !== "granted") return;
    try {
      const n = new Notification(title, { body, icon: "/favicon.ico" });
      if (url) n.onclick = () => window.open(url, "_blank");
    } catch {}
  }, [desktopNotif]);

  const handleExportMarkdown = useCallback(async () => {
    try {
      const data = await fetchIssues({ bookmarked_only: "true", limit: 200 });
      const items = data.issues || [];
      if (!items.length) { showToast("No bookmarked issues to export", "error"); return; }
      let md = `# Saved Issues (${new Date().toISOString().slice(0, 10)})\n\n`;
      for (const issue of items) {
        md += `- [${issue.title}](${issue.html_url}) — ${issue.repo_full_name}`;
        if (issue.language) md += ` (${issue.language})`;
        if (issue.difficulty) md += ` [${issue.difficulty}]`;
        md += "\n";
      }
      const blob = new Blob([md], { type: "text/markdown" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `saved-issues-${Date.now()}.md`;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast("Exported as markdown", "success");
    } catch { showToast("Export failed", "error"); }
  }, [showToast]);

  const handleSaveSearch = useCallback(() => {
    const name = prompt("Name this search preset:");
    if (!name) return;
    const preset = {
      name,
      filterLang, filterStatus, filterDiff, filterLabel,
      filterSaved, filterPriority, filterClaimed, filterBounty, searchQuery, sortBy,
    };
    const updated = [...savedSearches, preset];
    setSavedSearches(updated);
    localStorage.setItem("savedSearches", JSON.stringify(updated));
    showToast(`Saved "${name}"`, "success");
  }, [filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, filterClaimed, filterBounty, searchQuery, sortBy, savedSearches, showToast]);

  const handleLoadSearch = useCallback((preset) => {
    setFilterLang(preset.filterLang || "");
    setFilterStatus(preset.filterStatus || "");
    setFilterDiff(preset.filterDiff || "");
    setFilterLabel(preset.filterLabel || "");
    setFilterSaved(preset.filterSaved || false);
    setFilterPriority(preset.filterPriority || false);
    setFilterClaimed(preset.filterClaimed || false);
    setFilterBounty(preset.filterBounty || false);
    setSearchQuery(preset.searchQuery || "");
    setSortBy(preset.sortBy || "newest");
    showToast(`Loaded "${preset.name}"`, "success");
  }, [showToast]);

  const handleDeleteSearch = useCallback((idx) => {
    const updated = savedSearches.filter((_, i) => i !== idx);
    setSavedSearches(updated);
    localStorage.setItem("savedSearches", JSON.stringify(updated));
  }, [savedSearches]);

  const handleBatchTriage = useCallback(async () => {
    const ids = [...selectedIds];
    if (!ids.length) { showToast("No issues selected", "error"); return; }
    try {
      const res = await fetch("/api/issues/batch-triage", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      showToast(data?.message || `${ids.length} queued`, "success");
      setSelectedIds(new Set());
      setSelectMode(false);
    } catch { showToast("Batch triage failed", "error"); }
  }, [selectedIds, showToast]);

  const toggleSelect = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  useEffect(() => {
    writeFilters({ filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, filterClaimed, filterBounty, searchQuery, sortBy });
  }, [filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, filterClaimed, filterBounty, searchQuery, sortBy]);

  const {
    data,
    issues: pageIssues,
    page,
    setPage,
    hasNextPage,
    isFetchingPage,
    refetch,
  } = usePaginatedIssues({
    filterLang,
    filterStatus,
    filterDiff,
    filterLabel,
    filterSaved,
    filterPriority,
    filterClaimed,
    filterBounty,
  });

  const filterKey = [
    filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, filterClaimed, filterBounty,
  ].join("|");
  const lastFilterKey = useRef(filterKey);

  useEffect(() => {
    const list = pageIssues || [];
    if (!data) return;
    const isNewFilter = lastFilterKey.current !== filterKey;
    lastFilterKey.current = filterKey;
    if (isNewFilter) {
      setPriorityIssues(list.filter((i) => i.is_priority));
      setIssues(list.filter((i) => !i.is_priority));
    } else {
      setPriorityIssues(list.filter((i) => i.is_priority));
      setIssues(list.filter((i) => !i.is_priority));
    }
    list.forEach((i) => knownIds.current.add(i.id));
  }, [data, pageIssues, filterKey]);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatsHistory().then((d) => setStatsHistory(d.history || [])).catch(() => {});
  }, []);

  useEffect(() => {
    fetchTopPicks(3).then((d) => setTopPicks(d.top_picks || [])).catch(() => {});
  }, [issues.length]);

  useEffect(() => {
    let cancelled = false;
    fetchPRs(60)
      .then((d) => { if (!cancelled) setPrs(d.prs || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const refreshPRs = useCallback(() => {
    fetchPRs(60).then((d) => setPrs(d.prs || [])).catch(() => {});
  }, []);

  useSSE({
    onIssueUpdate: useCallback((updated) => {
      const isNew = !knownIds.current.has(updated.id);
      knownIds.current.add(updated.id);

      if (isNew && updated.is_priority) {
        playPriorityChime();
        showToast(`🔔 New priority: ${updated.title.slice(0, 60)}`, "info");
        sendDesktopNotif("🔔 New Priority Issue", `${updated.repo_full_name} — ${updated.title.slice(0, 80)}`, window.location.origin);
      }

      if (isNew && updated.is_bounty) {
        const id = Date.now();
        setBountyPopups((prev) => [...prev, { id, issue: updated }]);
        playPriorityChime();
        sendDesktopNotif(
          `💰 New Bounty Issue${updated.bounty_amount ? ` — $${updated.bounty_amount.toLocaleString()}` : ""}`,
          `${updated.repo_full_name} — ${updated.title.slice(0, 80)}`,
          updated.html_url
        );
      }

      if (autoRefresh) {
        setIssues((prev) => {
          const idx = prev.findIndex((i) => i.id === updated.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = updated;
            return next;
          }
          if (isNew && !updated.is_priority) {
            return [updated, ...prev];
          }
          return prev;
        });
        setPriorityIssues((prev) => {
          const idx = prev.findIndex((i) => i.id === updated.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = updated;
            return next;
          }
          if (isNew && updated.is_priority) {
            return [updated, ...prev];
          }
          return prev;
        });
      } else {
        setIssues((prev) => {
          const idx = prev.findIndex((i) => i.id === updated.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = updated;
            return next;
          }
          return prev;
        });
        setPriorityIssues((prev) => {
          const idx = prev.findIndex((i) => i.id === updated.id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = updated;
            return next;
          }
          return prev;
        });
      }
    }, [autoRefresh, showToast, sendDesktopNotif]),
    onStatsUpdate: useCallback((s) => setStats(s), []),
    onConnected: useCallback((c) => setConnected(c), []),
  });

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    refetch();
  }, [filterKey]);

  const handleRefresh = useCallback(() => {
    refetch();
    loadStats();
    showToast("Refreshed", "success");
  }, [refetch, loadStats, showToast]);

  const handlePollNow = useCallback(async () => {
    try {
      await triggerPoll();
      showToast("Poll requested — daemon will check shortly", "success");
    } catch {
      showToast("Poll request failed", "error");
    }
  }, [showToast]);

  const handleTriageClick = useCallback((issue) => {
    setPanelIssue(issue);
  }, []);

  const [lastDismissed, setLastDismissed] = useState(null);
  const handleDismiss = useCallback((issue) => {
    setLastDismissed(issue);
    showToast("Dismissed", "success", {
      label: "Undo",
      onClick: () => {
        setLastDismissed(null);
        fetch(`/api/issues/${issue.id}/dismiss`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: false }),
        }).then(() => {
          showToast("Undone", "success");
          refetch();
        }).catch(() => {
          showToast("Undo failed", "error");
        });
      },
    });
  }, [showToast, refetch]);

  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
      if (e.key === "p") handlePollNow();
      if (e.key === "r") handleRefresh();
      if (e.key === "Escape") setPanelIssue(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handlePollNow, handleRefresh]);

  // Frontend search + sort
  const filterBySearch = (list) => {
    if (!searchQuery) return list;
    const q = searchQuery.toLowerCase();
    return list.filter(
      (i) =>
        (i.title || "").toLowerCase().includes(q) ||
        (i.body || "").toLowerCase().includes(q) ||
        (i.repo_full_name || "").toLowerCase().includes(q)
    );
  };

  const savedRepos = useMemo(() => {
    const repos = new Set();
    for (const i of issues) { if (i.bookmarked || i.claimed) repos.add(i.repo_full_name); }
    for (const i of priorityIssues) { if (i.bookmarked || i.claimed) repos.add(i.repo_full_name); }
    return repos;
  }, [issues, priorityIssues]);

  const savedLanguages = useMemo(() => {
    const langs = new Set();
    for (const i of issues) { if (i.bookmarked || i.claimed && i.language) langs.add(i.language); }
    for (const i of priorityIssues) { if (i.bookmarked || i.claimed && i.language) langs.add(i.language); }
    return langs;
  }, [issues, priorityIssues]);

  const sortIssuesWithSaved = (list, sortBy) => {
    if (sortBy !== "saved") return sortIssues(list, sortBy);
    const saved = list.filter((i) => savedRepos.has(i.repo_full_name));
    const sameLang = list.filter((i) => !savedRepos.has(i.repo_full_name) && savedLanguages.has(i.language));
    const rest = list.filter((i) => !savedRepos.has(i.repo_full_name) && !savedLanguages.has(i.language));
    return [...sortIssues(saved, "newest"), ...sortIssues(sameLang, "newest"), ...sortIssues(rest, "newest")];
  };

  const displayPriority = sortIssuesWithSaved(filterBySearch(priorityIssues), sortBy);
  const displayIssues = sortIssuesWithSaved(filterBySearch(issues), sortBy);

  return (
    <div className="flex min-h-screen">
      <Sidebar
        stats={stats}
        statsHistory={statsHistory}
        connected={connected}
        onPollNow={handlePollNow}
        onRefresh={handleRefresh}
        showToast={showToast}
      />

      <main className="flex-1 min-w-0 px-10 py-10 max-w-[920px]">
        <header className="mb-8 rise-in">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary-hover mb-2">
            Signal · Live Watch
          </p>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em] leading-none">
            Issue Feed
          </h1>
          <p className="text-[13px] text-ink-subtle mt-2.5">
            Unclaimed issues from 50+ star repos (last 2 days), surfaced in real time.
          </p>
        </header>

        <div className="mb-7 flex flex-wrap gap-2 items-center rounded-2xl border border-hairline bg-surface-1/70 p-3 shadow-card rise-in" style={{ animationDelay: "0.05s" }}>
          <div className="relative flex-1 min-w-[160px] max-w-[240px]">
            <svg className="absolute left-[8px] top-1/2 -translate-y-1/2 w-[14px] h-[14px] text-ink-tertiary pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" strokeLinecap="round" />
            </svg>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search issues..."
              className="w-full bg-canvas border border-hairline rounded-xl pl-[30px] pr-[12px] py-[8px] text-[13px] text-ink outline-none focus:border-primary-focus/40 placeholder:text-ink-tertiary"
            />
          </div>

          <select
            value={filterLang}
            onChange={(e) => setFilterLang(e.target.value)}
            className="select-mini"
          >
            {LANG_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="select-mini"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={filterDiff}
            onChange={(e) => setFilterDiff(e.target.value)}
            className="select-mini"
          >
            {DIFFICULTY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={filterLabel}
            onChange={(e) => setFilterLabel(e.target.value)}
            className="select-mini"
          >
            {LABEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="select-mini"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <span className="w-px h-6 bg-hairline shrink-0" />

          <ToggleChip checked={filterSaved} onChange={setFilterSaved} label="Saved" />
          <ToggleChip checked={filterPriority} onChange={setFilterPriority} label="Priority" />
          <ToggleChip checked={filterClaimed} onChange={setFilterClaimed} label="Claimed" />
          <ToggleChip checked={filterBounty} onChange={setFilterBounty} label="Bounty" />
          <ToggleChip checked={autoRefresh} onChange={setAutoRefresh} label="Live" live />

          <span className="w-px h-6 bg-hairline shrink-0" />

          <button
            onClick={requestNotifPerm}
            className={`toolbar-btn ${
              desktopNotif ? "text-primary border-primary/30 bg-primary/8" : "text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
            }`}
            title={desktopNotif ? "Notifications enabled" : "Enable desktop notifications"}
          >
            {desktopNotif ? "🔔 On" : "🔕 Off"}
          </button>

          <button
            onClick={() => { setSelectMode((v) => !v); setSelectedIds(new Set()); }}
            className={`toolbar-btn ${
              selectMode
                ? "text-primary border-primary/30 bg-primary/8"
                : "text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
            }`}
          >
            {selectMode ? "✕ Cancel" : "☐ Select"}
          </button>

          {selectMode && selectedIds.size > 0 && (
            <button
              onClick={handleBatchTriage}
              className="toolbar-btn text-white bg-primary/90 border-primary/60 hover:bg-primary"
            >
              Triage {selectedIds.size}
            </button>
          )}

          {savedSearches.length > 0 && (
            <select
              onChange={(e) => {
                const idx = parseInt(e.target.value);
                if (idx >= 0) handleLoadSearch(savedSearches[idx]);
              }}
              defaultValue=""
              className="select-mini text-[11px]"
            >
              <option value="" disabled>Load preset</option>
              {savedSearches.map((s, i) => (
                <option key={i} value={i}>{s.name}</option>
              ))}
            </select>
          )}

          <button
            onClick={handleSaveSearch}
            className="toolbar-btn text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
            title="Save current filters as preset"
          >
            💾 Save
          </button>

          <button
            onClick={handleExportMarkdown}
            className="toolbar-btn text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
            title="Export bookmarked issues as markdown"
          >
            📥 Export
          </button>

          <button
            onClick={() => {
              const pool = [...displayIssues, ...displayPriority];
              if (!pool.length) { showToast("No issues to pick from", "error"); return; }
              const pick = pool[Math.floor(Math.random() * pool.length)];
              window.open(pick.html_url, "_blank");
            }}
            className="toolbar-btn text-ink-muted border-hairline hover:text-ink hover:border-hairline-strong"
            title="Open a random issue in GitHub"
          >
            🎲 Random
          </button>
          <button
            onClick={async () => {
              try {
                const d = await fetchResume(7);
                setResumeMd(d.markdown || "");
                setShowResume(true);
                navigator.clipboard.writeText(d.markdown || "").then(() => showToast("Resume copied to clipboard!", "success"));
              } catch { showToast("Failed to generate resume", "error"); }
            }}
            className="toolbar-btn text-primary border-primary/20 bg-primary/5 hover:bg-primary/10"
          >
            📄 YC Resume
          </button>
        </div>

        {topPicks.length > 0 && (
          <section className="mb-8 rise-in" style={{ animationDelay: "0.04s" }}>
            <div className="flex items-center justify-between mb-3.5">
              <h2 className="text-[15px] font-semibold tracking-[-0.01em] flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-[18px] h-[18px] rounded-md bg-primary/15 text-primary text-[10px]">★</span>
                Top Picks for You
              </h2>
              <span className="text-[11px] text-ink-tertiary">
                Ranked by repo prestige · label quality · difficulty
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {topPicks.map((issue) => (
                <div key={`pick-${issue.id}`} className="rise-in" style={{ animationDelay: "0.08s" }}>
                  <IssueCard issue={issue} onTriageClick={handleTriageClick} showToast={showToast} onDismiss={handleDismiss} selectMode={false} selected={false} onToggleSelect={() => {}} />
                </div>
              ))}
            </div>
          </section>
        )}

        {displayPriority.length > 0 && (
          <section className="mb-8 rise-in" style={{ animationDelay: "0.06s" }}>
            <div className="flex items-center gap-3 mb-3.5">
              <span className="inline-flex items-center justify-center w-[18px] h-[18px] rounded-md bg-warning/15 text-warning">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.26 6.6.96-4.75 4.63 1.12 6.55L12 17.43l-5.87 2.97 1.12-6.55L2.5 9.22l6.6-.96L12 2z"/></svg>
              </span>
              <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
                Priority Issues
              </h2>
              <span className="text-[11px] text-ink-tertiary ml-auto tabular-nums">
                {displayPriority.length} issues from tracked repos &amp; orgs
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {displayPriority.map((issue) => (
                <div key={issue.id} className="rise-in" style={{ animationDelay: "0.08s" }}>
                  <IssueCard issue={issue} onTriageClick={handleTriageClick} showToast={showToast} onDismiss={handleDismiss} selectMode={selectMode} selected={selectedIds.has(issue.id)} onToggleSelect={toggleSelect} />
                </div>
              ))}
            </div>
          </section>
        )}

        {prs.length > 0 && (
          <section className="mb-8 rise-in" style={{ animationDelay: "0.07s" }}>
            <div className="flex items-center gap-3 mb-3.5">
              <span className="inline-flex items-center justify-center w-[18px] h-[18px] rounded-md bg-primary/15 text-primary">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M4 1a2 2 0 0 1 2 2v6.535a3.5 3.5 0 1 1-2 0V3a2 2 0 0 1 2-2zm2.5 8.535A3.5 3.5 0 0 1 8 5.5c1.5 0 2 1.5 2 1.5h.5a1 1 0 0 1 1 1V9a3.5 3.5 0 1 1-1 2.465V8h-.06A3.49 3.49 0 0 0 9.5 5.5c-.44 0-.8-.38-.85-.9A1.2 1.2 0 0 0 7.4 4.5h-.4A2 2 0 0 1 5 2.5v7.035zM5 12.5a1.5 1.5 0 1 0-3 0 1.5 1.5 0 0 0 3 0zM13 11.5a1.5 1.5 0 1 0-3 0 1.5 1.5 0 0 0 3 0z"/></svg>
              </span>
              <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
                PRs to Review
              </h2>
              <span className="text-[11px] text-ink-tertiary ml-auto tabular-nums">
                {prs.length} open PRs · community reviews
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {prs.slice(0, 10).map((pr) => (
                <div key={`pr-${pr.id}`} className="rise-in" style={{ animationDelay: "0.08s" }}>
                  <PrCard pr={pr} onReviewClick={(p) => setPanelPr(p)} showToast={showToast} />
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="flex items-center justify-between mb-3.5 mt-2">
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-ink-muted">
            General Feed
          </h2>
          <span className="text-[11px] text-ink-tertiary tabular-nums">
            {displayIssues.length} issues
          </span>
        </div>

        <div className="flex flex-col gap-3">
          {displayIssues.length === 0 ? (
            <div className="text-center py-20 text-ink-subtle border border-dashed border-hairline-strong rounded-2xl rise-in">
              <p className="text-[14px] mb-1">No issues match your filters</p>
              <span className="text-[12px] text-ink-tertiary">
                Try adjusting the search or filter criteria.
              </span>
            </div>
          ) : (
            displayIssues.map((issue, i) => (
              <div key={issue.id} className="rise-in" style={{ animationDelay: `${Math.min(i * 0.03, 0.24)}s` }}>
                <IssueCard issue={issue} onTriageClick={handleTriageClick} showToast={showToast} onDismiss={handleDismiss} selectMode={selectMode} selected={selectedIds.has(issue.id)} onToggleSelect={toggleSelect} />
              </div>
            ))
          )}
        </div>

        <div className={`h-16 w-full flex items-center justify-center gap-3 ${isFetchingPage ? "opacity-60" : ""}`}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || isFetchingPage}
            className="toolbar-btn text-ink-muted border-hairline hover:text-ink disabled:opacity-40 disabled:hover:text-ink-muted"
          >
            ← Prev
          </button>
          <span className="text-[12px] text-ink-tertiary tabular-nums">
            Page {page + 1} · {pageIssues.length} shown
            {isFetchingPage && " · loading…"}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={!hasNextPage || isFetchingPage}
            className="toolbar-btn text-ink-muted border-hairline hover:text-ink disabled:opacity-40 disabled:hover:text-ink-muted"
          >
            Next →
          </button>
        </div>
      </main>

      {panelIssue && (
        <TriagePanel issue={panelIssue} onClose={() => setPanelIssue(null)} showToast={showToast} />
      )}

      {panelPr && (
        <PrReviewPanel pr={panelPr} onClose={() => { setPanelPr(null); refreshPRs(); }} showToast={showToast} />
      )}

      {showResume && (
        <div className="fixed inset-0 bg-black/60 z-50" onClick={() => setShowResume(false)} />
      )}
      {showResume && (
        <div className="fixed top-0 right-0 w-[600px] max-w-[90vw] h-full bg-surface-1 border-l border-hairline z-50 flex flex-col shadow-2xl panel-in">
          <div className="flex items-center justify-between px-5 py-4 border-b border-hairline shrink-0">
            <h2 className="text-[14px] font-semibold">📄 YC Resume (Last 7 Days)</h2>
            <button onClick={() => setShowResume(false)} className="panel-close">✕</button>
          </div>
          <pre className="flex-1 overflow-y-auto p-5 text-[12px] text-ink-muted leading-relaxed whitespace-pre-wrap font-mono bg-canvas">{resumeMd}</pre>
          <div className="px-5 py-3 border-t border-hairline shrink-0">
            <button
              onClick={() => { navigator.clipboard.writeText(resumeMd); showToast("Resume copied!", "success"); }}
              className="text-xs font-medium px-[12px] py-[6px] rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors cursor-pointer border-none"
            >
              📋 Copy Markdown
            </button>
          </div>
        </div>
      )}

      <Toast message={toast.message} type={toast.type} action={toast.action} onClose={() => setToast({ message: "", type: "info", action: null })} />

      <div className="fixed top-5 right-5 z-[100] flex flex-col gap-3">
        {bountyPopups.map(({ id, issue }) => (
          <BountyPopup
            key={id}
            issue={issue}
            onClose={() => setBountyPopups((prev) => prev.filter((p) => p.id !== id))}
            onOpen={() => {
              setBountyPopups((prev) => prev.filter((p) => p.id !== id));
              window.open(issue.html_url, "_blank");
            }}
          />
        ))}
      </div>
    </div>
  );
}
