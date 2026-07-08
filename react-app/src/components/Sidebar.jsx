import { useState, useEffect, useCallback } from "react";
import {
  triggerPoll,
  fetchPreferences,
  savePreferences,
  fetchPriorityRepos,
  addPriorityRepo,
  removePriorityRepo,
} from "../api";

export default function Sidebar({ stats, connected, onRefresh }) {
  const [polling, setPolling] = useState(false);
  const [pollMsg, setPollMsg] = useState("");
  const [prefs, setPrefs] = useState(null);
  const [priorityRepos, setPriorityRepos] = useState([]);
  const [repoInput, setRepoInput] = useState("");

  useEffect(() => {
    fetchPreferences().then(setPrefs).catch(() => {});
    fetchPriorityRepos().then((d) => setPriorityRepos(d.repos || [])).catch(() => {});
  }, []);

  const handlePollNow = useCallback(async () => {
    setPolling(true);
    setPollMsg("Polling…");
    try {
      await triggerPoll();
      setPollMsg("Poll requested!");
    } catch {
      setPollMsg("Poll failed");
    }
    setPolling(false);
    setTimeout(() => setPollMsg(""), 3000);
  }, []);

  const handleSavePrefs = useCallback(async () => {
    if (!prefs) return;
    try {
      await savePreferences(prefs);
    } catch {}
  }, [prefs]);

  const handleAddRepo = useCallback(async () => {
    const name = repoInput.trim();
    if (!name) return;
    try {
      const result = await addPriorityRepo(name);
      setPriorityRepos((prev) => [...prev, result]);
      setRepoInput("");
    } catch {}
  }, [repoInput]);

  const handleRemoveRepo = useCallback(async (id) => {
    try {
      await removePriorityRepo(id);
      setPriorityRepos((prev) => prev.filter((r) => r.id !== id));
    } catch {}
  }, []);

  return (
    <aside className="w-[240px] shrink-0 h-screen sticky top-0 flex flex-col gap-4 p-4 border-r border-hairline bg-canvas overflow-y-auto">
      {/* Logo */}
      <div className="flex items-center gap-2 pb-3 border-b border-hairline">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="text-primary shrink-0">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
        </svg>
        <span className="text-[15px] font-semibold tracking-[-0.02em]">Issue Triage</span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2 bg-surface-1 border border-hairline rounded-md p-[10px]">
          <div className="text-[20px] font-semibold tracking-[-0.03em] leading-tight">
            {stats?.total ?? 0}
          </div>
          <div className="text-[11px] font-medium text-ink-subtle uppercase tracking-[0.04em] mt-[2px]">
            Total Issues
          </div>
        </div>
        <div className="bg-surface-1 border border-hairline rounded-md p-[10px]">
          <div className="text-[20px] font-semibold tracking-[-0.03em] leading-tight">
            {stats?.complete ?? 0}
          </div>
          <div className="text-[11px] font-medium text-ink-subtle uppercase tracking-[0.04em] mt-[2px]">
            Triaged
          </div>
        </div>
        <div className="bg-surface-1 border border-hairline rounded-md p-[10px]">
          <div className="text-[20px] font-semibold tracking-[-0.03em] leading-tight">
            {stats?.pending ?? 0}
          </div>
          <div className="text-[11px] font-medium text-ink-subtle uppercase tracking-[0.04em] mt-[2px]">
            Pending
          </div>
        </div>
      </div>

      {/* Poll status */}
      <div className="bg-surface-1 border border-hairline rounded-md p-[10px]">
        <div className="text-[11px] font-medium text-ink-subtle uppercase tracking-[0.04em]">
          Last Poll
        </div>
        <div className="text-[12px] text-ink-muted mt-[2px] leading-snug">
          {stats?.last_poll_message || "Waiting..."}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex flex-col gap-[6px]">
        <button
          onClick={handlePollNow}
          disabled={polling}
          className="w-full text-[13px] font-medium px-[14px] py-[7px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors border-none cursor-pointer disabled:opacity-50"
        >
          {polling ? "Polling…" : "Poll Now"}
        </button>
        <button
          onClick={onRefresh}
          className="w-full text-[13px] font-medium px-[14px] py-[7px] rounded-md bg-surface-1 text-ink border border-hairline hover:bg-surface-2 hover:border-hairline-strong transition-colors cursor-pointer"
        >
          Refresh
        </button>
        {pollMsg && (
          <span className="text-[11px] text-primary text-center">{pollMsg}</span>
        )}
      </div>

      {/* Priority Repos */}
      <details className="bg-surface-1 border border-hairline rounded-md [&>summary]:list-none">
        <summary className="text-[12px] font-semibold text-ink-muted px-[10px] py-[8px] cursor-pointer hover:text-ink transition-colors select-none flex items-center justify-between">
          Priority Repos
          <svg width="12" height="12" viewBox="0 0 12 12" className="text-ink-tertiary details-open:rotate-180 transition-transform">
            <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </summary>
        <div className="px-[10px] pb-[10px] space-y-[6px]">
          <div style={{ display: "flex", gap: "6px" }}>
            <input
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddRepo()}
              placeholder="owner/repo"
              className="flex-1 bg-canvas border border-hairline rounded-md px-[8px] py-[5px] text-[11px] text-ink outline-none placeholder:text-ink-tertiary"
            />
            <button
              onClick={handleAddRepo}
              className="shrink-0 text-xs font-medium px-[8px] py-[4px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors border-none cursor-pointer"
            >
              +
            </button>
          </div>
          <div className="text-[11px] text-ink-muted space-y-[2px] max-h-[120px] overflow-y-auto">
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
      <details className="bg-surface-1 border border-hairline rounded-md [&>summary]:list-none">
        <summary className="text-[12px] font-semibold text-ink-muted px-[10px] py-[8px] cursor-pointer hover:text-ink transition-colors select-none flex items-center justify-between">
          Preferences
          <svg width="12" height="12" viewBox="0 0 12 12" className="text-ink-tertiary details-open:rotate-180 transition-transform">
            <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </summary>
        <div className="px-[10px] pb-[10px] space-y-[6px]">
          <label className="block text-[11px] text-ink-muted">
            Languages (comma-sep)
            <input
              value={prefs?.languages?.join(",") || ""}
              onChange={(e) => setPrefs((p) => ({ ...p, languages: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) }))}
              className="mt-[2px] w-full bg-canvas border border-hairline rounded-md px-[8px] py-[5px] text-[11px] text-ink outline-none"
            />
          </label>
          <label className="block text-[11px] text-ink-muted">
            Labels (comma-sep)
            <input
              value={prefs?.labels?.join(",") || ""}
              onChange={(e) => setPrefs((p) => ({ ...p, labels: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) }))}
              className="mt-[2px] w-full bg-canvas border border-hairline rounded-md px-[8px] py-[5px] text-[11px] text-ink outline-none"
            />
          </label>
          <label className="block text-[11px] text-ink-muted">
            Min repo stars
            <input
              type="number"
              value={prefs?.min_stars ?? 0}
              onChange={(e) => setPrefs((p) => ({ ...p, min_stars: parseInt(e.target.value) || 0 }))}
              min="0"
              className="mt-[2px] w-full bg-canvas border border-hairline rounded-md px-[8px] py-[5px] text-[11px] text-ink outline-none"
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
            className="w-full text-xs font-medium px-[10px] py-[5px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors border-none cursor-pointer"
          >
            Save Preferences
          </button>
        </div>
      </details>

      {/* Connection status */}
      <div className="mt-auto flex items-center gap-[6px] pt-3 border-t border-hairline">
        <span
          className={`w-[6px] h-[6px] rounded-full transition-colors duration-300 shrink-0
            ${connected ? "bg-success" : "bg-ink-tertiary"}
          `}
        />
        <span className="text-[11px] text-ink-subtle">
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>
    </aside>
  );
}
