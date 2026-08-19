import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

MIGRATIONS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_triage_requests_issue_id ON triage_requests(issue_id)",
    "ALTER TABLE issues ADD COLUMN claimed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN repo_stars INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN score REAL NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN bookmarked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN viewed_at TEXT",
    "ALTER TABLE issues ADD COLUMN github_created_at TEXT",
    "ALTER TABLE issues ADD COLUMN comments INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN is_priority INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE triage_reports ADD COLUMN difficulty TEXT",
    "ALTER TABLE triage_reports ADD COLUMN pr_url TEXT",
    "ALTER TABLE triage_reports ADD COLUMN pr_head_sha TEXT",
    "ALTER TABLE triage_reports ADD COLUMN pr_status TEXT",
    "ALTER TABLE triage_reports ADD COLUMN pr_checked_at TEXT",
    "ALTER TABLE issues ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE triage_reports ADD COLUMN claim_comment TEXT",
    "ALTER TABLE priority_repos ADD COLUMN is_high_priority INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE priority_repos ADD COLUMN is_org INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN is_bounty INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN bounty_amount REAL",
    "ALTER TABLE priority_repos ADD COLUMN is_small_target INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN is_small_target INTEGER NOT NULL DEFAULT 0",
    "CREATE TABLE IF NOT EXISTS pulls ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " repo_full_name TEXT NOT NULL,"
    " number INTEGER NOT NULL,"
    " title TEXT NOT NULL,"
    " body TEXT,"
    " html_url TEXT NOT NULL,"
    " head_sha TEXT,"
    " base_sha TEXT,"
    " base_ref TEXT,"
    " author TEXT,"
    " state TEXT NOT NULL DEFAULT 'open',"
    " labels TEXT NOT NULL DEFAULT '[]',"
    " head_label TEXT,"
    " is_priority INTEGER NOT NULL DEFAULT 0,"
    " ingested_via TEXT NOT NULL DEFAULT 'scan',"
    " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " UNIQUE (repo_full_name, number)"
    ")",
    "CREATE TABLE IF NOT EXISTS pr_reviews ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " pull_id INTEGER NOT NULL REFERENCES pulls(id) ON DELETE CASCADE,"
    " status TEXT NOT NULL DEFAULT 'reviewing',"
    " review_markdown TEXT,"
    " posted_to_github INTEGER NOT NULL DEFAULT 0,"
    " github_review_id INTEGER,"
    " error_message TEXT,"
    " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
    ")",
    "CREATE INDEX IF NOT EXISTS idx_pulls_state ON pulls(state)",
    "CREATE INDEX IF NOT EXISTS idx_pulls_updated_at ON pulls(updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_pr_reviews_pull_id ON pr_reviews(pull_id)",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _freshness_cutoff_iso() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.issue_discovery_window_minutes)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def _visible_issue_clauses(
    *,
    show_dismissed: bool = False,
    include_stale: bool = False,
    bookmarked_only: bool = False,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if not show_dismissed:
        clauses.append("i.dismissed = 0")
    if bookmarked_only:
        clauses.append("i.bookmarked = 1")
    if not include_stale:
        clauses.append(
            "(COALESCE(i.is_small_target, 0) = 1 OR (i.github_created_at IS NOT NULL AND i.github_created_at >= ?))"
        )
        params.append(_freshness_cutoff_iso())

    return clauses, params


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


@contextmanager
def get_connection():
    db_path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _configure_connection(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass

    row = conn.execute("SELECT labels, min_stars, languages FROM user_preferences WHERE id = 1").fetchone()
    if row:
        labels = json.loads(row["labels"] or "[]")
        min_stars = row["min_stars"]
        languages = json.loads(row["languages"] or "[]")
        needs_update = False

        new_labels = ["good first issue", "help wanted", "bug", "enhancement", "feature", "fix", "improvement"]
        old_default_labels = {"good first issue", "help wanted"}
        prev_default_labels = {"bug", "feature", "enhancement", "help wanted"}
        labels_set = set(labels)
        if labels_set == old_default_labels or labels_set == prev_default_labels:
            labels = list(new_labels)
            needs_update = True
        elif "open source" in labels or "open-source" in labels:
            labels = [label for label in labels if label not in ("open source", "open-source")]
            needs_update = True

        old_default_languages = {"javascript", "python", "go", "rust"}
        new_default_languages = {"javascript", "typescript", "python"}
        if set(languages) == old_default_languages:
            languages = list(new_default_languages)
            needs_update = True

        if min_stars == 0:
            min_stars = 500
            needs_update = True

        if needs_update:
            conn.execute(
                "UPDATE user_preferences SET labels = ?, min_stars = ?, languages = ? WHERE id = 1",
                (json.dumps(labels), min_stars, json.dumps(languages)),
            )


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_issues_score ON issues(score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_issues_dismissed ON issues(dismissed)",
    ]
    for sql in indexes:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        _migrate(conn)
        _ensure_indexes(conn)
    purge_stale_issues()


def is_issue_seen(github_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM seen_issues WHERE github_id = ?", (github_id,)).fetchone()
        return row is not None


def mark_issue_seen(github_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_issues (github_id) VALUES (?)",
            (github_id,),
        )


def compute_score(issue: dict[str, Any]) -> float:
    score = 0.0
    stars = issue.get("repo_stars") or 0
    score += min(stars / 100.0, 50.0)

    comments = issue.get("comments") or 0
    score += min(comments * 2.0, 20.0)

    body = issue.get("body") or ""
    body_len = len(body.strip())
    if body_len > 500:
        score += 15
    elif body_len > 200:
        score += 10
    elif body_len > 100:
        score += 5
    elif body_len == 0:
        score -= 5

    if issue.get("is_bounty"):
        amount = issue.get("bounty_amount") or 0
        score += min(amount / 10.0, 30.0) if amount else 25.0

    return round(score, 2)


def compute_top_pick_score(issue: dict[str, Any]) -> float:
    stars = issue.get("repo_stars") or 0
    prestige = min(math.log10(max(stars, 10)) / 5.0, 1.0)

    labels = issue.get("labels") or []
    if isinstance(labels, str):
        labels = json.loads(labels)
    label_lower = [label.lower() for label in labels]
    label_score = 0.4
    if "good first issue" in label_lower:
        label_score = 1.0
    elif "help wanted" in label_lower:
        label_score = 0.9
    elif "bug" in label_lower:
        label_score = 0.7
    elif "enhancement" in label_lower or "feature" in label_lower:
        label_score = 0.6

    diff = (issue.get("difficulty") or "").lower()
    difficulty_bonus = 1.0
    if diff == "easy":
        difficulty_bonus = 1.3
    elif diff == "hard":
        difficulty_bonus = 0.7

    comments = issue.get("comments") or 0
    freshness = max(0.0, 1.0 - comments * 0.05)

    age_hours = None
    raw_created = issue.get("github_created_at") or issue.get("created_at")
    if raw_created:
        try:
            created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            age_hours = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600.0)
        except ValueError, TypeError:
            age_hours = None
    recency = 1.0
    if age_hours is not None:
        recency = max(0.0, min(1.0, 1.0 - age_hours / 168.0))

    body_len = len((issue.get("body") or "").strip())
    quality = min(body_len / 500.0, 1.0)

    bounty_bonus = 1.5 if issue.get("is_bounty") else 1.0

    return round(
        prestige * label_score * difficulty_bonus * freshness * recency * bounty_bonus * (0.5 + 0.5 * quality) * 100,
        1,
    )


def get_top_picks(limit: int = 3) -> list[dict[str, Any]]:
    issues = list_issues(limit=500, offset=0, is_priority=True)
    for i in issues:
        i["top_pick_score"] = compute_top_pick_score(i)
    issues = [i for i in issues if i.get("top_pick_score", 0) > 0]
    issues.sort(key=lambda i: i.get("top_pick_score", 0), reverse=True)
    return issues[:limit]


def generate_pr_description(issue_id: int) -> dict[str, Any] | None:
    issue = get_issue(issue_id)
    if not issue:
        return None

    triage = issue.get("triage") or {}
    repo = issue["repo_full_name"]
    title = issue["title"]
    action_plan = triage.get("action_plan", "")
    breakdown = triage.get("issue_breakdown", "")

    owner, repo_name = repo.split("/")
    safe_title = (
        title.lower()[:40].replace(" ", "-").replace("[", "").replace("]", "").replace(":", "").replace("#", "")
    )
    branch = f"fix/{issue_id}-{safe_title}"

    body_parts = ["## Summary", f"Fixes #{issue_id}: {title}", "", "## Root Cause"]
    if breakdown:
        body_parts.append(breakdown[:800])
    elif issue.get("body"):
        body_parts.append(issue["body"][:800])
    else:
        body_parts.append("_Run the triage to auto-generate this section_")
    body_parts.append("")
    body_parts.append("## Changes")
    if action_plan:
        body_parts.append(action_plan[:1000])
    else:
        body_parts.append("_Describe your changes here_")
    body_parts.append("")
    body_parts.append("## How to Test")
    body_parts.append("_Describe how reviewers can verify this fix_")
    body_parts.append("")
    body_parts.append("Closes #" + str(issue.get("github_id", issue_id)))

    pr_body = "\n".join(body_parts)
    pr_title = f"fix: {title[:60]}"

    return {
        "owner": owner,
        "repo": repo_name,
        "branch_name": branch,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "compare_url": f"https://github.com/{repo}/compare/main...{branch}?expand=1",
        "issue_url": issue["html_url"],
    }


def get_resume_summary(days: int = 7) -> dict[str, Any]:
    with get_connection() as conn:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        claimed = conn.execute(
            "SELECT i.repo_full_name, i.title, i.html_url, t.difficulty, t.pr_url, t.pr_status, i.claimed "
            "FROM issues i LEFT JOIN triage_reports t ON t.issue_id = i.id "
            "WHERE i.claimed = 1 AND i.updated_at >= ? "
            "ORDER BY i.repo_full_name",
            (since,),
        ).fetchall()

        triaged = conn.execute("SELECT COUNT(*) FROM triage_reports WHERE created_at >= ?", (since,)).fetchone()[0]
        posted_reviews = conn.execute(
            "SELECT COUNT(*) FROM pr_reviews WHERE posted_to_github = 1 AND updated_at >= ?",
            (since,),
        ).fetchone()[0]
        reviews_ready = conn.execute(
            "SELECT COUNT(*) FROM pr_reviews WHERE review_markdown IS NOT NULL AND updated_at >= ?",
            (since,),
        ).fetchone()[0]

    contributions = [dict(r) for r in claimed]

    repos = {}
    for c in contributions:
        r = c["repo_full_name"]
        if r not in repos:
            repos[r] = []
        repos[r].append(c)

    md_lines = ["# YC Application — Open Source Contributions", ""]
    md_lines.append(f"_Last {days} days_")
    md_lines.append("")
    md_lines.append(f"**Issues Claimed:** {len(contributions)}")
    md_lines.append(f"**Issues Triaged:** {triaged}")
    md_lines.append(f"**PR Reviews Written:** {reviews_ready} (posted: {posted_reviews})")
    md_lines.append("")

    for repo, issues in sorted(repos.items()):
        md_lines.append(f"## [{repo}](https://github.com/{repo})")
        md_lines.append("")
        for idx, c in enumerate(issues, 1):
            md_lines.append(f"{idx}. **[{c['title']}]({c['html_url']})** `{c.get('difficulty', 'N/A')}`")
            if c.get("pr_url"):
                md_lines.append(f"   - PR: [{c['pr_url']}]({c['pr_url']}) `{c.get('pr_status', 'open')}`")
            md_lines.append("")
        md_lines.append("")

    return {
        "markdown": "\n".join(md_lines),
        "contributions": contributions,
        "total_claimed": len(contributions),
        "total_triaged": triaged,
        "pr_reviews_written": reviews_ready,
        "pr_reviews_posted": posted_reviews,
        "days": days,
    }


def insert_issue(issue: dict[str, Any]) -> int:
    now = _utcnow()
    score = issue.get("score")
    if score is None:
        score = compute_score(issue)
    github_created_at = issue.get("created_at") or now

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO issues (
                github_id, title, body, html_url, repo_full_name,
                repo_clone_url, labels, language, repo_stars, score,
                comments, state, status, github_created_at, created_at,
                updated_at, is_priority, is_bounty, bounty_amount, is_small_target
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue["github_id"],
                issue["title"],
                issue.get("body"),
                issue["html_url"],
                issue["repo_full_name"],
                issue["repo_clone_url"],
                json.dumps(issue.get("labels", [])),
                issue.get("language"),
                issue.get("repo_stars", 0),
                score,
                issue.get("comments", 0),
                issue.get("state", "open"),
                issue.get("status", "pending"),
                github_created_at,
                now,
                now,
                issue.get("is_priority", False),
                issue.get("is_bounty", False),
                issue.get("bounty_amount"),
                issue.get("is_small_target", False),
            ),
        )
        if cursor.lastrowid:
            return cursor.lastrowid
        # Already exists — return existing id
        row = conn.execute("SELECT id FROM issues WHERE github_id = ?", (issue["github_id"],)).fetchone()
        return row["id"] if row else 0


def update_issue_status(
    issue_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE issues
            SET status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error_message, _utcnow(), issue_id),
        )


