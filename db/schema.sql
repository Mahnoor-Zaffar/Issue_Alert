CREATE TABLE IF NOT EXISTS seen_issues (
    github_id   INTEGER PRIMARY KEY,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    github_id       INTEGER NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    body            TEXT,
    html_url        TEXT NOT NULL,
    repo_full_name  TEXT NOT NULL,
    repo_clone_url  TEXT NOT NULL,
    labels          TEXT NOT NULL DEFAULT '[]',
    language        TEXT,
    state           TEXT NOT NULL DEFAULT 'open',
    status          TEXT NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS triage_reports (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id             INTEGER NOT NULL UNIQUE REFERENCES issues(id) ON DELETE CASCADE,
    architecture_context TEXT,
    issue_breakdown      TEXT,
    action_plan          TEXT,
    raw_response         TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_updated_at ON issues(updated_at);
CREATE INDEX IF NOT EXISTS idx_issues_github_id ON issues(github_id);
