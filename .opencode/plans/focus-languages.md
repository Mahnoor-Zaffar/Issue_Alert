# Focus on JS/TS/Python beginner-friendly issues

## Changes

### 1. `daemon/poller.py:42-66` — `build_search_query()`

Add `language:` qualifiers to the GitHub search query so searches only return
issues from repos whose primary language matches user preferences:

```python
# After the stars:>N qualifier, add:
langs = prefs.get("languages") or []
for lang in langs:
    parts.append(f"language:{lang.lower()}")
```

This changes queries from:
```
is:issue is:open created:>=... stars:>1000
```
to:
```
is:issue is:open created:>=... stars:>1000 language:javascript language:typescript language:python
```

### 2. `config/settings.py:20`

Change `max_issue_comments: int = 5` → `max_issue_comments: int = 2`

Fewer comments means the issue is less likely to already be claimed/discussed.

### 3. `db/store.py:636-642` — `_default_preferences()`

Update defaults:
- **languages**: `["javascript", "typescript", "python"]` (adds typescript)
- **labels**: `["good first issue", "help wanted", "beginner friendly", "easy", "up-for-grabs"]` (focused on beginner-friendly)
- **min_stars**: keep at 500 (settings.py has 1000)

## Files changed
- `daemon/poller.py` — 3 lines added (the language qualifier loop)
- `config/settings.py` — 1 value changed
- `db/store.py` — 2 lines changed (languages + labels defaults)