def mark_issue_viewed(issue_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT id, bookmarked FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if not row:
            return False
        if row["bookmarked"]:
            return True
        conn.execute(
            "UPDATE issues SET viewed_at = ?, updated_at = ? WHERE id = ?",
            (_utcnow(), _utcnow(), issue_id),
        )
        return True


def purge_stale_issues() -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM issues
            WHERE bookmarked = 0
              AND COALESCE(is_small_target, 0) = 0
              AND github_created_at IS NOT NULL
              AND github_created_at < ?
            """,
            (cutoff,),
        )
        return cursor.rowcount


def purge_untracked_repo_issues() -> int:
    """Delete issues whose repo is no longer in the priority or general feed scope."""
    priority = {r["full_name"] for r in get_priority_repos()}
    general = {r["full_name"] for r in get_general_repos()}
    tracked = priority | general
    if not tracked:
        return 0
    placeholders = ",".join("?" * len(tracked))
    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            DELETE FROM issues
            WHERE bookmarked = 0
              AND repo_full_name NOT IN ({placeholders})
            """,
            list(tracked),
        )
        return cursor.rowcount


# ── Difficulty ──────────────────────────────────────────


def parse_difficulty(text: str) -> str | None:
    if not text:
        return None
    if "🟢" in text:
        return "easy"
    if "🟡" in text:
        return "medium"
    if "🔴" in text:
        return "hard"
    return None


