import daemon.main as main
import daemon.notifier as notifier


def test_notifications_are_capped_and_remaining_issues_digested(monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(main.settings, "max_notifications_per_cycle", 2)
    monkeypatch.setattr(
        main,
        "notify_new_issue",
        lambda title, repo, url, priority=False: calls.append(("single", title)),
    )
    monkeypatch.setattr(
        main,
        "notify_issue_digest",
        lambda issues, priority=False: calls.append(("digest", len(issues))),
    )

    issues = [
        {"title": f"issue {i}", "repo_full_name": "owner/repo", "html_url": f"https://example.com/{i}"}
        for i in range(5)
    ]
    main._dispatch_issue_notifications(issues)

    assert calls == [("single", "issue 0"), ("single", "issue 1"), ("digest", 3)]


def test_notification_text_is_escaped_for_applescript(monkeypatch):
    captured: dict[str, str] = {}

    def fake_run(args, **kwargs):
        captured["script"] = args[2]

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)

    notifier.notify_new_issue('Fix "quoted" title\nwith newline', "owner/repo", "https://example.com")

    script = captured["script"]
    assert '\\"quoted\\"' in script
    assert "\n" not in script
