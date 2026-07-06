import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config.settings import settings
from daemon.rate_limiter import GitHubRateLimiter
from db.store import get_last_poll_time, get_preferences, get_priority_repos

logger = logging.getLogger(__name__)

_LINKED_PR_BODY_RE = re.compile(
    r"github\.com/[\w.-]+/[\w.-]+/pull/\d+",
    re.IGNORECASE,
)


def freshness_cutoff_utc(
    window_minutes: int | None = None,
) -> datetime:
    """UTC timestamp for the start of the discovery window."""
    minutes = window_minutes or settings.issue_discovery_window_minutes
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def format_created_filter(cutoff: datetime) -> str:
    """GitHub Search API ``created:>=`` qualifier in UTC ISO-8601 form."""
    return f"created:>={cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def progressive_cutoff_utc() -> datetime:
    last_poll = get_last_poll_time()
    if last_poll is None:
        return freshness_cutoff_utc()
    lookback = timedelta(minutes=settings.search_lookback_minutes)
    return max(freshness_cutoff_utc(), last_poll - lookback)


def build_search_query(
    prefs: dict[str, Any] | None = None,
    cutoff: datetime | None = None,
) -> str:
    """Build GitHub issue search query for pristine, unclaimed recent issues.

    Note: ``label:`` and ``language:`` qualifiers return zero results when
    OR-combined in issue search, so both are filtered post-fetch using repo
    metadata instead of in the query.
    """
    prefs = prefs or get_preferences()
    min_stars = prefs.get("min_stars", settings.min_repo_stars)
    cutoff = cutoff or freshness_cutoff_utc()

    parts = [
        "is:issue",
        "is:open",
        format_created_filter(cutoff),
    ]
    if settings.max_issue_comments == 0:
        parts.append("comments:0")
    if min_stars > 0:
        parts.append(f"stars:>{min_stars}")

    return " ".join(parts)


def build_priority_query(full_name: str, cutoff: datetime | None = None) -> str:
    cutoff = cutoff or freshness_cutoff_utc()
    parts = [
        "is:issue",
        "is:open",
        format_created_filter(cutoff),
        f"repo:{full_name}",
    ]
    if settings.max_issue_comments == 0:
        parts.append("comments:0")
    return " ".join(parts)


def passes_claim_verification(
    item: dict[str, Any],
    cutoff: datetime | None = None,
) -> bool:
    """Secondary check: issue is open, unassigned, uncommented, and unclaimed."""
    cutoff = cutoff or freshness_cutoff_utc()

    if item.get("state") != "open":
        return False

    if "pull_request" in item:
        return False

    if item.get("comments", 0) > settings.max_issue_comments:
        return False

    assignees = item.get("assignees") or []
    if assignees or item.get("assignee"):
        return False

    body = item.get("body") or ""
    if _LINKED_PR_BODY_RE.search(body):
        return False

    created_at = item.get("created_at")
    if created_at:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created < cutoff:
            return False

    return True


def matches_language_preference(
    issue: dict[str, Any], prefs: dict[str, Any] | None = None
) -> bool:
    prefs = prefs or get_preferences()
    preferred = {lang.lower() for lang in (prefs.get("languages") or [])}
    if not preferred:
        return True
    language = (issue.get("language") or "").lower()
    if not language:
        return True
    return language in preferred


def matches_label_preference(
    issue: dict[str, Any], prefs: dict[str, Any] | None = None
) -> bool:
    prefs = prefs or get_preferences()
    preferred = {label.lower() for label in (prefs.get("labels") or [])}
    if not preferred:
        return True
    issue_labels = {label.lower() for label in (issue.get("labels") or [])}
    return bool(preferred & issue_labels)


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

    async def fetch_issues(self) -> tuple[list[dict[str, Any]], int, str | None]:
        prefs = get_preferences()
        cutoff = progressive_cutoff_utc()
        query = build_search_query(prefs, cutoff)
        all_items, total_count, search_ok = await self._search_pages(query)

        if not search_ok:
            logger.warning("GitHub search unavailable this cycle — skipping fetch")
            return [], 0, "GitHub search rate limited — will retry next poll"

        logger.info(
            "GitHub search: total_count=%d, raw_items=%d, query=%s",
            total_count,
            len(all_items),
            query,
        )

        pristine_items = [
            item for item in all_items if passes_claim_verification(item, cutoff)
        ]
        rejected = len(all_items) - len(pristine_items)
        if rejected:
            logger.info(
                "Claim verification rejected %d issue(s) (assigned, commented, linked PR, or stale)",
                rejected,
            )

        normalized = []
        for item in pristine_items:
            issue = await self._normalize_issue(item)
            normalized.append(issue)

        return normalized, total_count, None

    async def fetch_priority_issues(self) -> list[dict[str, Any]]:
        cutoff = freshness_cutoff_utc()
        repos = get_priority_repos()
        all_issues: list[dict[str, Any]] = []
        for r in repos:
            query = build_priority_query(r["full_name"], cutoff)
            items, _, ok = await self._search_pages(query, max_pages=1)
            if not ok:
                continue
            for item in items:
                if passes_claim_verification(item, cutoff):
                    issue = await self._normalize_issue(item)
                    issue["is_priority"] = True
                    all_issues.append(issue)
        if all_issues:
            logger.info("Found %d priority issue(s)", len(all_issues))
        return all_issues

    async def _search_pages(
        self, query: str, max_pages: int | None = None
    ) -> tuple[list[dict[str, Any]], int, bool]:
        pages = max_pages or settings.search_max_pages
        all_items: list[dict[str, Any]] = []
        total_count = 0
        any_success = False

        for page in range(1, pages + 1):
            items, page_total, page_ok = await self._fetch_page(query, page)
            if page_ok:
                any_success = True
            if page == 1:
                total_count = page_total
            if not items:
                break
            all_items.extend(items)
            if len(items) < settings.search_per_page:
                break

        return all_items, total_count, any_success

    async def _fetch_page(
        self, query: str, page: int
    ) -> tuple[list[dict[str, Any]], int, bool]:
        await self._rate_limiter.wait_if_needed()

        params = {
            "q": query,
            "sort": "interactions",
            "order": "desc",
            "per_page": settings.search_per_page,
            "page": page,
        }

        for attempt in range(4):
            try:
                response = await self._client.get("/search/issues", params=params)
                self._rate_limiter.update_from_headers(response.headers)

                if response.status_code in (403, 429):
                    await self._rate_limiter.backoff(attempt, response.headers)
                    continue

                response.raise_for_status()
                data = response.json()
                self._rate_limiter.mark_search_complete()

                if data.get("incomplete_results"):
                    logger.warning("GitHub search returned incomplete results (page %d)", page)

                return data.get("items", []), data.get("total_count", 0), True

            except httpx.HTTPStatusError:
                logger.exception("GitHub API HTTP error on page %d", page)
                return [], 0, False
            except httpx.RequestError:
                logger.exception("GitHub API request failed on page %d", page)
                return [], 0, False

        logger.error("GitHub search page %d failed after retries", page)
        return [], 0, False

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
            "created_at": item.get("created_at"),
            "comments": item.get("comments", 0),
            "assignees": item.get("assignees") or [],
            "assignee": item.get("assignee"),
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

        if not passes_claim_verification(issue):
            logger.debug(
                "Webhook issue %s rejected by claim verification",
                issue.get("id"),
            )
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
            "created_at": issue.get("created_at"),
            "comments": issue.get("comments", 0),
            "assignees": issue.get("assignees") or [],
            "assignee": issue.get("assignee"),
        }