# ── Triage Queue ──────────────────────────────────────────


def enqueue_triage(issue_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO triage_requests (issue_id) VALUES (?)",
            (issue_id,),
        )


def get_pending_triage_requests() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT issue_id FROM triage_requests ORDER BY created_at ASC").fetchall()
        return [r["issue_id"] for r in rows]


def dequeue_triage(issue_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM triage_requests WHERE issue_id = ?", (issue_id,))


# ── Daily Stats ──────────────────────────────────────────


def record_daily_stats() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_stats (date, triaged, bookmarked, polled)
            VALUES (?, (
                SELECT COUNT(*) FROM issues WHERE status = 'complete'
                  AND date(updated_at) = ?
            ), (
                SELECT COUNT(*) FROM issues WHERE bookmarked = 1
            ), 1)
            ON CONFLICT(date) DO UPDATE SET
                triaged = excluded.triaged,
                bookmarked = excluded.bookmarked,
                polled = polled + 1
            """,
            (today, today),
        )


def get_stats_history(days: int = 14) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT date, triaged, bookmarked, polled
            FROM daily_stats
            ORDER BY date ASC
            LIMIT ?
            """,
            (days,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_issue_flag(issue_id: int, field: str, value: bool) -> None:
    if field not in ("bookmarked", "dismissed", "claimed"):
        raise ValueError(f"Invalid field: {field}")
    with get_connection() as conn:
        conn.execute(
            f"UPDATE issues SET {field} = ?, updated_at = ? WHERE id = ?",
            (1 if value else 0, _utcnow(), issue_id),
        )


def insert_triage_report(
    issue_id: int,
    architecture_context: str,
    issue_breakdown: str,
    action_plan: str,
    raw_response: str,
    difficulty: str | None = None,
    claim_comment: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO triage_reports (
                issue_id, architecture_context, issue_breakdown,
                action_plan, raw_response, difficulty, claim_comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                architecture_context,
                issue_breakdown,
                action_plan,
                raw_response,
                difficulty,
                claim_comment,
            ),
        )


def get_issue(issue_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw,
                   t.difficulty, t.pr_url, t.pr_head_sha,
                   t.pr_status, t.pr_checked_at,
                   t.claim_comment
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE i.id = ?
            """,
            (issue_id,),
        ).fetchone()
        return _row_to_issue(row) if row else None


def list_issues(
    limit: int = 50,
    offset: int = 0,
    language: str | None = None,
    status: str | None = None,
    label: str | None = None,
    show_dismissed: bool = False,
    bookmarked_only: bool = False,
    claimed_only: bool = False,
    is_priority: bool | None = None,
    difficulty: str | None = None,
    bounty_only: bool = False,
    hide_old_unclaimed: bool = False,
) -> list[dict[str, Any]]:
    visible_clauses, visible_params = _visible_issue_clauses(
        show_dismissed=show_dismissed, bookmarked_only=bookmarked_only
    )
    clauses: list[str] = list(visible_clauses)
    params: list[Any] = list(visible_params)

    if language:
        clauses.append("LOWER(i.language) = LOWER(?)")
        params.append(language)
    if status:
        clauses.append("i.status = ?")
        params.append(status)
    if label:
        clauses.append("i.labels LIKE ?")
        params.append(f'%"{label}"%')
    if bookmarked_only:
        clauses.append("i.bookmarked = 1")
    if claimed_only:
        clauses.append("i.claimed = 1")
    if is_priority is not None:
        clauses.append("i.is_priority = ?")
        params.append(1 if is_priority else 0)
    if difficulty:
        clauses.append("t.difficulty = ?")
        params.append(difficulty)
    if bounty_only:
        clauses.append("i.is_bounty = 1")
    if hide_old_unclaimed:
        clauses.append(
            "(i.claimed = 1 OR COALESCE(i.is_small_target, 0) = 1 "
            "OR i.github_created_at IS NULL OR i.github_created_at >= ?)"
        )
        params.append(_freshness_cutoff_iso())

    where = " AND ".join(clauses)
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw,
                   t.difficulty, t.pr_url, t.pr_head_sha,
                   t.pr_status, t.pr_checked_at,
                   t.claim_comment
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE {where}
            ORDER BY COALESCE(i.is_small_target, 0) DESC, i.github_created_at DESC, i.score DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [_row_to_issue(row) for row in rows]


def get_issues_updated_since(since: str, bookmarked_only: bool = False) -> list[dict[str, Any]]:
    visible_clauses, visible_params = _visible_issue_clauses(bookmarked_only=bookmarked_only)
    where = " AND ".join(["i.updated_at > ?"] + visible_clauses)
    params: list[Any] = [since, *visible_params]

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw,
                   t.difficulty, t.pr_url, t.pr_head_sha,
                   t.pr_status, t.pr_checked_at,
                   t.claim_comment
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE {where}
            ORDER BY i.updated_at ASC
            """,
            params,
        ).fetchall()
        return [_row_to_issue(row) for row in rows]


def get_stats() -> dict[str, Any]:
    visible_clauses, visible_params = _visible_issue_clauses()
    where = " AND ".join(visible_clauses)

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM issues i WHERE {where}",
            visible_params,
        ).fetchone()[0]
        pending = conn.execute(
            f"""
            SELECT COUNT(*) FROM issues i
            WHERE {where} AND i.status NOT IN ('complete', 'error')
            """,
            visible_params,
        ).fetchone()[0]
        complete = conn.execute(
            f"""
            SELECT COUNT(*) FROM issues i
            WHERE {where} AND i.status = 'complete'
            """,
            visible_params,
        ).fetchone()[0]
        errors = conn.execute(
            f"""
            SELECT COUNT(*) FROM issues i
            WHERE {where} AND i.status = 'error'
            """,
            visible_params,
        ).fetchone()[0]
        bookmarked = conn.execute(
            f"""
            SELECT COUNT(*) FROM issues i
            WHERE {where} AND i.bookmarked = 1
            """,
            visible_params,
        ).fetchone()[0]
        last_updated = conn.execute(
            f"SELECT MAX(i.updated_at) FROM issues i WHERE {where}",
            visible_params,
        ).fetchone()[0]

        daemon = conn.execute(
            """
            SELECT last_poll_at, last_poll_fetched, last_poll_new,
                   last_poll_total_count, last_poll_message
            FROM daemon_state WHERE id = 1
            """
        ).fetchone()

        return {
            "total": total,
            "pending": pending,
            "complete": complete,
            "errors": errors,
            "bookmarked": bookmarked,
            "last_updated": last_updated,
            "last_poll_at": daemon["last_poll_at"] if daemon else None,
            "last_poll_fetched": daemon["last_poll_fetched"] if daemon else 0,
            "last_poll_new": daemon["last_poll_new"] if daemon else 0,
            "last_poll_total_count": daemon["last_poll_total_count"] if daemon else 0,
            "last_poll_message": daemon["last_poll_message"] if daemon else None,
        }


def get_pr_stats() -> dict[str, Any]:
    with get_connection() as conn:
        open_prs = conn.execute("SELECT COUNT(*) FROM pulls WHERE state = 'open'").fetchone()[0]
        reviews_ready = conn.execute(
            "SELECT COUNT(*) FROM pr_reviews WHERE review_markdown IS NOT NULL AND posted_to_github = 0"
        ).fetchone()[0]
        reviews_posted = conn.execute("SELECT COUNT(*) FROM pr_reviews WHERE posted_to_github = 1").fetchone()[0]
        reviewing = conn.execute("SELECT COUNT(*) FROM pr_reviews WHERE status = 'reviewing'").fetchone()[0]
        return {
            "open_prs": open_prs,
            "reviews_ready": reviews_ready,
            "reviews_posted": reviews_posted,
            "reviewing": reviewing,
        }


def get_personal_stats() -> dict[str, Any]:
    with get_connection() as conn:
        bookmarked = conn.execute("SELECT COUNT(*) FROM issues WHERE bookmarked = 1 AND dismissed = 0").fetchone()[0]
        claimed = conn.execute("SELECT COUNT(*) FROM issues WHERE claimed = 1 AND dismissed = 0").fetchone()[0]
        triaged = conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'complete' AND dismissed = 0").fetchone()[0]
        lang_rows = conn.execute(
            "SELECT language, COUNT(*) as cnt FROM issues"
            " WHERE language IS NOT NULL AND language != '' AND dismissed = 0"
            " GROUP BY language ORDER BY cnt DESC"
        ).fetchall()
        diff_rows = conn.execute(
            "SELECT t.difficulty, COUNT(*) as cnt FROM issues i"
            " JOIN triage_reports t ON t.issue_id = i.id"
            " WHERE i.dismissed = 0 AND t.difficulty IS NOT NULL"
            " GROUP BY t.difficulty"
        ).fetchall()
        return {
            "bookmarked": bookmarked,
            "claimed": claimed,
            "triaged": triaged,
            "languages": {r["language"]: r["cnt"] for r in lang_rows},
            "difficulties": {r["difficulty"]: r["cnt"] for r in diff_rows},
        }


def dismiss_repo_issues(repo_full_name: str) -> int:
    now = _utcnow()
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE issues SET dismissed = 1, updated_at = ? WHERE repo_full_name = ? AND dismissed = 0",
            (now, repo_full_name),
        )
        return cursor.rowcount


