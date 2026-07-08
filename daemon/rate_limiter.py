import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from db.rate_limit_store import save_rate_limit

logger = logging.getLogger(__name__)

# GitHub Search API: 30 authenticated requests per minute.
_MIN_SEARCH_INTERVAL_SECONDS = 2.1


@dataclass
class RateLimitState:
    remaining: int | None = None
    reset_epoch: int | None = None


class GitHubRateLimiter:
    def __init__(self) -> None:
        self._state = RateLimitState()
        self._last_search_at: float | None = None

    def update_from_headers(self, headers: httpx.Headers) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self._state.remaining = int(remaining)
        if reset is not None:
            self._state.reset_epoch = int(reset)
        save_rate_limit(self._state.remaining, self._state.reset_epoch)

    async def wait_if_needed(self) -> None:
        now = time.time()
        if self._last_search_at is not None:
            elapsed = now - self._last_search_at
            if elapsed < _MIN_SEARCH_INTERVAL_SECONDS:
                await asyncio.sleep(_MIN_SEARCH_INTERVAL_SECONDS - elapsed)

        if self._state.remaining is not None and self._state.remaining <= 1:
            if self._state.reset_epoch:
                wait = self._state.reset_epoch - time.time() + 1
                if wait > 0:
                    logger.warning(
                        "GitHub rate limit nearly exhausted, sleeping %.1fs",
                        wait,
                    )
                    await asyncio.sleep(wait)

    async def backoff(self, attempt: int, headers: httpx.Headers | None = None) -> None:
        if headers is not None:
            self.update_from_headers(headers)
        if self._state.reset_epoch:
            wait = self._state.reset_epoch - time.time() + 1
            if wait > 0:
                logger.warning(
                    "GitHub rate limited, waiting %.1fs for reset (attempt %d)",
                    wait,
                    attempt,
                )
                await asyncio.sleep(wait)
                return

        delay = min(2**attempt, 60)
        logger.warning("Rate limited, backing off %ds (attempt %d)", delay, attempt)
        await asyncio.sleep(delay)

    def mark_search_complete(self) -> None:
        self._last_search_at = time.time()
