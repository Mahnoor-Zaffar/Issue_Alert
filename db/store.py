import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

MIGRATIONS = [
    "ALTER TABLE issues ADD COLUMN repo_stars INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN score REAL NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN bookmarked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN viewed_at TEXT",
    "ALTER TABLE issues ADD COLUMN github_created_at TEXT",
    "ALTER TABLE issues ADD COLUMN comments INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN is_priority INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE triage_reports ADD COLUMN difficulty TEXT",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _freshness_cutoff_iso() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.issue_discovery_window_minutes
    )
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
    if not bookmarked_only:
        clauses.append("i.viewed_at IS NULL")
    if not include_stale:
        clauses.append(
            "(i.github_created_at IS NOT NULL AND i.github_created_at >= ?)"
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

    row = conn.execute(
        "SELECT labels, min_stars, languages FROM user_preferences WHERE id = 1"
    ).fetchone()
    if row:
        labels = json.loads(row["labels"] or "[]")
        min_stars = row["min_stars"]
        languages = json.loads(row["languages"] or "[]")
        needs_update = False

        new_labels = ["bug", "feature", "enhancement", "help wanted", "good first issue", "task", "improvement", "fix", "bugfix", "feature request", "todo"]
        old_default_labels = {"good first issue", "help wanted"}
        prev_default_labels = {"bug", "feature", "enhancement", "help wanted"}
        labels_set = set(labels)
        if labels_set == old_default_labels or labels_set == prev_default_labels:
            labels = list(new_labels)
            needs_update = True
        elif "open source" in labels or "open-source" in labels:
            labels = [l for l in labels if l not in ("open source", "open-source")]
            needs_update = True

        old_default_languages = {"javascript", "python", "go", "rust"}
        new_default_languages = {"javascript", "python"}
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
        row = conn.execute(
            "SELECT 1 FROM seen_issues WHERE github_id = ?", (github_id,)
        ).fetchone()
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

    return round(score, 2)


def insert_issue(issue: dict[str, Any]) -> int:
    now = _utcnow()
    score = issue.get("score")
    if score is None:
        score = compute_score(issue)
    github_created_at = issue.get("created_at") or now

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO issues (
                github_id, title, body, html_url, repo_full_name,
                repo_clone_url, labels, language, repo_stars, score,
                comments, state, status, github_created_at, created_at,
                updated_at, is_priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        return cursor.lastrowid


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
    cutoff = _freshness_cutoff_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM issues
            WHERE bookmarked = 0
              AND (viewed_at IS NOT NULL
                OR github_created_at IS NULL
                OR github_created_at < ?)
            """,
            (cutoff,),
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
        rows = conn.execute(
            "SELECT issue_id FROM triage_requests ORDER BY created_at ASC"
        ).fetchall()
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
    if field not in ("bookmarked", "dismissed"):
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
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO triage_reports (
                issue_id, architecture_context, issue_breakdown,
                action_plan, raw_response, difficulty
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                architecture_context,
                issue_breakdown,
                action_plan,
                raw_response,
                difficulty,
            ),
        )


def get_issue(issue_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw,
                   t.difficulty
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
    is_priority: bool | None = None,
    difficulty: str | None = None,
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
    if is_priority is not None:
        clauses.append("i.is_priority = ?")
        params.append(1 if is_priority else 0)
    if difficulty:
        clauses.append("t.difficulty = ?")
        params.append(difficulty)

    where = " AND ".join(clauses)
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw,
                   t.difficulty
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE {where}
            ORDER BY i.github_created_at DESC, i.score DESC
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
                   t.difficulty
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
        row = conn.execute(
            "SELECT last_poll_at FROM daemon_state WHERE id = 1"
        ).fetchone()
        if row and row["last_poll_at"]:
            dt = datetime.fromisoformat(row["last_poll_at"])
            return dt.replace(tzinfo=timezone.utc)
        return None


def is_poll_requested() -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT poll_requested FROM daemon_state WHERE id = 1"
        ).fetchone()
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
        "languages": ["javascript", "python"],
        "labels": ["bug", "feature", "enhancement", "help wanted", "good first issue", "task", "improvement", "fix", "bugfix", "feature request", "todo"],
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
    difficulty = issue.pop("difficulty", None)
    triage = None
    if issue.get("architecture_context") is not None:
        triage = {
            "architecture_context": issue.pop("architecture_context"),
            "issue_breakdown": issue.pop("issue_breakdown"),
            "action_plan": issue.pop("action_plan"),
            "raw_response": issue.pop("triage_raw"),
        }
    else:
        issue.pop("architecture_context", None)
        issue.pop("issue_breakdown", None)
        issue.pop("action_plan", None)
        issue.pop("triage_raw", None)
    issue["triage"] = triage
    issue["difficulty"] = difficulty
    issue["is_priority"] = bool(issue.get("is_priority", False))
    return issue


# ── Priority Repos ──────────────────────────────────────────

def get_priority_repos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, owner, repo, full_name, added_at FROM priority_repos ORDER BY added_at"
        ).fetchall()
        return [dict(r) for r in rows]


def add_priority_repo(full_name: str) -> dict[str, Any] | None:
    parts = full_name.strip().split("/")
    if len(parts) != 2:
        return None
    owner, repo = parts
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO priority_repos (owner, repo, full_name) VALUES (?, ?, ?)",
                (owner, repo, full_name),
            )
            return {"id": cursor.lastrowid, "owner": owner, "repo": repo, "full_name": full_name}
        except sqlite3.IntegrityError:
            return None


def remove_priority_repo(repo_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM priority_repos WHERE id = ?", (repo_id,))
        return cursor.rowcount > 0


def set_issue_difficulty(issue_id: int, difficulty: str | None) -> bool:
    if difficulty not in ("easy", "medium", "hard", None):
        return False
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE triage_reports SET difficulty = ? WHERE issue_id = ?",
            (difficulty, issue_id),
        )
        return cursor.rowcount > 0
