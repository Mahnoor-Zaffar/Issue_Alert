import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def notify_new_issue(title: str, repo: str, url: str, priority: bool = False) -> None:
    prefix = "🔔 " if priority else ""
    try:
        script = (
            f'display notification "{shlex.quote(title)}"'
            f' with title "{shlex.quote(prefix + repo)}"'
            f' subtitle "{shlex.quote(url)}"'
        )
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        logger.info("Notification sent for %s%s", "priority " if priority else "", repo)
    except Exception:
        logger.warning("Failed to send notification", exc_info=True)