def update_poll_state(
    fetched: int,
    new_count: int,
    total_count: int,
    message: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE daemon_state SET
                last_poll_at = ?,
                last_poll_fetched = ?,
                last_poll_new = ?,
                last_poll_total_count = ?,
                last_poll_message = ?,
                poll_requested = 0
            WHERE id = 1
            """,
            (_utcnow(), fetched, new_count, total_count, message),
        )


def request_poll() -> None:
    with get_connection() as conn:
        conn.execute("UPDATE daemon_state SET poll_requested = 1 WHERE id = 1")


def get_last_poll_time() -> datetime | None:
    with get_connection() as conn:
        row = conn.execute("SELECT last_poll_at FROM daemon_state WHERE id = 1").fetchone()
        if row and row["last_poll_at"]:
            dt = datetime.fromisoformat(row["last_poll_at"])
            return dt.replace(tzinfo=timezone.utc)
        return None


def is_poll_requested() -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT poll_requested FROM daemon_state WHERE id = 1").fetchone()
        return bool(row and row["poll_requested"])


def get_preferences() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT languages, labels, min_stars, show_dismissed FROM user_preferences WHERE id = 1"
        ).fetchone()
        if not row:
            return _default_preferences()
        return {
            "languages": json.loads(row["languages"]),
            "labels": json.loads(row["labels"]),
            "min_stars": row["min_stars"],
            "show_dismissed": bool(row["show_dismissed"]),
        }


def save_preferences(prefs: dict[str, Any]) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE user_preferences SET
                languages = ?,
                labels = ?,
                min_stars = ?,
                show_dismissed = ?
            WHERE id = 1
            """,
            (
                json.dumps(prefs.get("languages", [])),
                json.dumps(prefs.get("labels", [])),
                prefs.get("min_stars", settings.min_repo_stars),
                1 if prefs.get("show_dismissed") else 0,
            ),
        )
    return get_preferences()


