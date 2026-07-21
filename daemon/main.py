import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx

from config.settings import settings
from daemon.context_extractor import extract_repo_context
from daemon.notifier import notify_new_issue
from daemon.poller import (
    GitHubPoller,
    matches_label_preference,
    matches_language_preference,
    passes_claim_verification,
)
from daemon.triage import TriageEngine
from db.store import (
    dequeue_triage,
    fetch_pending_webhooks,
    get_errored_issues_for_retry,
    get_issue,
    get_pending_triage_requests,
    get_preferences,
    get_prs_pending_checks,
    increment_retry_count,
    init_db,
    insert_issue,
    insert_triage_report,
    is_issue_seen,
    is_poll_requested,
    mark_issue_seen,
    mark_webhook_processed,
    parse_difficulty,
    purge_stale_issues,
    record_daily_stats,
    reset_retry_count,
    update_issue_status,
    update_poll_state,
    update_pr_status,
)

LOG_FILE = Path(__file__).resolve().parent.parent / "data" / "daemon.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1024 * 512, backupCount=2),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
DAEMON_LOCK = settings.database_path.parent / "daemon.pid"


def acquire_daemon_lock() -> None:
    """Ensure only one daemon process polls GitHub at a time."""
    DAEMON_LOCK.parent.mkdir(parents=True, exist_ok=True)
    if DAEMON_LOCK.exists():
        try:
            old_pid = int(DAEMON_LOCK.read_text().strip())
            os.kill(old_pid, 0)
            logger.error(
                "Another daemon is already running (PID %d). Stop it before starting a new one: pkill -f 'daemon.main'",
                old_pid,
            )
            sys.exit(1)
        except ValueError, OSError:
            pass
    DAEMON_LOCK.write_text(str(os.getpid()))


def release_daemon_lock() -> None:
    if not DAEMON_LOCK.exists():
        return
    try:
        if int(DAEMON_LOCK.read_text().strip()) == os.getpid():
            DAEMON_LOCK.unlink()
    except ValueError, OSError:
        pass


def _passes_quality_gate(issue: dict[str, Any]) -> bool:
    body = (issue.get("body") or "").strip()
    title = (issue.get("title") or "").strip()
    github_id = issue.get("github_id", "?")

    if not body and len(title) < 15:
        logger.info("Skipping issue %s — no body and short title: %r", github_id, title)
        return False

    if len(body) < 30:
        logger.info("Skipping issue %s — body too short (%d chars)", github_id, len(body))
        return False

    spam_signals = ["http://", "https://", "buy ", "free ", "click here"]
    body_lower = body.lower()
    if any(signal in body_lower for signal in spam_signals) and len(body) < 100:
        logger.info("Skipping issue %s — looks like spam", github_id)
        return False

    return True


async def process_issue(issue_data: dict[str, Any], triage_engine: TriageEngine, notify: bool = True) -> bool:
    github_id = issue_data["github_id"]
    if is_issue_seen(github_id):
        return False

    if not passes_claim_verification(issue_data):
        mark_issue_seen(github_id)
        logger.info(
            "Skipping issue %s — failed claim verification (assigned, commented, or linked PR)",
            github_id,
        )
        return False

    issue_id = insert_issue(issue_data)
    mark_issue_seen(github_id)
    logger.info("New issue #%d: %s", issue_id, issue_data["title"])

    if notify:
        notify_new_issue(
            issue_data["title"],
            issue_data["repo_full_name"],
            issue_data["html_url"],
            priority=issue_data.get("is_priority", False),
        )
    update_issue_status(issue_id, "pending")

    return True


async def process_webhooks(poller: GitHubPoller, triage_engine: TriageEngine) -> int:
    processed = 0
    for entry in fetch_pending_webhooks():
        issue_data = poller.issue_from_webhook(entry["payload"])
        mark_webhook_processed(entry["id"])
        if issue_data and await process_issue(issue_data, triage_engine):
            processed += 1
    if processed:
        logger.info("Processed %d webhook issue(s)", processed)
    return processed


