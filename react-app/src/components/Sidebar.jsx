import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchPreferences,
  savePreferences,
  fetchPriorityRepos,
  addPriorityRepo,
  removePriorityRepo,
  fetchRateLimit,
  fetchDaemonLog,
} from "../api";

export default function Sidebar({ stats, statsHistory, connected, onPollNow, onRefresh, showToast }) {
  const [polling, setPolling] = useState(false);
  const [prefs, setPrefs] = useState(null);
  const [priorityRepos, setPriorityRepos] = useState([]);
  const [repoInput, setRepoInput] = useState("");
  const [rateLimit, setRateLimit] = useState(null);
  const [logLines, setLogLines] = useState([]);
  const [logExpanded, setLogExpanded] = useState(true);
  const logRef = useRef(null);

  useEffect(() => {
    fetchPreferences().then(setPrefs).catch(() => {});
    fetchPriorityRepos().then((d) => setPriorityRepos(d.repos || [])).catch(() => {});
    const loadRL = () => fetchRateLimit().then(setRateLimit).catch(() => {});
    loadRL();
    const iv = setInterval(loadRL, 30000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const load = () => fetchDaemonLog(40).then((d) => setLogLines(d.lines || [])).catch(() => {});
    load();
    const iv = setInterval(load, 4000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines, logExpanded]);

  const handlePollNow = useCallback(async () => {
    setPolling(true);
    try {
      await onPollNow();
    } finally {
      setPolling(false);
    }
  }, [onPollNow]);

  const handleSavePrefs = useCallback(async () => {
    if (!prefs) return;
    try {
      await savePreferences(prefs);
      showToast("Preferences saved", "success");
    } catch {
      showToast("Failed to save preferences", "error");
    }
  }, [prefs, showToast]);

  const handleAddRepo = useCallback(async () => {
    const name = repoInput.trim();
    if (!name) return;
    try {
      const result = await addPriorityRepo(name);
      setPriorityRepos((prev) => [...prev, result]);
      setRepoInput("");
      showToast(`Added ${name}`, "success");
    } catch {
      showToast("Failed to add repo", "error");
    }
  }, [repoInput, showToast]);

  const handleRemoveRepo = useCallback(async (id) => {
    try {
      await removePriorityRepo(id);
      setPriorityRepos((prev) => prev.filter((r) => r.id !== id));
    } catch {
      showToast("Failed to remove repo", "error");
    }
  }, [showToast]);

  const remaining = rateLimit?.remaining;
  const ratePct = remaining != null ? Math.round((remaining / 5000) * 100) : null;

  return (
    <aside className="w-[272px] shrink-0 h-screen sticky top-0 flex flex-col p-4 border-r border-hairline bg-canvas overflow-y-auto gap-[9px]">
      {/* Logo */}
      <div className="flex items-center gap-2.5 pb-3.5 border-b border-hairline">
        <span className="w-8 h-8 rounded-[10px] bg-primary/12 text-primary flex items-center justify-center shrink-0">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
          </svg>
        </span>
        <div className="min-w-0">
          <div className="text-[14px] font-semibold tracking-[-0.02em] leading-none">Issue Console</div>
          <div className="text-[10px] text-ink-tertiary mt-[3px]">daemon · triage · watch</div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex gap-[6px]">
        <button
          onClick={handlePollNow}
          disabled={polling}
          className="flex-1 text-[12px] font-semibold px-3 py-[8px] rounded-[10px] bg-primary text-[#04230f] hover:bg-primary-hover transition-colors border-none cursor-pointer disabled:opacity-50"
        >
          {polling ? "Polling…" : "Poll Now"}
        </button>
        <button
          onClick={onRefresh}
          className="flex-1 text-[12px] font-medium px-3 py-[8px] rounded-[10px] bg-surface-1 text-ink-muted border border-hairline hover:bg-surface-2 hover:border-hairline-strong hover:text-ink transition-colors cursor-pointer"
        >
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-[6px]">
        <StatCell label="Total" value={stats?.total ?? 0} accent="text-ink" />
        <StatCell label="Triaged" value={stats?.complete ?? 0} accent="text-success" />
        <StatCell label="Pending" value={stats?.pending ?? 0} accent="text-warning" />
      </div>

      {/* API activity + activity sparkline */}
      {(rateLimit && remaining != null) && (
        <div className="rounded-[12px] border border-hairline bg-surface-1/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">API Rate</span>
            <span className={`text-[11px] font-semibold tabular-nums ${ratePct <= 20 ? "text-error" : "text-ink-muted"}`}>
              {remaining}<span className="text-ink-tertiary">/5000</span>
            </span>
          </div>
          <div className="h-[6px] rounded-full bg-hairline overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${ratePct > 20 ? "bg-primary" : "bg-error"}`}
              style={{ width: `${ratePct}%` }}
            />
          </div>
          {stats?.last_poll_message && (
            <div className="mt-2 text-[10px] text-ink-subtle leading-snug line-clamp-2">
              {stats.last_poll_message}
              {stats?.last_poll_fetched != null && (
                <span className="text-ink-tertiary"> · {stats.last_poll_fetched} fetched{stats.last_poll_new ? `, ${stats.last_poll_new} new` : ""}</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Daemon console — always visible */}
      <div className="rounded-[12px] border border-hairline bg-surface-1/60 overflow-hidden">
        <button
          onClick={() => setLogExpanded((v) => !v)}
          className="w-full flex items-center gap-2 px-3 py-2.5 cursor-pointer border-none bg-transparent hover:bg-surface-2/60 transition-colors"
        >
          <span className={`w-[6px] h-[6px] rounded-full bg-success live-dot`} />
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">Daemon Console</span>
          <span className="ml-auto text-[10px] text-ink-tertiary tabular-nums">{logLines.length}</span>
          <svg width="10" height="10" viewBox="0 0 12 12" className={`text-ink-tertiary transition-transform ${logExpanded ? "rotate-180" : ""}`}>
            <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        {logExpanded && (
          <div ref={logRef} className="max-h-[210px] overflow-y-auto border-t border-hairline px-3 py-2 text-[10px] text-ink-muted leading-[1.65] font-mono bg-canvas/60">
            {logLines.length === 0 ? (
              <span className="text-ink-tertiary">Awaiting daemon activity…</span>
            ) : (
              logLines.map((line, i) => {
                const color =
                  /error|failed|exception|traceback/i.test(line) ? "text-error" :
                  /success|complete|done|200|201/i.test(line) ? "text-success" :
                  /httpx|request|started|fetch/i.test(line) ? "text-primary-hover" :
                  "text-ink-muted";
                return (
                  <div key={i} className={`truncate hover:text-ink transition-colors ${color}`}>
                    {line}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Liveness / connection */}
      <div className="flex items-center gap-[7px] pl-1">
        <span
          className={`w-[7px] h-[7px] rounded-full transition-colors duration-300 ${
            connected ? "bg-success live-dot" : "bg-error"
          }`}
        />
        <span className="text-[11px] text-ink-subtle tabular-nums">
          {connected ? "Daemon connected · live" : "Daemon disconnected"}
        </span>
      </div>

      {/* Priority Repos */}
      <details className="rounded-[12px] border border-hairline bg-surface-1/60 [&>summary]:list-none overflow-hidden">
        <summary className="flex items-center justify-between text-[11px] font-semibold text-ink-muted px-3 py-2.5 cursor-pointer hover:text-ink transition-colors select-none">
          <span>Priority Repos</span>
          <svg width="10" height="10" viewBox="0 0 12 12" className="text-ink-tertiary"><path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </summary>
        <div className="px-3 pb-3 space-y-1.5 border-t border-hairline pt-2">
          <div style={{ display: "flex", gap: "6px" }}>
            <input
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddRepo()}
              placeholder="owner/repo"
              className="flex-1 bg-canvas border border-hairline rounded-[8px] px-2 py-[6px] text-[11px] text-ink outline-none focus:border-primary-focus/50 placeholder:text-ink-tertiary"
            />
            <button
              onClick={handleAddRepo}
              className="shrink-0 text-[13px] font-medium w-[28px] rounded-[8px] bg-primary text-[#04230f] hover:bg-primary-hover transition-colors border-none cursor-pointer"
            >
              +
            </button>
          </div>
          <div className="text-[11px] text-ink-muted space-y-[2px] max-h-[110px] overflow-y-auto text-[10.5px]">
            {priorityRepos.length === 0 ? (
              <span className="text-ink-tertiary">No priority repos</span>
            ) : (
              priorityRepos.map((r) => (
                <div key={r.id} className="flex items-center justify-between py-[2px]">
                  <span className="truncate">{r.full_name}</span>
                  <button
                    onClick={() => handleRemoveRepo(r.id)}
                    className="shrink-0 text-ink-tertiary hover:text-error transition-colors bg-transparent border-none cursor-pointer text-[12px] leading-none px-[4px]"
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </details>

      {/* Preferences */}
      <details className="rounded-[12px] border border-hairline bg-surface-1/60 [&>summary]:list-none overflow-hidden">
        <summary className="flex items-center gap-2 text-[11px] font-semibold text-ink-muted px-3 py-2.5 cursor-pointer hover:text-ink transition-colors select-none">
          <span>Preferences</span>
          <svg width="10" height="10" viewBox="0 0 12 12" className="text-ink-tertiary ml-auto"><path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </summary>
        <div className="px-3 pb-3 space-y-2 border-t border-hairline pt-2">
          <label className="block text-[11px] text-ink-muted">
            Languages (comma-sep)
            <input
              value={prefs?.languages?.join(",") || ""}
              onChange={(e) => setPrefs((p) => ({ ...p, languages: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) }))}
              className="mt-[2px] w-full bg-canvas border border-hairline rounded-[8px] px-2 py-[6px] text-[11px] text-ink outline-none focus:border-primary-focus/50"
            />
          </label>
          <label className="block text-[11px] text-ink-muted">
            Labels (comma-sep)
            <input
              value={prefs?.labels?.join(",") || ""}
              onChange={(e) => setPrefs((p) => ({ ...p, labels: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) }))}
              className="mt-[2px] w-full bg-canvas border border-hairline rounded-[8px] px-2 py-[6px] text-[11px] text-ink outline-none focus:border-primary-focus/50"
            />
          </label>
          <label className="flex items-center gap-[5px] text-[11px] text-ink-muted cursor-pointer">
            <input
              type="checkbox"
              checked={prefs?.show_dismissed ?? false}
              onChange={(e) => setPrefs((p) => ({ ...p, show_dismissed: e.target.checked }))}
              className="accent-primary"
            />
            Show dismissed
          </label>
          <button
            onClick={handleSavePrefs}
            className="w-full text-[12px] font-medium px-3 py-[7px] rounded-[8px] bg-primary text-white hover:bg-primary-hover transition-colors border-none cursor-pointer"
          >
            Save Preferences
          </button>
        </div>
      </details>
    </aside>
  );
}

function StatCell({ label, value, accent = "text-ink" }) {
  return (
    <div className="rounded-[12px] border border-hairline bg-surface-1/60 px-3 py-2.5">
      <div className={`text-[17px] font-semibold tracking-[-0.03em] leading-tight tabular-nums ${accent}`}>
        {value ?? 0}
      </div>
      <div className="text-[9.5px] font-medium text-ink-subtle uppercase tracking-[0.08em] mt-[2px]">
        {label}
      </div>
    </div>
  );
}
