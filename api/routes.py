import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config.settings import settings
from db.store import (
    clear_all_data,
    enqueue_webhook,
    get_issue,
    get_issues_updated_since,
    get_preferences,
    get_stats,
    list_issues,
    request_poll,
    save_preferences,
    set_issue_flag,
)

logger = logging.getLogger(__name__)
router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class PreferencesBody(BaseModel):
    languages: list[str] | None = None
    labels: list[str] | None = None
    min_stars: int | None = None
    show_dismissed: bool | None = None


class FlagBody(BaseModel):
    value: bool = True


@router.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/issues")
async def api_list_issues(
    limit: int = 50,
    offset: int = 0,
    language: str | None = None,
    status: str | None = None,
    label: str | None = None,
    show_dismissed: bool = False,
    bookmarked_only: bool = False,
):
    return {
        "issues": list_issues(
            limit=limit,
            offset=offset,
            language=language,
            status=status,
            label=label,
            show_dismissed=show_dismissed,
            bookmarked_only=bookmarked_only,
        )
    }


@router.get("/api/issues/{issue_id}")
async def api_get_issue(issue_id: int):
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post("/api/issues/{issue_id}/bookmark")
async def api_bookmark_issue(issue_id: int, body: FlagBody):
    if not get_issue(issue_id):
        raise HTTPException(status_code=404, detail="Issue not found")
    set_issue_flag(issue_id, "bookmarked", body.value)
    return get_issue(issue_id)


@router.post("/api/issues/{issue_id}/dismiss")
async def api_dismiss_issue(issue_id: int, body: FlagBody):
    if not get_issue(issue_id):
        raise HTTPException(status_code=404, detail="Issue not found")
    set_issue_flag(issue_id, "dismissed", body.value)
    return get_issue(issue_id)


@router.get("/api/health")
async def api_health():
    stats = get_stats()
    return {"status": "ok", **stats}


@router.get("/api/preferences")
async def api_get_preferences():
    return get_preferences()


@router.put("/api/preferences")
async def api_save_preferences(body: PreferencesBody):
    current = get_preferences()
    updated = {
        "languages": body.languages if body.languages is not None else current["languages"],
        "labels": body.labels if body.labels is not None else current["labels"],
        "min_stars": body.min_stars if body.min_stars is not None else current["min_stars"],
        "show_dismissed": (
            body.show_dismissed
            if body.show_dismissed is not None
            else current["show_dismissed"]
        ),
    }
    return save_preferences(updated)


@router.post("/api/trigger-poll")
async def api_trigger_poll():
    request_poll()
    return {"status": "poll_requested", "message": "Daemon will poll on next check (within ~1s)"}


@router.post("/api/admin/clear-data")
async def api_clear_data():
    clear_all_data()
    return {"status": "cleared"}


@router.post("/api/webhooks/github")
async def api_github_webhook(request: Request):
    body = await request.body()
    if settings.github_webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    action = payload.get("action", "")
    if payload.get("issue") and action in ("opened", "labeled", "reopened"):
        webhook_id = enqueue_webhook(payload)
        request_poll()
        return {"status": "queued", "webhook_id": webhook_id}

    return {"status": "ignored", "action": action}


@router.get("/api/events")
async def api_events(request: Request):
    async def event_generator():
        since = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        yield {
            "event": "connected",
            "data": json.dumps({"message": "SSE connected"}),
        }

        while True:
            if await request.is_disconnected():
                break

            try:
                updates = get_issues_updated_since(since)
                for issue in updates:
                    since = issue["updated_at"]
                    yield {
                        "event": "issue_update",
                        "data": json.dumps(issue, default=str),
                    }

                stats = get_stats()
                yield {
                    "event": "stats_update",
                    "data": json.dumps(stats, default=str),
                }
            except Exception:
                logger.exception("SSE poll error")

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())
