import logging
from typing import Any

import httpx

from config.settings import settings
from daemon.rate_limiter import GitHubRateLimiter

logger = logging.getLogger(__name__)

SEARCH_QUERY = (
    'is:issue is:open '
    '(label:"good first issue" OR label:"help wanted" OR label:"open-source") '
    "(language:javascript OR language:python OR language:go OR language:rust)"
)


class GitHubPoller:
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

    async def fetch_issues(self) -> list[dict[str, Any]]:
        await self._rate_limiter.wait_if_needed()

        params = {
            "q": SEARCH_QUERY,
            "sort": "updated",
            "order": "desc",
            "per_page": 30,
        }

        for attempt in range(4):
            try:
                response = await self._client.get("/search/issues", params=params)
                self._rate_limiter.update_from_headers(response.headers)

                if response.status_code in (403, 429):
                    await self._rate_limiter.backoff(attempt)
                    continue

                response.raise_for_status()
                data = response.json()

                if data.get("incomplete_results"):
                    logger.warning("GitHub search returned incomplete results")

                return [self._normalize_issue(item) for item in data.get("items", [])]

            except httpx.HTTPStatusError:
                logger.exception("GitHub API HTTP error")
                raise
            except httpx.RequestError:
                logger.exception("GitHub API request failed")
                raise

        logger.error("GitHub search failed after retries due to rate limiting")
        return []

    def _normalize_issue(self, item: dict[str, Any]) -> dict[str, Any]:
        repo_url = item["repository_url"]
        repo_full_name = repo_url.rsplit("/", 2)[-2] + "/" + repo_url.rsplit("/", 1)[-1]

        labels = [label["name"] for label in item.get("labels", [])]
        language = self._detect_language(labels, item.get("title", ""))

        return {
            "github_id": item["id"],
            "title": item["title"],
            "body": item.get("body") or "",
            "html_url": item["html_url"],
            "repo_full_name": repo_full_name,
            "repo_clone_url": f"https://github.com/{repo_full_name}.git",
            "labels": labels,
            "language": language,
            "state": item.get("state", "open"),
        }

    def _detect_language(self, labels: list[str], title: str) -> str | None:
        combined = " ".join(labels + [title]).lower()
        for lang in ("rust", "go", "python", "javascript"):
            if lang in combined:
                return lang
        return None