async def _triage_single(issue_id: int, triage_engine: TriageEngine, sem: asyncio.Semaphore) -> bool:
    issue = get_issue(issue_id)
    if not issue or issue["status"] == "complete":
        dequeue_triage(issue_id)
        return False

    async with sem:
        logger.info("Processing queued triage for issue #%d: %s", issue_id, issue["title"])
        update_issue_status(issue_id, "extracting")
        file_context, file_paths = await asyncio.to_thread(extract_repo_context, issue["repo_clone_url"])

        update_issue_status(issue_id, "triaging")
        try:
            result = await triage_engine.triage(
                title=issue["title"],
                body=issue["body"],
                labels=issue["labels"],
                language=issue.get("language"),
                repo_url=issue["html_url"],
                file_context=file_context,
                file_paths=file_paths,
            )
            difficulty = parse_difficulty(result["action_plan"])
            insert_triage_report(
                issue_id=issue_id,
                architecture_context=result["architecture_context"],
                issue_breakdown=result["issue_breakdown"],
                action_plan=result["action_plan"],
                raw_response=result["raw_response"],
                difficulty=difficulty,
                claim_comment=result.get("claim_comment"),
            )
            update_issue_status(issue_id, "complete")
            logger.info("Queued triage complete for issue #%d", issue_id)
        except Exception as exc:
            logger.exception("Queued triage failed for issue #%d", issue_id)
            update_issue_status(issue_id, "error", str(exc))

        dequeue_triage(issue_id)
        return True


async def process_triage_queue(poller: GitHubPoller, triage_engine: TriageEngine) -> int:
    issue_ids = get_pending_triage_requests()
    if not issue_ids:
        return 0
    sem = asyncio.Semaphore(3)
    results = await asyncio.gather(*[_triage_single(iid, triage_engine, sem) for iid in issue_ids])
    return sum(1 for r in results if r)


async def poll_cycle(poller: GitHubPoller, triage_engine: TriageEngine) -> None:
    purged = purge_stale_issues()
    if purged:
        logger.info("Purged %d stale or viewed issue(s) from feed", purged)

    await process_triage_queue(poller, triage_engine)
    await process_webhooks(poller, triage_engine)

    priority_issues = await poller.fetch_priority_issues()
    priority_new = 0
    for issue_data in priority_issues:
        if is_issue_seen(issue_data["github_id"]):
            continue
        if not matches_label_preference(issue_data, get_preferences()):
            mark_issue_seen(issue_data["github_id"])
            continue
        if not _passes_quality_gate(issue_data):
            mark_issue_seen(issue_data["github_id"])
            continue
        if await process_issue(issue_data, triage_engine, notify=True):
            priority_new += 1

    issues, total_count, search_note = await poller.fetch_issues()
    new_count = 0
    skipped_seen = 0

    for issue_data in issues:
        if is_issue_seen(issue_data["github_id"]):
            skipped_seen += 1
            continue

        if not matches_language_preference(issue_data, get_preferences()):
            mark_issue_seen(issue_data["github_id"])
            logger.debug(
                "Skipping issue %s — language %s not in preferences",
                issue_data["github_id"],
                issue_data.get("language"),
            )
            continue

        if not matches_label_preference(issue_data, get_preferences()):
            mark_issue_seen(issue_data["github_id"])
            logger.debug(
                "Skipping issue %s — labels %s not in preferences",
                issue_data["github_id"],
                issue_data.get("labels"),
            )
            continue

        if not _passes_quality_gate(issue_data):
            mark_issue_seen(issue_data["github_id"])
            continue

        if await process_issue(issue_data, triage_engine, notify=False):
            new_count += 1

    if search_note:
        message = search_note
    elif len(issues) == 0 and new_count == 0:
        comment_note = (
            "zero comments" if settings.max_issue_comments == 0 else f"≤{settings.max_issue_comments} comments"
        )
        message = (
            f"No fresh unclaimed issues in the last {settings.issue_discovery_window_minutes} minutes ({comment_note})"
        )
    elif skipped_seen:
        message = f"{skipped_seen} already seen"
    else:
        message = None

    update_poll_state(len(issues), new_count, total_count, message)
    parts = [
        f"{len(issues)} fetched, {new_count} new",
        f"{skipped_seen} already seen" if skipped_seen else None,
        f"{priority_new} priority" if priority_new else None,
    ]
    detail = ", ".join(p for p in parts if p)
    logger.info(
        "Poll cycle complete: %s (total on GitHub: %d)",
        detail,
        total_count,
    )

    record_daily_stats()
    await retry_errored_issues()
    await check_pr_checks()


