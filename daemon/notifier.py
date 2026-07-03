import logging

from plyer import notification

logger = logging.getLogger(__name__)


def notify_new_issue(title: str, repo: str, url: str) -> None:
    try:
        notification.notify(
            title=f"New Issue: {repo}",
            message=f"{title}\n{url}",
            app_name="GitHub Triage",
            timeout=10,
        )
        logger.info("Desktop notification sent for %s", title)
    except Exception:
        logger.warning("Failed to send desktop notification", exc_info=True)
