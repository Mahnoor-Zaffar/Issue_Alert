import logging
from typing import Any

import httpx

from config.settings import settings
from daemon.rate_limiter import GitHubRateLimiter
from db.store import (
    get_priority_repos,
    get_pull_by_repo_number,
    has_pull,
    upsert_pull,
)

logger = logging.getLogger(__name__)


class PRDiscovery:
    """Scans priority repos for open pull requests and upserts them."""

    _MAX_PRS_PER_REPO = 30

    def __init__(self) -> None:
        self._rate_limiter = GitHubRateLimiter()
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def scan_priority_repos(self) -> int:
        """Upsert open PRs from all priority repos. Returns number of scans performed."""
        repos = [r for r in get_priority_repos() if not r.get("is_org")]
        scanned = 0
        for repo in repos:
            full_name = repo["full_name"]
            prs = await self._fetch_pulls(full_name)
            if prs is None:
                continue
            scanned += 1
            for pr in prs:
                self._upsert_from_github(pr, is_priority=True, ingested_via="scan")
        if scanned:
            logger.info("Scanned %d priority repo(s) for open PRs", scanned)
        return scanned

    async def ingest_webhook(self, payload: dict[str, Any]) -> bool:
        """Ingest a pull_request webhook payload. Returns True if a PR was upserted."""
        pr = payload.get("pull_request")
        if not pr:
            return False
        repo = payload.get("repository") or {}
        full_name = repo.get("full_name")
        if not full_name:
            return False
        number = pr.get("number")
        if number is None:
            return False
        if not has_pull(full_name, number):
            logger.info("Ingesting new PR from webhook: %s#%d", full_name, number)
        self._upsert_from_github(
            pr,
            is_priority=True,
            ingested_via="webhook",
            fallback_repo=full_name,
        )
        return True

    def _upsert_from_github(
        self,
        pr: dict[str, Any],
        *,
        is_priority: bool,
        ingested_via: str,
        fallback_repo: str | None = None,
    ) -> int:
        number = pr.get("number") or 0
        repo_url = pr.get("html_url") or ""
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        repo_name = fallback_repo
        if not repo_name:
            base_repo = base.get("repo") or {}
            repo_name = base_repo.get("full_name")
        if not repo_name:
            repo_name = _repo_from_url(repo_url) or "unknown/unknown"

        labels = [(label.get("name") or "") for label in (pr.get("labels") or []) if label.get("name")]

        return upsert_pull(
            repo_full_name=repo_name,
            number=number,
            title=(pr.get("title") or "").strip() or f"PR #{number}",
            body=pr.get("body"),
            html_url=repo_url,
            head_sha=(head.get("sha") or None) if isinstance(head, dict) else None,
            base_sha=(base.get("sha") or None) if isinstance(base, dict) else None,
            base_ref=(base.get("ref") or None) if isinstance(base, dict) else None,
            author=_author_login(pr.get("user")),
            state=(pr.get("state") or "open"),
            labels=labels,
            head_label=(head.get("label") or None) if isinstance(head, dict) else None,
            is_priority=is_priority,
            ingested_via=ingested_via,
        )

    async def _fetch_pulls(self, full_name: str) -> list[dict[str, Any]] | None:
        await self._rate_limiter.wait_if_needed()
        try:
            response = await self._client.get(
                f"/repos/{full_name}/pulls",
                params={"state": "open", "sort": "updated", "direction": "desc", "per_page": self._MAX_PRS_PER_REPO},
            )
            self._rate_limiter.update_from_headers(response.headers)
            if response.status_code in (403, 429):
                await self._rate_limiter.backoff(0, response.headers)
                return None
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            logger.exception("Failed to fetch PRs for %s", full_name)
            return None


def _repo_from_url(html_url: str) -> str | None:
    """Extract owner/repo from a PR html_url like https://github.com/o/r/pull/1."""
    parts = (html_url or "").split("/")
    try:
        i = parts.index("github.com")
    except ValueError:
        return None
    if len(parts) >= i + 3:
        return f"{parts[i + 1]}/{parts[i + 2]}"
    return None


def _author_login(user: Any) -> str | None:
    if isinstance(user, dict):
        return user.get("login")
    return None


def pull_from_webhook_is_new(payload: dict[str, Any]) -> bool:
    """Heuristic used by the API to decide if a webhook PR is worth queueing for review."""
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    full_name = repo.get("full_name")
    number = pr.get("number")
    if not full_name or not number:
        return False
    return not has_pull(full_name, number) or (get_pull_by_repo_number(full_name, number) or {}).get("state") != "open"
