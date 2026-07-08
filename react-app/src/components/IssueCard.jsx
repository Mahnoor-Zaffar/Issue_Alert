import { useState, useCallback } from "react";
import { setDifficulty, setBookmark, dismissIssue } from "../api";

const DIFFICULTY_LABELS = { easy: "Easy", medium: "Medium", hard: "Hard" };
const STATUS_LABELS = {
  pending: "Pending",
  notified: "Notified",
  extracting: "Extracting",
  triaging: "Triaging",
  complete: "Complete",
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

export default function IssueCard({ issue, onTriageClick, showToast }) {
  const [saving, setSaving] = useState(false);
  const [bodyExpanded, setBodyExpanded] = useState(false);

  const handleCycleDifficulty = useCallback(
    async (e) => {
      e.stopPropagation();
      const order = ["easy", "medium", "hard"];
      const next = order[(order.indexOf(issue.difficulty) + 1) % order.length];
      try {
        await setDifficulty(issue.id, next);
        showToast?.("Difficulty updated", "success");
      } catch {
        showToast?.("Failed to update difficulty", "error");
      }
    },
    [issue.id, issue.difficulty, showToast]
  );

  const handleBookmark = useCallback(
    async (e) => {
      e.stopPropagation();
      setSaving(true);
      try {
        await setBookmark(issue.id, !issue.bookmarked);
        showToast?.(issue.bookmarked ? "Bookmark removed" : "Bookmarked", "success");
      } catch {
        showToast?.("Failed to bookmark", "error");
      }
      setSaving(false);
    },
    [issue.id, issue.bookmarked, showToast]
  );

  const handleDismiss = useCallback(
    async (e) => {
      e.stopPropagation();
      try {
        await dismissIssue(issue.id);
        showToast?.("Dismissed", "success");
      } catch {
        showToast?.("Failed to dismiss", "error");
      }
    },
    [issue.id, showToast]
  );

  const prStatus = issue.triage?.pr_status;
  const hasPR = !!issue.triage?.pr_url;
  const bodyLong = issue.body && issue.body.length > 200;

  return (
    <div
      className={`group relative rounded-xl px-[28px] py-[20px] cursor-default transition-colors duration-150
        ${issue.status === "error" ? "bg-surface-1/80" : "bg-surface-1"}
      `}
    >
      <div
        className={`absolute inset-0 rounded-xl border pointer-events-none transition-colors duration-150
          ${issue.status === "error" ? "border-error/25 group-hover:border-error/45" : "border-hairline group-hover:border-hairline-strong"}
        `}
      />

      <div className="relative">
        {/* Meta row */}
        <div className="flex items-center gap-[6px] mb-[12px] flex-wrap">
          <span className="text-[11px] font-medium text-ink-subtle tracking-[0.01em]">
            {issue.repo_full_name}
          </span>

          {issue.language && (
            <Badge className="bg-primary/10 text-primary-hover">{issue.language}</Badge>
          )}

          {issue.repo_stars > 0 && (
            <Badge className="bg-warning/10 text-warning">
              ★ {issue.repo_stars >= 1000 ? `${(issue.repo_stars / 1000).toFixed(1)}k` : issue.repo_stars}
            </Badge>
          )}

          {issue.is_priority && (
            <Badge className="bg-warning/10 text-warning">Priority</Badge>
          )}

          {issue.difficulty && (
            <Badge
              className={`cursor-pointer transition-colors
                ${issue.difficulty === "easy" ? "bg-success/10 text-success hover:bg-success/15" : ""}
                ${issue.difficulty === "medium" ? "bg-warning/10 text-warning hover:bg-warning/15" : ""}
                ${issue.difficulty === "hard" ? "bg-error/10 text-error hover:bg-error/15" : ""}
              `}
              onClick={handleCycleDifficulty}
              title="Click to cycle difficulty"
            >
              {DIFFICULTY_LABELS[issue.difficulty]}
            </Badge>
          )}

          {hasPR && (
            <Badge
              className={`
                ${prStatus === "success" ? "bg-success/10 text-success" : ""}
                ${prStatus === "failure" ? "bg-error/10 text-error" : ""}
                ${prStatus === "pending" ? "bg-warning/10 text-warning" : ""}
                ${!prStatus || prStatus === "open" ? "bg-primary/10 text-primary-hover" : ""}
              `}
            >
              PR
            </Badge>
          )}
        </div>

        {/* Title row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-[14px] font-[500] leading-[1.35] tracking-[-0.01em]">
              <a
                href={issue.html_url}
                target="_blank"
                rel="noopener"
                className="text-ink hover:text-primary transition-colors no-underline"
              >
                {issue.title}
              </a>
            </h3>

            {issue.body && (
              <div>
                <p
                  className={`mt-[6px] text-[12.5px] text-ink-subtle leading-[1.55] ${
                    bodyExpanded ? "" : "line-clamp-2"
                  }`}
                >
                  {issue.body}
                </p>
                {bodyLong && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setBodyExpanded((v) => !v); }}
                    className="mt-[2px] text-[11px] font-medium text-primary hover:text-primary-hover transition-colors bg-transparent border-none cursor-pointer"
                  >
                    {bodyExpanded ? "Show less" : "Show more"}
                  </button>
                )}
              </div>
            )}
          </div>

          <span
            className={`shrink-0 inline-flex items-center px-[10px] py-[4px] rounded-md text-[10px] font-semibold tracking-[0.02em] leading-none
              ${issue.status === "complete" ? "bg-success/10 text-success" : ""}
              ${issue.status === "error" ? "bg-error/10 text-error" : ""}
              ${issue.status === "pending" || issue.status === "notified" ? "bg-warning/10 text-warning" : ""}
              ${issue.status === "extracting" || issue.status === "triaging" ? "bg-primary/10 text-primary-hover" : ""}
            `}
          >
            {STATUS_LABELS[issue.status] || issue.status}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-[4px] mt-[14px] opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <button
            onClick={handleBookmark}
            disabled={saving}
            className={`text-xs font-medium px-[8px] py-[3px] rounded-sm transition-colors
              ${issue.bookmarked
                ? "text-warning bg-warning/10"
                : "text-ink-tertiary hover:text-warning hover:bg-warning/8"
              }`}
          >
            {issue.bookmarked ? "★ Saved" : "☆ Save"}
          </button>

          {issue.status === "complete" && issue.triage && (
            <button
              onClick={(e) => { e.stopPropagation(); onTriageClick?.(issue); }}
              className="text-xs font-medium px-[8px] py-[3px] rounded-sm text-primary hover:bg-primary/10 transition-colors"
            >
              View Report
            </button>
          )}

          {issue.status === "error" && (
            <button
              onClick={(e) => { e.stopPropagation(); onTriageClick?.(issue); }}
              className="text-xs font-medium px-[8px] py-[3px] rounded-sm text-error hover:bg-error/10 transition-colors"
            >
              Error
            </button>
          )}

          {issue.triage && (
            <button
              onClick={(e) => { e.stopPropagation(); onTriageClick?.(issue, true); }}
              className="text-xs font-medium px-[8px] py-[3px] rounded-sm text-ink-tertiary hover:text-primary hover:bg-primary/10 transition-colors"
            >
              ↻ Retriage
            </button>
          )}

          <div className="flex-1" />

          <span className="text-[10px] text-ink-tertiary mr-1">
            #{issue.number}
          </span>

          <button
            onClick={handleDismiss}
            className="w-[26px] h-[26px] flex items-center justify-center rounded-sm text-ink-tertiary hover:text-error hover:bg-error/10 transition-colors text-[14px]"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
