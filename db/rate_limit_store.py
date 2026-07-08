import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

RATE_LIMIT_FILE = Path(__file__).resolve().parent.parent / "data" / "rate_limit.json"


def save_rate_limit(remaining: int | None, reset_epoch: int | None) -> None:
    try:
        RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RATE_LIMIT_FILE, "w") as f:
            json.dump({"remaining": remaining, "reset_epoch": reset_epoch}, f)
    except OSError:
        logger.exception("Failed to save rate limit info")


def read_rate_limit() -> dict:
    try:
        if RATE_LIMIT_FILE.exists():
            with open(RATE_LIMIT_FILE) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read rate limit info")
    return {"remaining": None, "reset_epoch": None}
