import asyncio
import logging
from typing import Any

from config.settings import settings
from daemon.context_extractor import extract_repo_context
from daemon.notifier import notify_new_issue
from daemon.poller import (
    GitHubPoller,
    matches_language_preference,
    passes_claim_verification,
)
from daemon.triage import TriageEngine
from db.store import (
    fetch_pending_webhooks,
    get_preferences,
    init_db,
    insert_issue,
    insert_triage_report,
    is_issue_seen,
    is_poll_requested,
    mark_issue_seen,
    mark_webhook_processed,
    purge_stale_issues,
    update_issue_status,
    update_poll_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def process_issue(issue_data: dict[str, Any], triage_engine: TriageEngine) -> bool:
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

    if not (issue_data.get("body") or "").strip() and not issue_data.get("title"):
        mark_issue_seen(github_id)
        logger.info("Skipping issue %s — empty title and body", github_id)
        return False

    issue_id = insert_issue(issue_data)
    mark_issue_seen(github_id)
    logger.info("New issue #%d: %s", issue_id, issue_data["title"])

    notify_new_issue(
        issue_data["title"],
        issue_data["repo_full_name"],
        issue_data["html_url"],
    )
    update_issue_status(issue_id, "notified")

    update_issue_status(issue_id, "extracting")
    file_context = await asyncio.to_thread(
        extract_repo_context, issue_data["repo_clone_url"]
    )

    update_issue_status(issue_id, "triaging")
    try:
        if not (issue_data.get("body") or "").strip() and not file_context:
            logger.info("Skipping LLM triage for #%d — no body or file context", issue_id)
            insert_triage_report(
                issue_id=issue_id,
                architecture_context="Insufficient context — issue body is empty and repo clone yielded no files.",
                issue_breakdown=issue_data.get("title", ""),
                action_plan="Review the issue on GitHub directly before contributing.",
                raw_response="",
            )
            update_issue_status(issue_id, "complete")
            return True

        result = await triage_engine.triage(
            title=issue_data["title"],
            body=issue_data["body"],
            labels=issue_data["labels"],
            language=issue_data.get("language"),
            repo_url=issue_data["html_url"],
            file_context=file_context,
        )
        insert_triage_report(
            issue_id=issue_id,
            architecture_context=result["architecture_context"],
            issue_breakdown=result["issue_breakdown"],
            action_plan=result["action_plan"],
            raw_response=result["raw_response"],
        )
        update_issue_status(issue_id, "complete")
        logger.info("Triage complete for issue #%d", issue_id)

    except Exception as exc:
        logger.exception("Triage failed for issue #%d", issue_id)
        update_issue_status(issue_id, "error", str(exc))

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


async def poll_cycle(poller: GitHubPoller, triage_engine: TriageEngine) -> None:
    purged = purge_stale_issues()
    if purged:
        logger.info("Purged %d stale or viewed issue(s) from feed", purged)

    await process_webhooks(poller, triage_engine)

    issues, total_count = await poller.fetch_issues()
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

        if await process_issue(issue_data, triage_engine):
            new_count += 1

    message = f"{skipped_seen} already seen" if skipped_seen else None
    update_poll_state(len(issues), new_count, total_count, message)
    logger.info(
        "Poll cycle complete: %d fetched, %d new, %d already seen (total on GitHub: %d)",
        len(issues),
        new_count,
        skipped_seen,
        total_count,
    )


async def interruptible_sleep(seconds: int) -> bool:
    for _ in range(seconds):
        if is_poll_requested():
            logger.info("Poll requested — running early")
            return True
        await asyncio.sleep(1)
    return False


async def run() -> None:
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
                update_poll_state(0, 0, 0, "Poll cycle failed — see logs")

            await interruptible_sleep(settings.poll_interval_seconds)
    finally:
        await poller.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
