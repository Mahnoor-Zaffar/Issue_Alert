import { useState, useCallback } from "react";
import { reTriage, openPR, fetchPRDetails } from "../api";

function Section({ title, children }) {
  return (
    <div className="mb-4 last:mb-0">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-primary mb-2 pb-1 border-b border-hairline">
        {title}
      </h3>
      {children}
    </div>
  );
}

const PR_STATUS_LABELS = {
  open: "Open",
  pending: "CI Running…",
  success: "CI Passing",
  failure: "CI Failing",
  merged: "Merged",
  closed: "Closed",
  error: "CI Error",
};

export default function TriagePanel({ issue, onClose }) {
  const [prDetails, setPRDetails] = useState(null);
  const [prLoading, setPRLoading] = useState(false);
  const [prOpening, setPROpening] = useState(false);
  const [retriaging, setRetriaging] = useState(false);
  const [retriageMsg, setRetriageMsg] = useState("");
  const [copied, setCopied] = useState(false);

  const t = issue?.triage;
  if (!issue || !t) return null;

  const prUrl = t.pr_url;
  const prStatus = t.pr_status;
  const claimComment = t.claim_comment;

  const handleReTriage = useCallback(async () => {
    setRetriaging(true);
    setRetriageMsg("");
    try {
      const data = await reTriage(issue.id);
      setRetriageMsg(data?.message || "Re-triage queued");
    } catch (e) {
      setRetriageMsg(e?.message || "Re-triage failed");
    }
    setRetriaging(false);
  }, [issue.id]);

  const handleOpenPR = useCallback(async () => {
    setPROpening(true);
    try {
      const data = await openPR(issue.id);
      if (data.pr_url) window.open(data.pr_url, "_blank");
    } catch {}
    setPROpening(false);
  }, [issue.id]);

  const handleLoadPRDetails = useCallback(async () => {
    if (prDetails || !prUrl) return;
    setPRLoading(true);
    try {
      const data = await fetchPRDetails(prUrl);
      setPRDetails(data);
    } catch {}
    setPRLoading(false);
  }, [prUrl, prDetails]);

  const handleCopy = useCallback(() => {
    if (!claimComment) return;
    navigator.clipboard.writeText(claimComment).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [claimComment]);

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

  return (
    <>
      <div className="fixed inset-0 bg-black/60 z-50" onClick={onClose} />
      <div className="fixed top-0 right-0 w-[520px] max-w-[90vw] h-full bg-surface-1 border-l border-hairline z-50 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-hairline shrink-0">
          <div className="min-w-0">
            <h2 className="text-[14px] font-medium tracking-[-0.01em] leading-snug">{issue.title}</h2>
            <span className="text-[12px] text-ink-subtle mt-[2px] block">{issue.repo_full_name}</span>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 w-[28px] h-[28px] flex items-center justify-center rounded-md border border-hairline text-ink-tertiary hover:text-ink hover:bg-surface-2 transition-colors text-[14px] cursor-pointer bg-transparent"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <Section title="🧩 What This Part Does">
            {renderMD(t.architecture_context)}
          </Section>

          <Section title="🐛 What's Wrong">
            {renderMD(t.issue_breakdown)}
          </Section>

          <Section title="📝 Plan to Fix It">
            {renderMD(t.action_plan)}
          </Section>

          {claimComment && (
            <Section title="💬 Comment to Get Assigned">
              <div className="bg-success/5 border border-success/20 rounded-md p-3">
                <p className="text-[13px] text-ink-muted leading-relaxed mb-2">{claimComment}</p>
                <button
                  onClick={handleCopy}
                  className="text-xs font-medium px-[10px] py-[4px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors cursor-pointer border-none"
                >
                  {copied ? "✓ Copied" : "📋 Copy"}
                </button>
              </div>
            </Section>
          )}

          {/* PR section */}
          {prUrl && (
            <Section title="Pull Request">
              <div className="bg-surface-2 border border-hairline rounded-md p-3">
                <div className="text-xs font-semibold text-ink-muted mb-1">
                  PR: {PR_STATUS_LABELS[prStatus] || prStatus}
                </div>
                <a href={prUrl} target="_blank" rel="noopener" className="text-[12px] text-primary hover:text-primary-hover break-all">
                  {prUrl}
                </a>
                <button
                  onClick={handleLoadPRDetails}
                  disabled={prLoading || prDetails}
                  className="block mt-2 text-xs font-medium px-[10px] py-[4px] rounded-md bg-surface-1 text-ink border border-hairline hover:bg-surface-3 transition-colors cursor-pointer disabled:opacity-40"
                >
                  {prLoading ? "Loading…" : prDetails ? "Loaded" : "Show Details"}
                </button>
                {prDetails && (
                  <div className="mt-3 pt-3 border-t border-hairline space-y-2">
                    <div className="flex items-center justify-between">
                      <strong className="text-[12px]">{prDetails.title}</strong>
                      <span className="text-[10px] px-[5px] py-[1px] rounded-full bg-surface-3 text-ink-muted">
                        {prDetails.draft ? "Draft" : prDetails.merged ? "Merged" : prDetails.state}
                      </span>
                    </div>
                    {prDetails.body && (
                      <p className="text-[12px] text-ink-subtle line-clamp-3">{prDetails.body}</p>
                    )}
                    {prDetails.files?.length > 0 && (
                      <div>
                        <div className="text-[11px] font-semibold text-ink-muted mb-1">Files ({prDetails.files.length})</div>
                        {prDetails.files.slice(0, 8).map((f) => (
                          <div key={f.filename} className="flex justify-between text-[11px] text-ink-subtle py-[1px]">
                            <span className="truncate">{f.filename}</span>
                            <span className="shrink-0 ml-2 text-success">+{f.additions}</span>
                            <span className="shrink-0 text-error">-{f.deletions}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {prDetails.checks?.length > 0 && (
                      <div>
                        <div className="text-[11px] font-semibold text-ink-muted mb-1">Checks</div>
                        {prDetails.checks.map((c) => (
                          <div key={c.name} className="text-[11px] text-ink-subtle py-[1px]">
                            <span>
                              {c.conclusion === "success" ? "✓" : c.conclusion === "failure" ? "✗" : "○"}
                              {" "}{c.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 pt-2">
            {issue.difficulty === "easy" && !prUrl && (
              <button
                onClick={handleOpenPR}
                disabled={prOpening}
                className="text-xs font-medium px-[12px] py-[6px] rounded-md bg-primary text-white hover:bg-primary-hover transition-colors cursor-pointer border-none disabled:opacity-40"
              >
                {prOpening ? "Opening…" : "Open Draft PR"}
              </button>
            )}
            <button
              onClick={handleReTriage}
              disabled={retriaging}
              className="text-xs font-medium px-[12px] py-[6px] rounded-md bg-surface-1 text-ink border border-hairline hover:bg-surface-2 transition-colors cursor-pointer disabled:opacity-40"
            >
              {retriaging ? "Re-triaging…" : "↻ Re-triage"}
            </button>
          </div>
          {retriageMsg && (
            <p className="text-xs text-ink-muted mt-2 italic">{retriageMsg}</p>
          )}
        </div>
      </div>
    </>
  );
}
