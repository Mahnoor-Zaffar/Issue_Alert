export default function Sidebar({ stats, connected, onPollNow, onRefresh }) {
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
          onClick={onPollNow}
          className="w-full text-[13px] font-medium px-[14px] py-[7px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors border-none cursor-pointer"
        >
          Poll Now
        </button>
        <button
          onClick={onRefresh}
          className="w-full text-[13px] font-medium px-[14px] py-[7px] rounded-md bg-surface-1 text-ink border border-hairline hover:bg-surface-2 hover:border-hairline-strong transition-colors cursor-pointer"
        >
          Refresh
        </button>
      </div>

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
