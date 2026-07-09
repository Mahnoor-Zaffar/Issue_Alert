import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "./components/Sidebar";
import IssueCard from "./components/IssueCard";
import TriagePanel from "./components/TriagePanel";
import Toast from "./components/Toast";
import { useSSE } from "./useSSE";
import { fetchIssues, fetchStats, fetchStatsHistory, triggerPoll } from "./api";

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

const SORT_OPTIONS = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "stars_desc", label: "Most Stars" },
  { value: "stars_asc", label: "Least Stars" },
  { value: "repo", label: "Repo A-Z" },
];

const PAGE_SIZE = 30;

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

export default function App() {
  const initial = readFilters();
  const [issues, setIssues] = useState([]);
  const [priorityIssues, setPriorityIssues] = useState([]);
  const [stats, setStats] = useState(null);
  const [statsHistory, setStatsHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const [panelIssue, setPanelIssue] = useState(null);
  const [toast, setToast] = useState({ message: "", type: "info", action: null });
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const [filterLang, setFilterLang] = useState(initial.filterLang);
  const [filterStatus, setFilterStatus] = useState(initial.filterStatus);
  const [filterDiff, setFilterDiff] = useState(initial.filterDiff);
  const [filterLabel, setFilterLabel] = useState(initial.filterLabel);
  const [filterSaved, setFilterSaved] = useState(initial.filterSaved);
  const [filterPriority, setFilterPriority] = useState(initial.filterPriority);
  const [searchQuery, setSearchQuery] = useState(initial.searchQuery);
  const [sortBy, setSortBy] = useState(initial.sortBy);

  const loadRef = useRef(0);
  const knownIds = useRef(new Set());

  const showToast = useCallback((message, type = "info", action = null) => {
    setToast({ message, type, action });
  }, []);

  useEffect(() => {
    writeFilters({ filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, searchQuery, sortBy });
  }, [filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, searchQuery, sortBy]);

  const loadIssues = useCallback(async (append = false) => {
    const id = ++loadRef.current;
    const params = { limit: PAGE_SIZE };
    if (!append) params.offset = 0;
    else params.offset = offset;
    if (filterLang) params.language = filterLang;
    if (filterStatus) params.status = filterStatus;
    if (filterDiff) params.difficulty = filterDiff;
    if (filterLabel) params.label = filterLabel;
    if (filterSaved) params.bookmarked_only = "true";
    if (filterPriority) params.is_priority = "true";

    try {
      const data = await fetchIssues(params);
      if (id !== loadRef.current) return;
      const list = data.issues || [];
      setHasMore(list.length >= PAGE_SIZE);
      if (append) {
        setIssues((prev) => [...prev, ...list.filter((i) => !i.is_priority)]);
      } else {
        setPriorityIssues(list.filter((i) => i.is_priority));
        setIssues(list.filter((i) => !i.is_priority));
        setOffset(0);
      }
      list.forEach((i) => knownIds.current.add(i.id));
    } catch {
      showToast("Failed to load issues", "error");
    }
  }, [filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority, offset, showToast]);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatsHistory().then((d) => setStatsHistory(d.history || [])).catch(() => {});
  }, []);

  useSSE({
    onIssueUpdate: useCallback((updated) => {
      const isNew = !knownIds.current.has(updated.id);
      knownIds.current.add(updated.id);

      if (isNew && updated.is_priority) {
        playPriorityChime();
        showToast(`🔔 New priority: ${updated.title.slice(0, 60)}`, "info");
      }

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
    }, [showToast]),
    onStatsUpdate: useCallback((s) => setStats(s), []),
    onConnected: useCallback((c) => setConnected(c), []),
  });

  useEffect(() => {
    loadIssues();
    loadStats();
  }, []);

  useEffect(() => {
    loadIssues();
    setOffset(0);
  }, [filterLang, filterStatus, filterDiff, filterLabel, filterSaved, filterPriority]);

  const handleRefresh = useCallback(() => {
    loadIssues();
    loadStats();
    showToast("Refreshed", "success");
  }, [loadIssues, loadStats, showToast]);

  const handlePollNow = useCallback(async () => {
    try {
      await triggerPoll();
      showToast("Poll requested — daemon will check shortly", "success");
    } catch {
      showToast("Poll request failed", "error");
    }
  }, [showToast]);

  const handleLoadMore = useCallback(() => {
    setOffset((prev) => prev + PAGE_SIZE);
    loadIssues(true);
  }, [loadIssues]);

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
          loadIssues();
        }).catch(() => {
          showToast("Undo failed", "error");
        });
      },
    });
  }, [showToast, loadIssues]);

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

  const displayPriority = sortIssues(filterBySearch(priorityIssues), sortBy);
  const displayIssues = sortIssues(filterBySearch(issues), sortBy);

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

      <main className="flex-1 px-10 py-7 max-w-[860px]">
        <div className="mb-5">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">Live Issue Feed</h1>
          <p className="text-[13px] text-ink-subtle mt-[2px]">
            Unclaimed issues from 1000+ star repos (last 7 days).
          </p>
        </div>

        <div className="flex flex-wrap gap-2 mb-5 items-center">
          <div className="relative flex-1 min-w-[160px] max-w-[240px]">
            <svg className="absolute left-[8px] top-1/2 -translate-y-1/2 w-[14px] h-[14px] text-ink-tertiary pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" strokeLinecap="round" />
            </svg>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search issues..."
              className="w-full bg-surface-1 border border-hairline rounded-md pl-[28px] pr-[10px] py-[7px] text-[12px] text-ink outline-none placeholder:text-ink-tertiary"
            />
          </div>

          <select
            value={filterLang}
            onChange={(e) => setFilterLang(e.target.value)}
            className="bg-surface-1 border border-hairline rounded-md px-[10px] py-[7px] text-[12px] text-ink outline-none cursor-pointer"
          >
            <option value="">All languages</option>
            <option value="javascript">JavaScript</option>
            <option value="python">Python</option>
            <option value="go">Go</option>
            <option value="rust">Rust</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="bg-surface-1 border border-hairline rounded-md px-[10px] py-[7px] text-[12px] text-ink outline-none cursor-pointer"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={filterDiff}
            onChange={(e) => setFilterDiff(e.target.value)}
            className="bg-surface-1 border border-hairline rounded-md px-[10px] py-[7px] text-[12px] text-ink outline-none cursor-pointer"
          >
            {DIFFICULTY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={filterLabel}
            onChange={(e) => setFilterLabel(e.target.value)}
            className="bg-surface-1 border border-hairline rounded-md px-[10px] py-[7px] text-[12px] text-ink outline-none cursor-pointer"
          >
            {LABEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="bg-surface-1 border border-hairline rounded-md px-[10px] py-[7px] text-[12px] text-ink outline-none cursor-pointer"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          <label className="flex items-center gap-[5px] text-[12px] text-ink-muted cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={filterSaved}
              onChange={(e) => setFilterSaved(e.target.checked)}
              className="accent-primary"
            />
            Saved
          </label>

          <label className="flex items-center gap-[5px] text-[12px] text-ink-muted cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={filterPriority}
              onChange={(e) => setFilterPriority(e.target.checked)}
              className="accent-primary"
            />
            Priority
          </label>
        </div>

        {displayPriority.length > 0 && (
          <div className="mb-5">
            <h2 className="text-[15px] font-semibold tracking-[-0.01em] flex items-center gap-2 mb-3">
              <span className="w-[6px] h-[6px] rounded-full bg-warning animate-pulse" />
              Priority Issues
            </h2>
            <div className="flex flex-col gap-[10px]">
              {displayPriority.map((issue) => (
                <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} showToast={showToast} onDismiss={handleDismiss} />
              ))}
            </div>
          </div>
        )}

        <h2 className="text-[15px] font-semibold tracking-[-0.01em] mb-3 text-ink-muted">
          General Feed
        </h2>

        <div className="flex flex-col gap-[10px]">
          {displayIssues.length === 0 ? (
            <div className="text-center py-16 text-ink-subtle">
              <p className="text-[14px] mb-1">No issues match your filters</p>
              <span className="text-[12px] text-ink-tertiary">
                Try adjusting the search or filter criteria.
              </span>
            </div>
          ) : (
            displayIssues.map((issue) => (
              <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} showToast={showToast} onDismiss={handleDismiss} />
            ))
          )}
        </div>

        {hasMore && displayIssues.length > 0 && (
          <button
            onClick={handleLoadMore}
            className="w-full mt-4 text-[13px] font-medium px-[14px] py-[9px] rounded-md bg-surface-1 text-ink-muted border border-hairline hover:bg-surface-2 hover:text-ink transition-colors cursor-pointer"
          >
            Load More
          </button>
        )}
      </main>

      {panelIssue && (
        <TriagePanel issue={panelIssue} onClose={() => setPanelIssue(null)} showToast={showToast} />
      )}

      <Toast message={toast.message} type={toast.type} action={toast.action} onClose={() => setToast({ message: "", type: "info", action: null })} />
    </div>
  );
}