def _default_preferences() -> dict[str, Any]:
    return {
        "languages": ["javascript", "typescript", "python"],
        "labels": ["good first issue", "help wanted", "bug", "enhancement", "feature", "fix", "improvement"],
        "min_stars": 500,
        "show_dismissed": False,
    }


def enqueue_webhook(payload: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO webhook_queue (payload) VALUES (?)",
            (json.dumps(payload),),
        )
        return cursor.lastrowid


def fetch_pending_webhooks(limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, payload, created_at FROM webhook_queue
            WHERE processed = 0
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result


def mark_webhook_processed(webhook_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE webhook_queue SET processed = 1 WHERE id = ?",
            (webhook_id,),
        )


def clear_all_data() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            DELETE FROM triage_reports;
            DELETE FROM issues;
            DELETE FROM seen_issues;
            DELETE FROM webhook_queue;
            UPDATE daemon_state SET
                last_poll_at = NULL, last_poll_fetched = 0,
                last_poll_new = 0, last_poll_total_count = 0,
                last_poll_message = NULL, poll_requested = 0
            WHERE id = 1;
            """
        )


def _row_to_issue(row: sqlite3.Row) -> dict[str, Any]:
    issue = dict(row)
    issue["labels"] = json.loads(issue.get("labels") or "[]")
    issue["bookmarked"] = bool(issue.get("bookmarked"))
    issue["dismissed"] = bool(issue.get("dismissed"))
    issue["claimed"] = bool(issue.get("claimed"))
    difficulty = issue.pop("difficulty", None)
    pr_url = issue.pop("pr_url", None)
    pr_head_sha = issue.pop("pr_head_sha", None)
    pr_status = issue.pop("pr_status", None)
    pr_checked_at = issue.pop("pr_checked_at", None)
    claim_comment = issue.pop("claim_comment", None)
    claim_variants = []
    if claim_comment:
        if claim_comment.startswith("["):
            try:
                claim_variants = json.loads(claim_comment)
                claim_comment = claim_variants[0] if claim_variants else ""
            except json.JSONDecodeError:
                claim_variants = [claim_comment]
        else:
            claim_variants = [claim_comment]
    triage = None
    if issue.get("architecture_context") is not None:
        triage = {
            "architecture_context": issue.pop("architecture_context"),
            "issue_breakdown": issue.pop("issue_breakdown"),
            "action_plan": issue.pop("action_plan"),
            "raw_response": issue.pop("triage_raw"),
            "pr_url": pr_url,
            "pr_head_sha": pr_head_sha,
            "pr_status": pr_status,
            "pr_checked_at": pr_checked_at,
            "claim_comment": claim_comment,
            "claim_variants": claim_variants,
        }
    else:
        issue.pop("architecture_context", None)
        issue.pop("issue_breakdown", None)
        issue.pop("action_plan", None)
        issue.pop("triage_raw", None)
    issue["triage"] = triage
    issue["difficulty"] = difficulty
    issue["is_priority"] = bool(issue.get("is_priority", False))
    issue["is_bounty"] = bool(issue.get("is_bounty", False))
    return issue


# ── Priority Repos ──────────────────────────────────────────


def get_priority_repos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, owner, repo, full_name, added_at, "
            "COALESCE(is_high_priority, 0) AS is_high_priority, "
            "COALESCE(is_org, 0) AS is_org, "
            "COALESCE(is_small_target, 0) AS is_small_target "
            "FROM priority_repos ORDER BY is_high_priority DESC, added_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_small_target_repos() -> list[dict[str, Any]]:
    """Small active repos that actively merge contributor PRs.

    Their issues are surfaced regardless of age (no created-date filter) so
    long-lived good-first-issues from these repos always appear in the feed.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, owner, repo, full_name, added_at, "
            "COALESCE(is_high_priority, 0) AS is_high_priority, "
            "COALESCE(is_small_target, 0) AS is_small_target "
            "FROM priority_repos WHERE COALESCE(is_small_target, 0) = 1 "
            "ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]


def add_priority_repo(full_name: str, is_high_priority: bool = False) -> dict[str, Any] | None:
    parts = full_name.strip().split("/")
    if len(parts) == 1:
        owner = parts[0]
        is_org = 1
        repo = f".org-{owner}"
    elif len(parts) == 2:
        owner, repo = parts
        is_org = 0
    else:
        return None
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO priority_repos (owner, repo, full_name, is_org, is_high_priority) VALUES (?, ?, ?, ?, ?)",
                (owner, repo, full_name, is_org, 1 if is_high_priority else 0),
            )
            return {
                "id": cursor.lastrowid,
                "owner": owner,
                "repo": repo,
                "full_name": full_name,
                "is_org": bool(is_org),
                "is_high_priority": is_high_priority,
            }
        except sqlite3.IntegrityError:
            return None


