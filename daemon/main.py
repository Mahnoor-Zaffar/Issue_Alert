import asyncio
import logging
from typing import Any

from config.settings import settings
from daemon.context_extractor import extract_repo_context
from daemon.notifier import notify_new_issue
from daemon.poller import GitHubPoller
from daemon.triage import TriageEngine
from db.store import (
    init_db,
    insert_issue,
    insert_triage_report,
    is_issue_seen,
    mark_issue_seen,
    update_issue_status,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def process_issue(issue_data: dict[str, Any], triage_engine: TriageEngine) -> None:
    github_id = issue_data["github_id"]
    if is_issue_seen(github_id):
        return

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


async def poll_cycle(poller: GitHubPoller, triage_engine: TriageEngine) -> None:
    issues = await poller.fetch_issues()
    new_count = 0
    for issue_data in issues:
        if not is_issue_seen(issue_data["github_id"]):
            new_count += 1
            await process_issue(issue_data, triage_engine)

    logger.info("Poll cycle complete: %d fetched, %d new", len(issues), new_count)


async def run() -> None:
    init_db()
    poller = GitHubPoller()
    triage_engine = TriageEngine()

    logger.info(
        "Daemon started — polling every %ds", settings.poll_interval_seconds
    )

    try:
        while True:
            try:
                await poll_cycle(poller, triage_engine)
            except Exception:
                logger.exception("Poll cycle failed")
            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        await poller.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
