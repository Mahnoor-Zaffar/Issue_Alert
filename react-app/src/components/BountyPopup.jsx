import { useEffect } from "react";

export default function BountyPopup({ issue, onClose, onOpen }) {
  useEffect(() => {
    const t = setTimeout(onClose, 8000);
    return () => clearTimeout(t);
  }, [onClose]);

  const amount = issue.bounty_amount
    ? `$${Number(issue.bounty_amount).toLocaleString()}`
    : "Bounty";

  return (
    <div className="w-[360px] rounded-2xl border border-success/40 bg-surface-1/90 backdrop-blur-md shadow-pop overflow-hidden rise-in">
      <div className="bg-success/12 px-4 py-2.5 flex items-center justify-between border-b border-success/20">
        <span className="text-[12px] font-bold text-success tracking-wide flex items-center gap-2">
          <span className="w-[18px] h-[18px] rounded-md bg-success/20 text-white flex items-center justify-center text-[10px]">$</span>
          New Bounty Issue — {amount}
        </span>
        <button
          onClick={onClose}
          className="panel-close shrink-0 !w-[22px] !h-[22px] text-success border-success/20 hover:bg-success/15 hover:text-success"
        >
          ✕
        </button>
      </div>
      <div className="px-4 py-3">
        <div className="text-[11px] text-ink-muted mb-1">{issue.repo_full_name}</div>
        <div className="text-[13px] font-semibold text-ink leading-snug line-clamp-2 mb-3">
          {issue.title}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onOpen}
            className="flex-1 text-xs font-semibold px-[12px] py-[7px] rounded-lg bg-success text-white hover:bg-success/80 transition-colors border-none cursor-pointer"
          >
            Open Issue
          </button>
          <button
            onClick={onClose}
            className="text-xs font-medium px-[12px] py-[7px] rounded-lg bg-surface-1 text-ink-muted border border-hairline hover:text-ink transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