def set_priority_repo_flags(
    full_name: str,
    *,
    is_high_priority: bool | None = None,
    is_small_target: bool | None = None,
) -> bool:
    """Update flags on a priority repo; returns True if a row was updated."""
    with get_connection() as conn:
        fields, values = [], []
        if is_high_priority is not None:
            fields.append("is_high_priority = ?")
            values.append(1 if is_high_priority else 0)
        if is_small_target is not None:
            fields.append("is_small_target = ?")
            values.append(1 if is_small_target else 0)
        if not fields:
            return False
        values.append(full_name)
        cursor = conn.execute(
            f"UPDATE priority_repos SET {', '.join(fields)} WHERE full_name = ?",
            tuple(values),
        )
        return cursor.rowcount > 0


def remove_priority_repo(repo_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM priority_repos WHERE id = ?", (repo_id,))
        return cursor.rowcount > 0


def clear_priority_repos() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM priority_repos")


def replace_priority_repos(full_names: list[str], high_priority: set[str] | None = None) -> list[dict[str, Any]]:
    clear_priority_repos()
    high_priority = high_priority or set()
    added: list[dict[str, Any]] = []
    for full_name in full_names:
        result = add_priority_repo(full_name, full_name in high_priority)
        if result:
            added.append(result)
    return added


def is_priority_repo(full_name: str) -> bool:
    owner = full_name.split("/", 1)[0] if "/" in full_name else full_name
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM priority_repos WHERE full_name = ? OR (is_org = 1 AND owner = ?) LIMIT 1",
            (full_name, owner),
        ).fetchone()
        return row is not None


