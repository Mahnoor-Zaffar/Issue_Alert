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
    repo_stars      INTEGER NOT NULL DEFAULT 0,
    score           REAL NOT NULL DEFAULT 0,
    bookmarked      INTEGER NOT NULL DEFAULT 0,
    dismissed       INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS daemon_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    last_poll_at        TEXT,
    last_poll_fetched   INTEGER NOT NULL DEFAULT 0,
    last_poll_new       INTEGER NOT NULL DEFAULT 0,
    last_poll_total_count INTEGER NOT NULL DEFAULT 0,
    last_poll_message   TEXT,
    poll_requested      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    languages       TEXT NOT NULL DEFAULT '["javascript","python","go","rust"]',
    labels          TEXT NOT NULL DEFAULT '["good first issue","help wanted"]',
    min_stars       INTEGER NOT NULL DEFAULT 0,
    show_dismissed  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webhook_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    payload     TEXT NOT NULL,
    processed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_updated_at ON issues(updated_at);
CREATE INDEX IF NOT EXISTS idx_issues_github_id ON issues(github_id);
CREATE INDEX IF NOT EXISTS idx_webhook_queue_processed ON webhook_queue(processed);

INSERT OR IGNORE INTO daemon_state (id) VALUES (1);
INSERT OR IGNORE INTO user_preferences (id) VALUES (1);
