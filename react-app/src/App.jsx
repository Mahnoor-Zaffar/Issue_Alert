import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "./components/Sidebar";
import IssueCard from "./components/IssueCard";
import TriagePanel from "./components/TriagePanel";
import { useSSE } from "./useSSE";
import { fetchIssues, fetchStats, fetchStatsHistory } from "./api";

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

export default function App() {
  const [issues, setIssues] = useState([]);
  const [priorityIssues, setPriorityIssues] = useState([]);
  const [stats, setStats] = useState(null);
  const [connected, setConnected] = useState(false);
  const [panelIssue, setPanelIssue] = useState(null);

  // Filters
  const [filterLang, setFilterLang] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDiff, setFilterDiff] = useState("");
  const [filterSaved, setFilterSaved] = useState(false);
  const [filterPriority, setFilterPriority] = useState(false);

  const loadRef = useRef(0);

  const loadIssues = useCallback(async () => {
    const id = ++loadRef.current;
    const params = {};
    if (filterLang) params.language = filterLang;
    if (filterStatus) params.status = filterStatus;
    if (filterDiff) params.difficulty = filterDiff;
    if (filterSaved) params.bookmarked_only = "true";
    if (filterPriority) params.is_priority = "true";

    try {
      const data = await fetchIssues(params);
      if (id !== loadRef.current) return;
      const list = data.issues || [];
      setPriorityIssues(list.filter((i) => i.is_priority));
      setIssues(list.filter((i) => !i.is_priority));
    } catch {}
  }, [filterLang, filterStatus, filterDiff, filterSaved, filterPriority]);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
    } catch {}
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

  // Initial load
  useEffect(() => {
    loadIssues();
    loadStats();
    fetchStatsHistory().then((d) => {
      // Could render sparkline here
    });
  }, []);

  // Reload when filters change
  useEffect(() => {
    loadIssues();
  }, [filterLang, filterStatus, filterDiff, filterSaved, filterPriority]);

  const handleRefresh = useCallback(() => {
    loadIssues();
    loadStats();
  }, [loadIssues, loadStats]);

  const handleTriageClick = useCallback(
    (issue, retriage = false) => {
      setPanelIssue(issue);
    },
    []
  );

  return (
    <div className="flex min-h-screen">
      <Sidebar
        stats={stats}
        connected={connected}
        onRefresh={handleRefresh}
      />

      <main className="flex-1 px-10 py-7 max-w-[860px]">
        {/* Header */}
        <div className="mb-5">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">Live Issue Feed</h1>
          <p className="text-[13px] text-ink-subtle mt-[2px]">
            Unclaimed issues from 1000+ star repos (last 7 days).
          </p>
        </div>

        {/* Toolbar */}
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

        {/* Priority section */}
        {priorityIssues.length > 0 && (
          <div className="mb-5">
            <h2 className="text-[15px] font-semibold tracking-[-0.01em] flex items-center gap-2 mb-3">
              <span className="w-[6px] h-[6px] rounded-full bg-warning animate-pulse" />
              Priority Issues
            </h2>
            <div className="flex flex-col gap-[10px]">
              {priorityIssues.map((issue) => (
                <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} />
              ))}
            </div>
          </div>
        )}

        {/* General feed */}
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
              <IssueCard key={issue.id} issue={issue} onTriageClick={handleTriageClick} />
            ))
          )}
        </div>
      </main>

      {/* Triage panel */}
      {panelIssue && (
        <TriagePanel issue={panelIssue} onClose={() => setPanelIssue(null)} />
      )}
    </div>
  );
}
