import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text())


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


def insert_issue(issue: dict[str, Any]) -> int:
    now = _utcnow()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO issues (
                github_id, title, body, html_url, repo_full_name,
                repo_clone_url, labels, language, state, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def list_issues(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT i.*,
                   t.architecture_context, t.issue_breakdown,
                   t.action_plan, t.raw_response AS triage_raw
            FROM issues i
            LEFT JOIN triage_reports t ON t.issue_id = i.id
            ORDER BY i.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
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
        total = conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE status NOT IN ('complete', 'error')"
        ).fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE status = 'complete'"
        ).fetchone()[0]
        last_updated = conn.execute(
            "SELECT MAX(updated_at) FROM issues"
        ).fetchone()[0]
        return {
            "total": total,
            "pending": pending,
            "complete": complete,
            "last_updated": last_updated,
        }


def _row_to_issue(row: sqlite3.Row) -> dict[str, Any]:
    issue = dict(row)
    issue["labels"] = json.loads(issue.get("labels") or "[]")
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
