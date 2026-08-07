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
    <div className="w-[360px] rounded-xl border-2 border-success/50 bg-success/10 backdrop-blur-md shadow-2xl overflow-hidden animate-[fadeIn_0.25s_ease-out]">
      <div className="bg-success/20 px-4 py-2.5 flex items-center justify-between">
        <span className="text-[12px] font-bold text-success tracking-wide flex items-center gap-2">
          <span className="text-[15px]">💰</span> New Bounty Issue — {amount}
        </span>
        <button
          onClick={onClose}
          className="w-[22px] h-[22px] flex items-center justify-center rounded-md text-success hover:bg-success/20 transition-colors border-none cursor-pointer"
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
            className="flex-1 text-xs font-semibold px-[12px] py-[7px] rounded-md bg-success text-white hover:bg-success/80 transition-colors border-none cursor-pointer"
          >
            Open Issue
          </button>
          <button
            onClick={onClose}
            className="text-xs font-medium px-[12px] py-[7px] rounded-md bg-surface-1 text-ink-muted border border-hairline hover:text-ink transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
