import logging
from typing import Any

import httpx

from config.settings import settings
from daemon.rate_limiter import GitHubRateLimiter
from db.store import get_preferences

logger = logging.getLogger(__name__)


def build_search_query(prefs: dict[str, Any] | None = None) -> str:
    prefs = prefs or get_preferences()
    labels = prefs.get("labels") or []
    languages = prefs.get("languages") or []
    min_stars = prefs.get("min_stars", settings.min_repo_stars)

    label_clause = " OR ".join(f'label:"{label}"' for label in labels)
    lang_clause = " OR ".join(f"language:{lang}" for lang in languages)

    parts = ["is:issue", "is:open"]
    if label_clause:
        parts.append(f"({label_clause})")
    if lang_clause:
        parts.append(f"({lang_clause})")
    if min_stars > 0:
        parts.append(f"stars:>{min_stars}")

    return " ".join(parts)


class GitHubPoller:
    def __init__(self) -> None:
        self._rate_limiter = GitHubRateLimiter()
        self._repo_cache: dict[str, dict[str, Any]] = {}
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

    async def fetch_issues(self) -> tuple[list[dict[str, Any]], int]:
        prefs = get_preferences()
        query = build_search_query(prefs)
        all_items: list[dict[str, Any]] = []
        total_count = 0

        for page in range(1, settings.search_max_pages + 1):
            items, page_total = await self._fetch_page(query, page)
            if page == 1:
                total_count = page_total
            if not items:
                break
            all_items.extend(items)
            if len(items) < settings.search_per_page:
                break

        logger.info(
            "GitHub search: total_count=%d, items=%d, query=%s",
            total_count,
            len(all_items),
            query,
        )

        normalized = []
        for item in all_items:
            issue = await self._normalize_issue(item)
            normalized.append(issue)

        return normalized, total_count

    async def _fetch_page(
        self, query: str, page: int
    ) -> tuple[list[dict[str, Any]], int]:
        await self._rate_limiter.wait_if_needed()

        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": settings.search_per_page,
            "page": page,
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
                    logger.warning("GitHub search returned incomplete results (page %d)", page)

                return data.get("items", []), data.get("total_count", 0)

            except httpx.HTTPStatusError:
                logger.exception("GitHub API HTTP error on page %d", page)
                raise
            except httpx.RequestError:
                logger.exception("GitHub API request failed on page %d", page)
                raise

        logger.error("GitHub search page %d failed after retries", page)
        return [], 0

    async def _fetch_repo_info(self, repo_full_name: str) -> dict[str, Any]:
        if repo_full_name in self._repo_cache:
            return self._repo_cache[repo_full_name]

        try:
            response = await self._client.get(f"/repos/{repo_full_name}")
            self._rate_limiter.update_from_headers(response.headers)
            if response.status_code == 200:
                data = response.json()
                info = {
                    "language": (data.get("language") or "").lower() or None,
                    "stars": data.get("stargazers_count", 0),
                }
            else:
                info = {"language": None, "stars": 0}
        except (httpx.HTTPError, KeyError):
            logger.warning("Failed to fetch repo info for %s", repo_full_name)
            info = {"language": None, "stars": 0}

        self._repo_cache[repo_full_name] = info
        return info

    async def _normalize_issue(self, item: dict[str, Any]) -> dict[str, Any]:
        repo_url = item["repository_url"]
        repo_full_name = (
            repo_url.rsplit("/", 2)[-2] + "/" + repo_url.rsplit("/", 1)[-1]
        )

        repo_info = await self._fetch_repo_info(repo_full_name)
        labels = [label["name"] for label in item.get("labels", [])]

        language = repo_info.get("language")
        if not language:
            language = self._detect_language_from_text(labels, item.get("title", ""))

        return {
            "github_id": item["id"],
            "title": item["title"],
            "body": item.get("body") or "",
            "html_url": item["html_url"],
            "repo_full_name": repo_full_name,
            "repo_clone_url": f"https://github.com/{repo_full_name}.git",
            "labels": labels,
            "language": language,
            "repo_stars": repo_info.get("stars", 0),
            "state": item.get("state", "open"),
        }

    def _detect_language_from_text(
        self, labels: list[str], title: str
    ) -> str | None:
        combined = " ".join(labels + [title]).lower()
        for lang in ("rust", "go", "python", "javascript"):
            if lang in combined:
                return lang
        return None

    def issue_from_webhook(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        issue = payload.get("issue")
        if not issue:
            return None

        repo = payload.get("repository", {})
        repo_full_name = repo.get("full_name")
        if not repo_full_name:
            return None

        labels = [label["name"] for label in issue.get("labels", [])]
        return {
            "github_id": issue["id"],
            "title": issue["title"],
            "body": issue.get("body") or "",
            "html_url": issue["html_url"],
            "repo_full_name": repo_full_name,
            "repo_clone_url": repo.get("clone_url")
            or f"https://github.com/{repo_full_name}.git",
            "labels": labels,
            "language": (repo.get("language") or "").lower() or None,
            "repo_stars": repo.get("stargazers_count", 0),
            "state": issue.get("state", "open"),
        }