def resync_issue_priority_flags() -> int:
    with get_connection() as conn:
        conn.execute("UPDATE issues SET is_priority = 0")
        updated = 0
        for full_name, is_org in conn.execute("SELECT full_name, is_org FROM priority_repos").fetchall():
            if is_org:
                cur = conn.execute(
                    "UPDATE issues SET is_priority = 1 WHERE repo_full_name LIKE ?",
                    (full_name + "/%",),
                )
            else:
                cur = conn.execute(
                    "UPDATE issues SET is_priority = 1 WHERE repo_full_name = ?",
                    (full_name,),
                )
            updated += cur.rowcount
        return updated


# ── General Repos (general feed scope) ──────────────────────


def get_general_repos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, owner, repo, full_name, added_at FROM general_repos ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]


def add_general_repo(full_name: str) -> dict[str, Any] | None:
    parts = full_name.strip().split("/")
    if len(parts) != 2:
        return None
    owner, repo = parts
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO general_repos (owner, repo, full_name) VALUES (?, ?, ?)",
                (owner, repo, full_name),
            )
            return {
                "id": cursor.lastrowid,
                "owner": owner,
                "repo": repo,
                "full_name": full_name,
                "is_org": False,
            }
        except sqlite3.IntegrityError:
            return None


def remove_general_repo(repo_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM general_repos WHERE id = ?", (repo_id,))
        return cursor.rowcount > 0


def clear_general_repos() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM general_repos")


def replace_general_repos(full_names: list[str]) -> list[dict[str, Any]]:
    clear_general_repos()
    added: list[dict[str, Any]] = []
    for full_name in full_names:
        result = add_general_repo(full_name)
        if result:
            added.append(result)
    return added


def set_issue_difficulty(issue_id: int, difficulty: str | None) -> bool:
    if difficulty not in ("easy", "medium", "hard", None):
        return False
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE triage_reports SET difficulty = ? WHERE issue_id = ?",
            (difficulty, issue_id),
        )
        return cursor.rowcount > 0


def save_pr_info(issue_id: int, pr_url: str, head_sha: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE triage_reports
               SET pr_url = ?, pr_head_sha = ?, pr_status = 'open', pr_checked_at = ?
               WHERE issue_id = ?""",
            (pr_url, head_sha, _utcnow(), issue_id),
        )


def get_prs_pending_checks() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT t.issue_id, t.pr_url, t.pr_head_sha, i.repo_full_name
               FROM triage_reports t
               JOIN issues i ON i.id = t.issue_id
               WHERE t.pr_url IS NOT NULL
                 AND t.pr_status NOT IN ('success', 'failure', 'merged', 'closed', 'error')"""
        ).fetchall()
        return [dict(r) for r in rows]


def update_pr_status(issue_id: int, status: str) -> None:
    now = _utcnow()
    with get_connection() as conn:
        conn.execute(
            "UPDATE triage_reports SET pr_status = ?, pr_checked_at = ? WHERE issue_id = ?",
            (status, now, issue_id),
        )
        conn.execute(
            "UPDATE issues SET updated_at = ? WHERE id = ?",
            (now, issue_id),
        )


