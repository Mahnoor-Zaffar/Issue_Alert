import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

MIGRATIONS = [
    "ALTER TABLE issues ADD COLUMN repo_stars INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN score REAL NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN bookmarked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE issues ADD COLUMN dismissed INTEGER NOT NULL DEFAULT 0",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
        "SELECT labels FROM user_preferences WHERE id = 1"
    ).fetchone()
    if row:
        labels = json.loads(row["labels"] or "[]")
        if len(labels) > 2 or "open source" in labels or "open-source" in labels:
            conn.execute(
                """
                UPDATE user_preferences
                SET labels = '["good first issue","help wanted"]', min_stars = 0
                WHERE id = 1
                """
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

    label_boost = {
        "good first issue": 30,
        "help wanted": 20,
        "open source": 10,
        "open-source": 10,
    }
    for label in issue.get("labels", []):
        score += label_boost.get(label.lower(), 0)

    body = issue.get("body") or ""
    if len(body.strip()) > 100:
        score += 10
    elif not body.strip():
        score -= 5

    return round(score, 2)


def insert_issue(issue: dict[str, Any]) -> int:
    now = _utcnow()
    score = issue.get("score")
    if score is None:
        score = compute_score(issue)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO issues (
                github_id, title, body, html_url, repo_full_name,
                repo_clone_url, labels, language, repo_stars, score,
                state, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                issue.get("state", "open"),
                issue.get("status", "pending"),
                now,
                now,
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
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO triage_reports (
                issue_id, architecture_context, issue_breakdown,
                action_plan, raw_response
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                architecture_context,
                issue_breakdown,
                action_plan,
                raw_response,
            ),
        )


def get_issue(issue_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw
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
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []

    if not show_dismissed:
        clauses.append("i.dismissed = 0")
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

    where = " AND ".join(clauses)
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE {where}
            ORDER BY i.score DESC, i.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [_row_to_issue(row) for row in rows]


def get_issues_updated_since(since: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            WHERE i.updated_at > ?
            ORDER BY i.updated_at ASC
            """,
            (since,),
        ).fetchall()
        return [_row_to_issue(row) for row in rows]


def get_stats() -> dict[str, Any]:
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE dismissed = 0"
        ).fetchone()[0]
        pending = conn.execute(
            """
            SELECT COUNT(*) FROM issues
            WHERE dismissed = 0 AND status NOT IN ('complete', 'error')
            """
        ).fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE status = 'complete' AND dismissed = 0"
        ).fetchone()[0]
        errors = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE status = 'error' AND dismissed = 0"
        ).fetchone()[0]
        bookmarked = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE bookmarked = 1 AND dismissed = 0"
        ).fetchone()[0]
        last_updated = conn.execute(
            "SELECT MAX(updated_at) FROM issues"
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
        "languages": ["javascript", "python", "go", "rust"],
        "labels": ["good first issue", "help wanted"],
        "min_stars": 0,
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
    return issue
