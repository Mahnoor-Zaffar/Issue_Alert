import pytest

from config.settings import settings
from db import store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "test.db")
    store.init_db()
    return tmp_path / "test.db"


def _issue(github_id: int, repo_full_name: str) -> dict:
    return {
        "github_id": github_id,
        "title": f"issue {github_id}",
        "html_url": f"https://github.com/{repo_full_name}/issues/{github_id}",
        "repo_full_name": repo_full_name,
        "repo_clone_url": f"https://github.com/{repo_full_name}.git",
    }


def test_ui_added_priority_targets_survive_daemon_resync(db):
    assert store.add_priority_repo("user-added/repo", is_user_added=True)
    assert store.add_priority_repo("UserOrg", is_user_added=True)

    store.replace_priority_repos(["curated/repo"], high_priority={"curated/repo"})

    rows = {r["full_name"]: r for r in store.get_priority_repos()}
    assert set(rows) == {"curated/repo", "user-added/repo", "UserOrg"}
    assert rows["user-added/repo"]["is_user_added"] == 1
    assert rows["UserOrg"]["is_user_added"] == 1
    assert rows["UserOrg"]["is_org"] == 1
    assert rows["curated/repo"]["is_user_added"] == 0


def test_ui_added_general_targets_survive_daemon_resync(db):
    assert store.add_general_repo("user-added/general", is_user_added=True)

    store.replace_general_repos(["curated/repo"])

    rows = {r["full_name"]: r for r in store.get_general_repos()}
    assert set(rows) == {"curated/repo", "user-added/general"}
    assert rows["user-added/general"]["is_user_added"] == 1
    assert rows["curated/repo"]["is_user_added"] == 0


def test_purge_keeps_issues_from_org_targets(db):
    store.replace_priority_repos(["OpenMS"])
    store.insert_issue(_issue(1, "OpenMS/OpenMS-benchmarking"))
    store.insert_issue(_issue(2, "untracked/repo"))

    assert store.purge_untracked_repo_issues() == 1
    with store.get_connection() as conn:
        remaining = {r["repo_full_name"] for r in conn.execute("SELECT repo_full_name FROM issues")}
    assert remaining == {"OpenMS/OpenMS-benchmarking"}
