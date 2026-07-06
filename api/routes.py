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
    add_priority_repo,
    clear_all_data,
    enqueue_triage,
    enqueue_webhook,
    get_issue,
    get_issues_updated_since,
    get_preferences,
    get_priority_repos,
    get_stats,
    get_stats_history,
    list_issues,
    mark_issue_viewed,
    remove_priority_repo,
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


class RepoBody(BaseModel):
    full_name: str


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
    is_priority: bool | None = None,
    difficulty: str | None = None,
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
            is_priority=is_priority,
            difficulty=difficulty,
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
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    set_issue_flag(issue_id, "bookmarked", body.value)
    if body.value and issue.get("status") != "complete":
        enqueue_triage(issue_id)
        request_poll()
    return get_issue(issue_id)


@router.post("/api/issues/{issue_id}/view")
async def api_mark_issue_viewed(issue_id: int):
    if not mark_issue_viewed(issue_id):
        raise HTTPException(status_code=404, detail="Issue not found")
    return {"id": issue_id, "removed": True}


@router.post("/api/issues/{issue_id}/dismiss")
async def api_dismiss_issue(issue_id: int, body: FlagBody):
    if not get_issue(issue_id):
        raise HTTPException(status_code=404, detail="Issue not found")
    if body.value:
        mark_issue_viewed(issue_id)
        return {"id": issue_id, "removed": True}
    set_issue_flag(issue_id, "dismissed", False)
    return get_issue(issue_id)


@router.get("/api/health")
async def api_health():
    stats = get_stats()
    return {"status": "ok", **stats}


@router.get("/api/stats/history")
async def api_stats_history(days: int = 14):
    return {"history": get_stats_history(days)}


class OpenPRBody(BaseModel):
    issue_id: int


@router.post("/api/issues/{issue_id}/open-pr")
async def api_open_pr(issue_id: int):
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not issue.get("triage"):
        raise HTTPException(status_code=400, detail="Issue not triaged yet")
    if issue.get("difficulty") not in ("easy",):
        raise HTTPException(status_code=400, detail="Only Easy issues can auto-open PRs")

    try:
        url = await asyncio.to_thread(_do_open_pr, issue)
        return {"pr_url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to open PR for issue #%d", issue_id)
        raise HTTPException(status_code=500, detail=str(e))


import base64
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

def _do_open_pr(issue: dict[str, Any]) -> str:
    action_plan = issue["triage"]["action_plan"]
    repo = issue["repo_full_name"]
    title = issue["title"]
    html_url = issue["html_url"]
    token = settings.github_token

    file_match = re.search(r"`([^`]+)`", action_plan)
    if not file_match:
        raise ValueError("Could not determine which file to edit from the triage report")
    file_path = file_match.group(1)

    code_match = re.search(r"```\w*\n(.*?✅.*?)\n```", action_plan, re.DOTALL)
    if not code_match:
        code_match = re.search(r"✅.*?\n(.*?)(?:\n```|$)", action_plan, re.DOTALL)
    if not code_match:
        raise ValueError("Could not extract fix code from the triage report")
    new_code = code_match.group(1).strip()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    client = httpx.Client(headers=headers, timeout=30.0)

    owner, repo_name = repo.split("/")
    fork_resp = client.post(f"https://api.github.com/repos/{repo}/forks")
    if fork_resp.status_code not in (202, 200):
        raise ValueError(f"Failed to fork repo: HTTP {fork_resp.status_code}")
    fork_data = fork_resp.json()
    fork_full = fork_data["full_name"]
    fork_owner = fork_full.split("/")[0]

    resp = client.get(f"https://api.github.com/repos/{fork_full}/git/ref/heads/{fork_data.get('default_branch', 'main')}")
    if resp.status_code != 200:
        resp = client.get(f"https://api.github.com/repos/{fork_full}/git/refs/heads/main")
    if resp.status_code != 200:
        raise ValueError("Could not get default branch SHA from fork")
    base_sha = resp.json()["object"]["sha"]

    branch = f"fix-issue-{issue['id']}-{int(datetime.now(timezone.utc).timestamp())}"
    client.post(f"https://api.github.com/repos/{fork_full}/git/refs", json={
        "ref": f"refs/heads/{branch}",
        "sha": base_sha,
    })

    content_resp = client.get(
        f"https://api.github.com/repos/{fork_full}/contents/{file_path}",
        params={"ref": branch},
    )
    if content_resp.status_code != 200:
        raise ValueError(f"File {file_path} not found in fork (HTTP {content_resp.status_code})")
    content_data = content_resp.json()
    current_content = base64.b64decode(content_data["content"]).decode("utf-8", errors="replace")
    sha = content_data["sha"]

    new_content = current_content + "\n\n" + new_code

    client.put(f"https://api.github.com/repos/{fork_full}/contents/{file_path}", json={
        "message": f"fix: {title[:60]}",
        "content": base64.b64encode(new_content.encode()).decode(),
        "sha": sha,
        "branch": branch,
    })

    pr_resp = client.post(f"https://api.github.com/repos/{repo}/pulls", json={
        "title": f"[Auto-fix] {title[:80]}",
        "body": f"🤖 Auto-generated fix from triage report\n\nIssue: {html_url}\n\nThis PR was automatically generated by the Issue Triage system.",
        "head": f"{fork_owner}:{branch}",
        "base": fork_data.get("default_branch", "main"),
        "draft": True,
    })
    if pr_resp.status_code not in (201, 200):
        raise ValueError(f"Failed to create PR: HTTP {pr_resp.status_code}")

    pr_url = pr_resp.json().get("html_url", "")
    logger.info("Opened draft PR: %s", pr_url)
    return pr_url


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


@router.get("/api/issues/priority")
async def api_priority_issues():
    return {"issues": list_issues(is_priority=True)}


@router.get("/api/priority-repos")
async def api_get_priority_repos():
    return {"repos": get_priority_repos()}


@router.post("/api/priority-repos")
async def api_add_priority_repo(body: RepoBody):
    result = add_priority_repo(body.full_name)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid or duplicate repo (format: owner/repo)")
    request_poll()
    return result


@router.delete("/api/priority-repos/{repo_id}")
async def api_remove_priority_repo(repo_id: int):
    if not remove_priority_repo(repo_id):
        raise HTTPException(status_code=404, detail="Repo not found")
    return {"removed": True}


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