async def _retry_single_issue(issue_row: dict[str, Any], sem: asyncio.Semaphore) -> None:
    issue_id = issue_row["id"]
    async with sem:
        logger.info("Retrying triage for issue #%d (attempt %d)", issue_id, issue_row.get("retry_count", 0) + 1)
        increment_retry_count(issue_id)
        issue_data = {
            "title": issue_row["title"],
            "body": issue_row.get("body", ""),
            "html_url": issue_row["html_url"],
            "repo_full_name": issue_row["repo_full_name"],
            "repo_clone_url": issue_row["repo_clone_url"],
            "labels": issue_row.get("labels", []),
            "language": issue_row.get("language"),
            "github_id": issue_row.get("github_id"),
        }
        if isinstance(issue_data["labels"], str):
            import json

            issue_data["labels"] = json.loads(issue_data["labels"])
        if issue_data["github_id"] is None:
            return
        from daemon.triage import TriageEngine

        triage_engine = TriageEngine()
        try:
            update_issue_status(issue_id, "extracting")
            file_context, file_paths = await asyncio.to_thread(extract_repo_context, issue_row["repo_clone_url"])
            update_issue_status(issue_id, "triaging")
            result = await triage_engine.triage(
                title=issue_data["title"],
                body=issue_data.get("body", ""),
                labels=issue_data["labels"],
                language=issue_data.get("language"),
                repo_url=issue_data["html_url"],
                file_context=file_context,
                file_paths=file_paths,
            )
            difficulty = parse_difficulty(result["action_plan"])
            insert_triage_report(
                issue_id=issue_id,
                architecture_context=result["architecture_context"],
                issue_breakdown=result["issue_breakdown"],
                action_plan=result["action_plan"],
                raw_response=result["raw_response"],
                difficulty=difficulty,
                claim_comment=result.get("claim_comment"),
            )
            update_issue_status(issue_id, "complete")
            reset_retry_count(issue_id)
            logger.info("Retry triage succeeded for issue #%d", issue_id)
        except Exception as exc:
            logger.exception("Retry triage failed for issue #%d", issue_id)
            update_issue_status(issue_id, "error", str(exc))


async def retry_errored_issues() -> None:
    errored = get_errored_issues_for_retry()
    if not errored:
        return
    sem = asyncio.Semaphore(3)
    tasks = [_retry_single_issue(row, sem) for row in errored]
    await asyncio.gather(*tasks)


async def check_pr_checks() -> None:
    pending = get_prs_pending_checks()
    if not pending:
        return
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        for pr in pending:
            try:
                owner_repo = pr["repo_full_name"]
                sha = pr["pr_head_sha"]
                resp = await client.get(
                    f"https://api.github.com/repos/{owner_repo}/commits/{sha}/check-runs",
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                check_runs = data.get("check_runs", [])
                if not check_runs:
                    continue
                concluded = [c for c in check_runs if c.get("status") == "completed"]
                if not concluded:
                    update_pr_status(pr["issue_id"], "pending")
                    continue
                all_success = all(c.get("conclusion") == "success" for c in concluded)
                update_pr_status(
                    pr["issue_id"],
                    "success" if all_success else "failure",
                )
                logger.info(
                    "PR check status for issue #%d: %s",
                    pr["issue_id"],
                    "success" if all_success else "failure",
                )
            except Exception:
                logger.exception("Failed to check PR checks for issue #%d", pr["issue_id"])


async def interruptible_sleep(seconds: int) -> bool:
    for _ in range(seconds):
        if is_poll_requested():
            logger.info("Poll requested — running early")
            return True
        await asyncio.sleep(1)
    return False


async def run() -> None:
    acquire_daemon_lock()
    init_db()
    poller = GitHubPoller()
    triage_engine = TriageEngine()

    logger.info(
        "Daemon started — polling every %ds (discovery window: last %d minutes)",
        settings.poll_interval_seconds,
        settings.issue_discovery_window_minutes,
    )

    try:
        while True:
            try:
                await poll_cycle(poller, triage_engine)
            except Exception:
                logger.exception("Poll cycle failed")
                update_poll_state(
                    0,
                    0,
                    0,
                    "Poll cycle failed — check daemon logs and GitHub token",
                )

            await interruptible_sleep(settings.poll_interval_seconds)
    finally:
        await poller.close()
        release_daemon_lock()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