def get_errored_issues_for_retry(max_retries: int = 3) -> list[dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT i.*
               FROM issues i
               WHERE i.status = 'error'
                 AND (i.retry_count IS NULL OR i.retry_count < ?)
                 AND (
                   i.updated_at IS NULL
                   OR datetime(i.updated_at, '+' || (i.retry_count + 1) || ' minutes') <= datetime('now')
                 )
               ORDER BY i.updated_at ASC
               LIMIT 10""",
            (max_retries,),
        ).fetchall()
        return [dict(r) for r in rows]


def increment_retry_count(issue_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE issues SET retry_count = COALESCE(retry_count, 0) + 1, updated_at = ? WHERE id = ?",
            (_utcnow(), issue_id),
        )


def reset_retry_count(issue_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE issues SET retry_count = 0, updated_at = ? WHERE id = ?",
            (_utcnow(), issue_id),
        )


def upsert_pull(
    *,
    repo_full_name: str,
    number: int,
    title: str,
    body: str | None,
    html_url: str,
    head_sha: str | None,
    base_sha: str | None,
    base_ref: str | None,
    author: str | None,
    state: str,
    labels: list[str],
    head_label: str | None,
    is_priority: bool,
    ingested_via: str,
) -> int:
    """Insert or update a pull request; returns the pulls.id."""
    now = _utcnow()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM pulls WHERE repo_full_name = ? AND number = ?",
            (repo_full_name, number),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE pulls
                   SET title = ?, body = ?, html_url = ?, head_sha = ?, base_sha = ?,
                       base_ref = ?, author = ?, state = ?, labels = ?, head_label = ?,
                       is_priority = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    title,
                    body,
                    html_url,
                    head_sha,
                    base_sha,
                    base_ref,
                    author,
                    state,
                    json.dumps(labels),
                    head_label,
                    1 if is_priority else 0,
                    now,
                    existing["id"],
                ),
            )
            pull_id = existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO pulls
                   (repo_full_name, number, title, body, html_url, head_sha, base_sha,
                    base_ref, author, state, labels, head_label, is_priority, ingested_via)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    repo_full_name,
                    number,
                    title,
                    body,
                    html_url,
                    head_sha,
                    base_sha,
                    base_ref,
                    author,
                    state,
                    json.dumps(labels),
                    head_label,
                    1 if is_priority else 0,
                    ingested_via,
                ),
            )
            pull_id = cursor.lastrowid
        return pull_id


def has_pull(repo_full_name: str, number: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM pulls WHERE repo_full_name = ? AND number = ?",
            (repo_full_name, number),
        ).fetchone()
        return row is not None


def list_open_prs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT p.*, pr.id AS review_id, pr.status AS review_status,
                      pr.review_markdown, pr.posted_to_github, pr.github_review_id,
                      pr.updated_at AS review_updated_at
               FROM pulls p
               LEFT JOIN pr_reviews pr ON pr.pull_id = p.id
               WHERE p.state = 'open'
               ORDER BY
                 -- Pulls needing attention first: ready reviews, then queued, then fresh
                 CASE WHEN pr.review_markdown IS NOT NULL THEN 0
                      WHEN pr.status = 'reviewing' THEN 1
                      ELSE 2 END,
                 p.updated_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pull(pull_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT p.*, pr.id AS review_id, pr.status AS review_status,
                      pr.review_markdown, pr.posted_to_github, pr.github_review_id,
                      pr.error_message AS review_error, pr.updated_at AS review_updated_at
               FROM pulls p
               LEFT JOIN pr_reviews pr ON pr.pull_id = p.id
               WHERE p.id = ?""",
            (pull_id,),
        ).fetchone()
        return dict(row) if row else None


def get_pull_by_repo_number(repo_full_name: str, number: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM pulls WHERE repo_full_name = ? AND number = ?",
            (repo_full_name, number),
        ).fetchone()
        return dict(row) if row else None


def save_pr_review(
    pull_id: int,
    review_markdown: str,
    *,
    status: str = "ready",
) -> int:
    """Store a completed (or updated) review; returns pr_reviews.id."""
    now = _utcnow()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM pr_reviews WHERE pull_id = ?",
            (pull_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE pr_reviews
                   SET review_markdown = ?, status = ?, error_message = NULL, updated_at = ?
                   WHERE id = ?""",
                (review_markdown, status, now, existing["id"]),
            )
            review_id = existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO pr_reviews (pull_id, review_markdown, status)
                   VALUES (?, ?, ?)""",
                (pull_id, review_markdown, status),
            )
            review_id = cursor.lastrowid
        conn.execute(
            "UPDATE pulls SET updated_at = ? WHERE id = ?",
            (now, pull_id),
        )
        return review_id


def mark_review_queued(pull_id: int) -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM pr_reviews WHERE pull_id = ?",
            (pull_id,),
        ).fetchone()
        now = _utcnow()
        if row:
            conn.execute(
                "UPDATE pr_reviews SET status = 'reviewing', error_message = NULL, updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO pr_reviews (pull_id, status) VALUES (?, 'reviewing')",
                (pull_id,),
            )


def mark_review_error(pull_id: int, message: str) -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM pr_reviews WHERE pull_id = ?",
            (pull_id,),
        ).fetchone()
        now = _utcnow()
        if row:
            conn.execute(
                """UPDATE pr_reviews SET status = 'error', error_message = ?, updated_at = ?
                   WHERE id = ?""",
                (message, now, row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO pr_reviews (pull_id, status, error_message)
                   VALUES (?, 'error', ?)""",
                (pull_id, message),
            )


def mark_review_posted(pull_id: int, github_review_id: int) -> None:
    now = _utcnow()
    with get_connection() as conn:
        conn.execute(
            """UPDATE pr_reviews
               SET posted_to_github = 1, github_review_id = ?, updated_at = ?
               WHERE pull_id = ?""",
            (github_review_id, now, pull_id),
        )
        conn.execute(
            "UPDATE pulls SET updated_at = ? WHERE id = ?",
            (now, pull_id),
        )


def get_pulls_needing_review(limit: int = 5) -> list[dict[str, Any]]:
    """PRs explicitly queued for review by the user (status='reviewing' or 'error').

    Reviews are strictly on-demand: nothing is reviewed until the user clicks
    "Get review" in the UI, which flips the PR to 'reviewing'. No auto-drip,
    no background generation. 'error' rows are retried so a user-requested
    review that transiently failed gets completed.
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT p.*, pr.id AS review_id, pr.status AS review_status, pr.error_message
               FROM pulls p
               JOIN pr_reviews pr ON pr.pull_id = p.id
               WHERE p.state = 'open'
                 AND pr.status IN ('reviewing', 'error')
               ORDER BY p.updated_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def has_posted_review(pull_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT posted_to_github FROM pr_reviews WHERE pull_id = ?",
            (pull_id,),
        ).fetchone()
        return bool(row and row["posted_to_github"])
