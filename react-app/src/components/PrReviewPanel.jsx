import { useState, useCallback } from "react";
import { reviewPR, postPRReview } from "../api";

function Section({ title, children }) {
  return (
    <div className="mb-4 last:mb-0">
      <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-primary-hover mb-2 pb-1.5 border-b border-hairline">
        {title}
      </h3>
      {children}
    </div>
  );
}

export default function PrReviewPanel({ pr, onClose, showToast }) {
  const [reviewing, setReviewing] = useState(false);
  const [posting, setPosting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const reviewMarkdown = pr?.review_markdown;
  const reviewId = pr?.review_id;
  const reviewStatus = pr?.review_status;
  const posted = !!pr?.posted_to_github;

  if (!pr) return null;

  const renderMD = (text) => {
    if (!text) return null;
    const html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-canvas border border-hairline rounded-md p-[10px] my-[6px] overflow-x-auto text-[12px] text-ink-muted"><code>$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="bg-surface-2 text-primary-hover px-[4px] rounded-[3px] text-[12px] font-mono">$1</code>')
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br />");
    return <div className="text-[13px] text-ink-muted leading-normal" dangerouslySetInnerHTML={{ __html: html }} />;
  };

  const handleReview = useCallback(async () => {
    setReviewing(true);
    try {
      await reviewPR(pr.id);
      showToast?.("Review queued — check back in a moment", "success");
    } catch (e) {
      showToast?.(e?.message || "Failed to queue review", "error");
    }
    setReviewing(false);
  }, [pr.id, showToast]);

  const handlePost = useCallback(async () => {
    if (!reviewId) return;
    setPosting(true);
    try {
      const data = await postPRReview(pr.id, reviewId);
      showToast?.("Review posted to GitHub as a comment", "success");
      setConfirming(false);
      window.location.reload();
    } catch (e) {
      showToast?.(e?.message || "Failed to post review", "error");
    }
    setPosting(false);
  }, [pr.id, reviewId, showToast]);

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-50" onClick={onClose} />
      <div className="fixed top-0 right-0 w-[540px] max-w-[92vw] h-full bg-surface-1 border-l border-hairline z-50 flex flex-col shadow-2xl panel-in">
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-hairline shrink-0">
          <div className="min-w-0">
            <h2 className="text-[14px] font-medium tracking-[-0.01em] leading-snug">{pr.title}</h2>
            <span className="text-[12px] text-ink-subtle mt-[2px] block">
              {pr.repo_full_name} · PR #{pr.number}
            </span>
          </div>
          <button onClick={onClose} className="panel-close shrink-0">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <Section title="#️⃣ Pull Request">
            <a
              href={pr.html_url}
              target="_blank"
              rel="noopener"
              className="text-[13px] text-primary hover:text-primary-hover underline"
            >
              Open on GitHub ↗
            </a>
            {pr.head_sha && (
              <p className="text-[11px] text-ink-tertiary mt-[4px] font-mono">
                head {pr.head_sha.slice(0, 7)}
              </p>
            )}
          </Section>

          <Section title="💬 Community Review">
            {posted && (
              <div className="bg-success/10 text-success text-[12px] font-medium rounded-md px-3 py-2 mb-3">
                ✓ Posted to GitHub
              </div>
            )}

            {reviewMarkdown ? (
              <div className="bg-surface-2/50 border border-hairline rounded-md p-3">
                {renderMD(reviewMarkdown)}
              </div>
            ) : reviewStatus === "reviewing" ? (
              <p className="text-[12px] text-ink-tertiary italic">Review in progress…</p>
            ) : reviewStatus === "error" ? (
              <p className="text-[12px] text-error">Review failed — check daemon logs for details.</p>
            ) : (
              <p className="text-[12px] text-ink-tertiary">
                No review generated yet. Queue one to have the LLM analyze this PR.
              </p>
            )}
          </Section>
        </div>

        <div className="border-t border-hairline px-5 py-4 shrink-0 flex items-center gap-2 flex-wrap">
          <button
            onClick={handleReview}
            disabled={reviewing || reviewStatus === "reviewing"}
            className="text-xs font-medium px-[10px] py-[6px] rounded-lg bg-primary text-white hover:bg-primary-hover transition-colors cursor-pointer border-none disabled:opacity-40"
          >
            {reviewing ? "Queuing…" : reviewMarkdown ? "↻ Regenerate" : "Generate review"}
          </button>

          {reviewMarkdown && !posted && (
            confirming ? (
              <>
                <span className="text-[12px] text-ink-subtle">
                  Post this review publicly to GitHub?
                </span>
                <button
                  onClick={handlePost}
                  disabled={posting}
                  className="text-xs font-medium px-[10px] py-[6px] rounded-lg bg-success text-white hover:bg-success/80 transition-colors cursor-pointer border-none disabled:opacity-40"
                >
                  {posting ? "Posting…" : "Confirm post"}
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="text-xs font-medium px-[10px] py-[6px] rounded-lg bg-surface-2 text-ink hover:bg-surface-1 transition-colors cursor-pointer border border-hairline"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirming(true)}
                className="text-xs font-medium px-[10px] py-[6px] rounded-lg bg-surface-2 text-ink border border-hairline hover:bg-surface-2/70 transition-colors cursor-pointer"
              >
                Post to GitHub
              </button>
            )
          )}

          {posted && (
            <span className="text-xs font-medium px-[10px] py-[6px] rounded-lg bg-success/10 text-success">
              ✓ Already posted
            </span>
          )}
        </div>
      </div>
    </>
  );
}