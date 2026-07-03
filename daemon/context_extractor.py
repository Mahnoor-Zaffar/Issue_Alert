import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)

_git_available: bool | None = None


def _check_git_available() -> bool:
    global _git_available
    if _git_available is not None:
        return _git_available
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        _git_available = True
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("git CLI not found on PATH — context extraction disabled")
        _git_available = False
    return _git_available


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _read_file(path: Path, max_bytes: int) -> str | None:
    try:
        raw = path.read_bytes()
        if _is_binary(raw):
            return None
        return raw[:max_bytes].decode("utf-8", errors="replace")
    except OSError:
        return None


def extract_repo_context(repo_clone_url: str) -> list[dict[str, str]]:
    if not _check_git_available():
        return []

    tmpdir = tempfile.mkdtemp(prefix="gh_triage_")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", repo_clone_url, tmpdir],
            capture_output=True,
            timeout=settings.git_clone_timeout_seconds,
            check=True,
        )

        result = subprocess.run(
            ["git", "-C", tmpdir, "log", "-3", "--name-only", "--pretty=format:"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        seen: set[str] = set()
        files: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                files.append(line)
            if len(files) >= 3:
                break

        context: list[dict[str, str]] = []
        for rel_path in files:
            full_path = Path(tmpdir) / rel_path
            if not full_path.is_file():
                continue
            content = _read_file(full_path, settings.max_file_bytes)
            if content is not None:
                context.append({"path": rel_path, "content": content})

        logger.info(
            "Extracted context from %s: %d files", repo_clone_url, len(context)
        )
        return context

    except subprocess.TimeoutExpired:
        logger.warning("Git clone timed out for %s", repo_clone_url)
        return []
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else exc.stderr
        logger.warning(
            "Git clone failed for %s: %s", repo_clone_url, stderr or exc
        )
        return []
    except OSError:
        logger.warning("Git operation failed for %s", repo_clone_url, exc_info=True)
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
