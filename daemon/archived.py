import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_archived_from_payload(payload: dict[str, Any]) -> bool:
    """Best-effort archived flag from a GitHub API payload.

    PR objects carry the base repo object; repo-scoped payloads (webhooks,
    repo info) carry a ``repository`` object. Returns True only when GitHub
    explicitly reports the repo as archived.
    """
    candidates = [
        (payload.get("base") or {}).get("repo"),
        payload.get("repository"),
        payload.get("repo"),
    ]
    for repo in candidates:
        if isinstance(repo, dict) and repo.get("archived"):
            return True
    return False
