import asyncio
import logging
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from config.settings import settings
from daemon.rate_limiter import GitHubRateLimiter

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = """\
You write constructive community PR review comments for open-source repositories. \
You review a pull request by reading its diff, its CI check status, and any codebase \
conventions you can observe. You never claim anything you did not verify.

Rules (non-negotiable):
1. You are a community reviewer, NOT a maintainer. Your output is a Comment, \
never a formal approval or a "request changes" verdict.
2. Be explicitly honest: if you did not run the test suite locally, you MUST \
state "Static review — tests not run locally (reviewed from diff + CI checks)." \
at the top. NEVER claim tests passed, failed, or were run unless you actually ran them.
3. State what you actually reviewed: exact files, and the CI check status you saw \
(e.g. "CI: build passing, 2/6 jobs pending," or "CI status unavailable").
4. Focus on correctness, edge cases, and test validity. Do not nitpick subjective styling \
already covered by linters.
5. Concrete actionable feedback only: reference file paths and line concepts, explain the \
impact, and give a specific suggestion. If the change is fine, say so plainly.
6. Note obvious gaps: missing tests for a behavior change, undocumented/ untyped new \
parameters, unexpected breaking API changes.
7. Keep it under ~220 words. End with a short positive line. Use plain Markdown with \
bullet points only (no headings heavier than "##").

Good tone example, exactly this kind of structure:
Static review — tests not run locally (reviewed from diff + CI checks).

Reviewed: `app/core.py` (lines ~50-70), `tests/test_core.py`. CI: all checks passing.

- The new `retry` parameter is typed and defaulted correctly...
- Possible edge case in `_maybe_backoff` when `attempt` is 0...
- Tests cover the happy path; consider adding a case for `ConnectionError`...

One suggestion: in `app/client.py`, typing `timeout: float | None = None` would match the \
existing convention at `app/core.py`.

Looks solid — happy to re-review once the edge-case test is added.
"""


class PRReviewer:
    """Produces constructive community PR reviews using the LLM."""

    def __init__(self) -> None:
        self._llm = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/Mahnoor-Zaffar/Issue_Alert",
                "X-Title": "GitHub PR Review",
            },
        )
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

    async def review_pull(self, pull: dict[str, Any]) -> str:
        """Fetch PR detail + diff + checks and ask the LLM for a review comment."""
        repo = pull["repo_full_name"]
        number = pull["number"]
        head_sha = pull.get("head_sha")

        diff = await self._fetch_pr_diff(repo, number)
        checks = await self._fetch_check_runs(repo, head_sha) if head_sha else []
        files = await self._fetch_pr_files(repo, number)

        user_message = self._build_user_message(pull, diff, files, checks)

        for attempt in range(3):
            try:
                response = await self._llm.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.2,
                    max_tokens=1200,
                )
                return response.choices[0].message.content or ""
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                delay = 2 ** (attempt + 1)
                logger.warning("PR review LLM error (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(delay)

        raise RuntimeError("PR review failed after 3 retries")

    def _build_user_message(
        self,
        pull: dict[str, Any],
        diff: str,
        files: list[dict[str, Any]],
        checks: list[dict[str, Any]],
    ) -> str:
        title = pull.get("title") or ""
        body = (pull.get("body") or "").strip() or "(no description provided)"
        labels = ", ".join(pull.get("labels") or []) or "(none)"

        lines = [
            f"# Pull Request #{pull['number']}: {title}",
            f"Repository: `{pull['repo_full_name']}`",
            f"Labels: {labels}",
            f"Head SHA: `{pull.get('head_sha')}`",
            "",
            "## Description",
            body,
            "",
            "## Files changed (GitHub API)",
        ]
        for f in files[:40]:
            lines.append(
                f"- {f.get('status', 'changed')} `{f.get('filename', '?')}` "
                f"(+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
            )

        lines.append("\n## Diff")
        diff_snippet = diff[:12000]
        lines.append(diff_snippet if diff_snippet.strip() else "_(diff unavailable)_")

        lines.append("\n## CI checks (GitHub API)")
        if checks:
            for c in checks[:25]:
                lines.append(f"- {c.get('name', 'check')}: {c.get('conclusion') or c.get('status') or 'unknown'}")
        else:
            lines.append("_(no check runs reported / unavailable)_")

        lines.append("\nWrite your community PR review comment now, following the rules in your instructions.")
        return "\n".join(lines)

    async def _fetch_pr_diff(self, repo: str, number: int) -> str:
        await self._rate_limiter.wait_if_needed()
        try:
            response = await self._client.get(
                f"/repos/{repo}/pulls/{number}",
                headers={"Accept": "application/vnd.github.v3.diff"},
            )
            self._rate_limiter.update_from_headers(response.headers)
            if response.status_code in (403, 429):
                await self._rate_limiter.backoff(0, response.headers)
            elif response.status_code == 200:
                return response.text
        except httpx.HTTPError:
            logger.exception("Failed to fetch diff for %s#%d", repo, number)
        return ""

    async def _fetch_pr_files(self, repo: str, number: int) -> list[dict[str, Any]]:
        await self._rate_limiter.wait_if_needed()
        try:
            response = await self._client.get(
                f"/repos/{repo}/pulls/{number}/files",
                params={"per_page": 50},
            )
            self._rate_limiter.update_from_headers(response.headers)
            if response.status_code in (403, 429):
                await self._rate_limiter.backoff(0, response.headers)
            elif response.status_code == 200:
                return response.json()
        except httpx.HTTPError:
            logger.exception("Failed to fetch files for %s#%d", repo, number)
        return []

    async def _fetch_check_runs(
        self,
        repo: str,
        head_sha: str,
    ) -> list[dict[str, Any]]:
        await self._rate_limiter.wait_if_needed()
        try:
            response = await self._client.get(
                f"/repos/{repo}/commits/{head_sha}/check-runs",
                params={"per_page": 50},
            )
            self._rate_limiter.update_from_headers(response.headers)
            if response.status_code in (403, 429):
                await self._rate_limiter.backoff(0, response.headers)
            elif response.status_code == 200:
                data = response.json()
                return data.get("check_runs", [])
        except httpx.HTTPError:
            logger.exception("Failed to fetch check runs for %s", head_sha)
        return []


async def post_review_comment(
    repo: str,
    number: int,
    review_markdown: str,
) -> int:
    """Post a pull request review as a COMMENT. Returns the GitHub review id."""
    body_text = review_markdown[:65536]
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    ) as client:
        response = await client.post(
            f"/repos/{repo}/pulls/{number}/reviews",
            json={"body": body_text, "event": "COMMENT"},
        )
        response.raise_for_status()
        data = response.json()
        return int(data["id"])
