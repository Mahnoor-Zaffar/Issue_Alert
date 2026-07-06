import base64
import logging
import re
from pathlib import Path

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt",
    ".scala", ".m", ".mm", ".cs", ".fs", ".ex", ".exs", ".sh",
    ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini", ".conf",
    ".css", ".scss", ".less", ".html", ".xml",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", ".env",
    "dist", "build", ".next", "target", "vendor", ".vscode", ".idea",
    "coverage", ".github", "third_party", "third-party",
}

MAX_TREE_ENTRIES = 1000


def _parse_repo_url(clone_url: str) -> tuple[str, str] | None:
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", clone_url)
    if match:
        return match.group(1), re.sub(r"\.git$", "", match.group(2))
    return None


def _should_skip_path(path: str) -> bool:
    parts = path.split("/")
    return any(skip in parts for skip in SKIP_DIRS)


def extract_repo_context(repo_clone_url: str) -> list[dict[str, str]]:
    parsed = _parse_repo_url(repo_clone_url)
    if not parsed:
        logger.warning("Could not parse repo URL: %s", repo_clone_url)
        return []

    owner, repo = parsed
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(headers=headers, timeout=30.0) as client:
        repo_resp = client.get(f"https://api.github.com/repos/{owner}/{repo}")
        if repo_resp.status_code != 200:
            logger.warning("Failed to fetch repo info for %s/%s: HTTP %d", owner, repo, repo_resp.status_code)
            return []
        repo_data = repo_resp.json()
        default_branch = repo_data.get("default_branch", "main")

        tree_resp = client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
        )
        if tree_resp.status_code != 200:
            return []

        tree = tree_resp.json().get("tree", [])

        candidates = []
        for entry in tree[:MAX_TREE_ENTRIES]:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path", "")
            ext = Path(path).suffix.lower()
            if ext not in SOURCE_EXTENSIONS or _should_skip_path(path):
                continue
            candidates.append(path)

        candidates.sort(key=lambda p: (p.count("/"), len(p)))
        selected = candidates[:3]

        context = []
        for path in selected:
            content_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                params={"ref": default_branch},
            )
            if content_resp.status_code != 200:
                continue
            content_data = content_resp.json()
            if content_data.get("encoding") != "base64":
                continue
            raw = base64.b64decode(content_data.get("content", ""))
            decoded = raw[: settings.max_file_bytes].decode("utf-8", errors="replace")
            context.append({"path": path, "content": decoded})

        logger.info("Extracted context from %s: %d files", repo_clone_url, len(context))
        return context
