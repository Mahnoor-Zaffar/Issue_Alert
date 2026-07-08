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

const PAGE_SIZE = 30;

export default function App() {
  const [issues, setIssues] = useState([]);
  const [priorityIssues, setPriorityIssues] = useState([]);
  const [stats, setStats] = useState(null);
  const [statsHistory, setStatsHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const [panelIssue, setPanelIssue] = useState(null);
  const [toast, setToast] = useState({ message: "", type: "info" });
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const [filterLang, setFilterLang] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDiff, setFilterDiff] = useState("");
  const [filterLabel, setFilterLabel] = useState("");
  const [filterSaved, setFilterSaved] = useState(false);
  const [filterPriority, setFilterPriority] = useState(false);

  const loadRef = useRef(0);

  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type });
  }, []);

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
    }, []),
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

  // Keyboard shortcuts
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

        <div className="flex flex-wrap gap-2 mb-5">
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

          <label className="flex items-center gap-[5px] text-[12px] text-ink-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filterSaved}
              onChange={(e) => setFilterSaved(e.target.checked)}
              className="accent-primary"
            />
            Saved only
          </label>

          <label className="flex items-center gap-[5px] text-[12px] text-ink-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filterPriority}
              onChange={(e) => setFilterPriority(e.target.checked)}
              className="accent-primary"
            />
            Priority only
          </label>
        </div>

        {priorityIssues.length > 0 && (
          <div className="mb-5">
            <h2 className="text-[15px] font-semibold tracking-[-0.01em] flex items-center gap-2 mb-3">
              <span className="w-[6px] h-[6px] rounded-full bg-warning animate-pulse" />
              Priority Issues
            </h2>
            <div className="flex flex-col gap-[10px]">
              {priorityIssues.map((issue) => (
                <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} showToast={showToast} />
              ))}
            </div>
          </div>
        )}

        <h2 className="text-[15px] font-semibold tracking-[-0.01em] mb-3 text-ink-muted">
          General Feed
        </h2>

        <div className="flex flex-col gap-[10px]">
          {issues.length === 0 ? (
            <div className="text-center py-16 text-ink-subtle">
              <p className="text-[14px] mb-1">Waiting for issues...</p>
              <span className="text-[12px] text-ink-tertiary">
                The daemon polls GitHub every 60s.
              </span>
            </div>
          ) : (
            issues.map((issue) => (
              <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} showToast={showToast} />
            ))
          )}
        </div>

        {hasMore && issues.length > 0 && (
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

      <Toast message={toast.message} type={toast.type} onClose={() => setToast({ message: "", type: "info" })} />
    </div>
  );
}
