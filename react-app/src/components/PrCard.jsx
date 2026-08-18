import { timeAgo } from "../utils";
import { reviewPR } from "../api";

const REVIEW_STATUS_LABELS = {
  reviewing: "Reviewing…",
  ready: "Ready",
  error: "Error",
};

function Badge({ children, className = "" }) {
  return (
    <span
      className={`inline-flex items-center leading-none font-semibold px-[8px] py-[4px] rounded-md text-[10px] tracking-[0.02em] ${className}`}
    >
      {children}
    </span>
  );
}

export default function PrCard({ pr, onReviewClick, showToast }) {
  const reviewStatus = pr.review_status;
  const posted = !!pr.posted_to_github;

  const handleReview = async (e) => {
    e.stopPropagation();
    try {
      await reviewPR(pr.id);
      showToast?.("Review queued — check back in a moment", "success");
    } catch {
      showToast?.("Failed to queue review", "error");
    }
  };

  return (
    <div className="group relative rounded-xl px-[28px] py-[20px] bg-surface-1">
      <div className="absolute inset-0 rounded-xl border pointer-events-none transition-colors duration-150 border-hairline group-hover:border-hairline-strong" />

      <div className="relative">
        <div className="flex items-center gap-[6px] mb-[12px] flex-wrap">
          <span className="text-[11px] font-medium text-ink-subtle tracking-[0.01em]">
            {pr.repo_full_name}
          </span>

          {pr.is_priority && <Badge className="bg-warning/10 text-warning">Priority</Badge>}
          <Badge className="bg-primary/10 text-primary-hover">PR #{pr.number}</Badge>

          {Array.isArray(pr.labels) && pr.labels.length > 0 && (
            <span className="flex items-center gap-[4px] flex-wrap">
              {pr.labels.map((lbl) => (
                <Badge key={lbl} className="bg-surface-2 text-ink-muted">
                  {lbl}
                </Badge>
              ))}
            </span>
          )}

          {reviewStatus === "ready" && (
            <Badge className="bg-success/15 text-success">
              {posted ? "Posted ✓" : "Review ready"}
            </Badge>
          )}
          {reviewStatus === "reviewing" && (
            <Badge className="bg-primary/10 text-primary-hover">
              {REVIEW_STATUS_LABELS.reviewing}
            </Badge>
          )}
          {reviewStatus === "error" && <Badge className="bg-error/10 text-error">Error</Badge>}
          {!reviewStatus && <Badge className="bg-surface-2 text-ink-muted">Needs review</Badge>}
        </div>

        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-[14px] font-[500] leading-[1.35] tracking-[-0.01em]">
              <a
                href={pr.html_url}
                target="_blank"
                rel="noopener"
                className="text-ink hover:text-primary transition-colors no-underline"
              >
                {pr.title}
              </a>
            </h3>
            {pr.body && (
              <p className="mt-[6px] text-[12.5px] text-ink-subtle leading-[1.55] line-clamp-2">
                {pr.body}
              </p>
            )}
          </div>

          <div className="shrink-0 flex flex-col items-end gap-[4px]">
            <span
              className={`inline-flex items-center px-[10px] py-[4px] rounded-md text-[10px] font-semibold tracking-[0.02em] leading-none
                ${reviewStatus === "ready" ? "bg-success/10 text-success" : ""}
                ${reviewStatus === "reviewing" ? "bg-primary/10 text-primary-hover" : ""}
                ${reviewStatus === "error" ? "bg-error/10 text-error" : ""}
                ${!reviewStatus ? "bg-warning/10 text-warning" : ""}
              `}
            >
              {REVIEW_STATUS_LABELS[reviewStatus] || (posted ? "Posted" : "Needs review")}
            </span>
            <span className="text-[10px] text-ink-tertiary">
              #{pr.number} · {timeAgo(pr.updated_at)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-[4px] mt-[14px] opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-150">
          {!reviewStatus && reviewStatus !== "reviewing" && (
            <button
              onClick={handleReview}
              className="text-xs font-medium px-[8px] py-[3px] rounded-sm text-primary hover:bg-primary/10 transition-colors border border-primary/30"
            >
              Get review
            </button>
          )}

          {reviewStatus && (
            <button
              onClick={(e) => { e.stopPropagation(); onReviewClick?.(pr); }}
              className={`text-xs font-medium px-[8px] py-[3px] rounded-sm transition-colors
                ${posted ? "text-success" : "text-primary hover:bg-primary/10"}`}
            >
              {posted ? "View review" : "View review"}
            </button>
          )}

          <a
            href={pr.html_url}
            target="_blank"
            rel="noopener"
            className="text-xs font-medium px-[8px] py-[3px] rounded-sm text-ink-tertiary hover:text-primary hover:bg-primary/10 transition-colors"
          >
            GitHub ↗
          </a>
        </div>
      </div>
    </div>
  );
}