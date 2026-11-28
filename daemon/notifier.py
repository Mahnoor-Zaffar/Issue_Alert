import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def _applescript_string(value: object) -> str:
    """Escape a value for use inside an AppleScript double-quoted string."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


def notify_new_issue(title: str, repo: str, url: str, priority: bool = False) -> None:
    prefix = "🔔 " if priority else ""
    try:
        script = (
            f'display notification "{_applescript_string(title)}"'
            f' with title "{_applescript_string(prefix + repo)}"'
            f' subtitle "{_applescript_string(url)}"'
        )
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        logger.info("Notification sent for %s%s", "priority " if priority else "", repo)
    except Exception:
        logger.warning("Failed to send notification", exc_info=True)


def notify_issue_digest(issues: list[dict[str, Any]], priority: bool = False) -> None:
    """Send one notification summarising issues that exceeded the per-cycle cap."""
    count = len(issues)
    if not count:
        return
    prefix = "🔔 " if priority else ""
    samples = "; ".join(f"{issue.get('repo_full_name')}: {str(issue.get('title', ''))[:45]}" for issue in issues[:3])
    message = f"{count} more new issue(s): {samples}"
    try:
        script = (
            f'display notification "{_applescript_string(message)}"'
            f' with title "{_applescript_string(prefix + str(count) + " more issues")}"'
            ' subtitle "Open Issue Alert to review"'
        )
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        logger.info("Digest notification sent for %d issue(s)", count)
    except Exception:
        logger.warning("Failed to send digest notification", exc_info=True)


def notify_pr_review(repo: str, number: int, url: str) -> None:
    try:
        script = (
            f'display notification "PR #{number} review ready — open the app to review it"'
            f' with title "📝 {_applescript_string(repo)}"'
            f' subtitle "{_applescript_string(url)}"'
        )
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        logger.info("PR review notification sent for %s#%d", repo, number)
    except Exception:
        logger.warning("Failed to send PR review notification", exc_info=True)
