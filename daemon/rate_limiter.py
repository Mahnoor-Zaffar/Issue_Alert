import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    remaining: int | None = None
    reset_epoch: int | None = None


class GitHubRateLimiter:
    def __init__(self) -> None:
        self._state = RateLimitState()

    def update_from_headers(self, headers: httpx.Headers) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if remaining is not None:
            self._state.remaining = int(remaining)
        if reset is not None:
            self._state.reset_epoch = int(reset)

    async def wait_if_needed(self) -> None:
        if self._state.remaining is not None and self._state.remaining <= 1:
            if self._state.reset_epoch:
                wait = self._state.reset_epoch - time.time() + 1
                if wait > 0:
                    logger.warning(
                        "GitHub rate limit nearly exhausted, sleeping %.1fs",
                        wait,
                    )
                    await asyncio.sleep(wait)

    async def backoff(self, attempt: int) -> None:
        delay = min(2**attempt, 60)
        logger.warning("Rate limited, backing off %ds (attempt %d)", delay, attempt)
        await asyncio.sleep(delay)
