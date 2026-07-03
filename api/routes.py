import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from db.store import get_issue, get_issues_updated_since, get_stats, list_issues

logger = logging.getLogger(__name__)
router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/issues")
async def api_list_issues(limit: int = 50, offset: int = 0):
    return {"issues": list_issues(limit=limit, offset=offset)}


@router.get("/api/issues/{issue_id}")
async def api_get_issue(issue_id: int):
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.get("/api/health")
async def api_health():
    stats = get_stats()
    return {
        "status": "ok",
        "issue_count": stats["total"],
        "pending": stats["pending"],
        "complete": stats["complete"],
        "last_updated": stats["last_updated"],
    }


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
            except Exception:
                logger.exception("SSE poll error")

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())
