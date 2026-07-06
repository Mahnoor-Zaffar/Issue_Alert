# GitHub Issue Triage

A local-first system for discovering open-source contribution opportunities, enriching them with repository context, and producing kid-friendly AI triage reports — delivered through a real-time glass-morphism web dashboard and macOS desktop notifications.

[![Deploy GitHub Pages](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml/badge.svg)](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml)

**Live UI preview:** [mahnoor-zaffar.github.io/Issue_Alert](https://mahnoor-zaffar.github.io/Issue_Alert/) *(static frontend only)*  
**Full experience:** run locally at `http://127.0.0.1:8000`

---

## Overview

GitHub Issue Triage runs as two cooperating processes on your machine:

| Process | Role |
|---------|------|
| **Daemon** | Polls GitHub, deduplicates issues, extracts repo context via Contents API, calls LLM for triage, persists results |
| **API + Dashboard** | Serves the modern glass-morphism UI, REST endpoints, and SSE live feed |

Both share a single SQLite database (WAL mode), so either process can restart independently without losing state.

```
┌─────────────────┐     poll / triage      ┌──────────────────┐
│  daemon/        │ ─────────────────────► │  data/triage.db  │
│  (background)   │                        │  (SQLite WAL)    │
└─────────────────┘                        └────────┬─────────┘
                                                      │ read
                                                      ▼
┌─────────────────┐     SSE + REST           ┌──────────────────┐
│  Browser        │ ◄─────────────────────── │  api/ + static/  │
│  Dashboard      │                          │  (FastAPI)       │
└─────────────────┘                          └──────────────────┘
```

### Pipeline (per issue)

1. **Discover** — GitHub Search API (`good first issue`, `help wanted`) + priority repos
2. **Extract** — GitHub Contents API fetches repo tree, reads 3 relevant source files (no git clone)
3. **Score** — multi-factor scoring: repo stars (capped), comments count, body length tiers
4. **Triage** — LLM generates kid-friendly report: emoji sections, bullet points, code snippets, difficulty badge (🟢/🟡/🔴), one-line fix
5. **Notify** — macOS desktop notification via `osascript` *(for priority repos only)*
6. **Display** — dashboard updates live over Server-Sent Events

---

## Features

- **Priority repos** — watch specific repos with desktop notifications; shown first in a dedicated feed section
- **Configurable search** — labels, languages, minimum repo stars, progressive polling
- **LLM-agnostic** — works with OpenAI, OpenRouter, or any OpenAI-compatible API
- **Kid-friendly triage** — each issue analyzed as a friendly coding tutor with real-life analogies
- **Glass-morphism UI** — slide-out triage panel, dark theme, difficulty badges, bookmark/save
- **Bookmark, dismiss, and export** triage reports as Markdown
- **Manual Poll Now** trigger from the dashboard
- **Rate-limit-aware** GitHub client with exponential backoff
- **Graceful degradation** when LLM calls or Content API requests fail
- **Optional GitHub webhook ingestion**

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Persistence | SQLite (WAL) |
| GitHub | Search API, Contents API |
| AI | OpenRouter / OpenAI (`openai/gpt-4o-mini` by default) |
| Frontend | Vanilla HTML, CSS, JavaScript, [anime.js](https://animejs.com/) |
| Real-time | Server-Sent Events (SSE) |
| Notifications | macOS `osascript` |
| CI / Pages | GitHub Actions |

---

## Prerequisites

- **Python 3.11+** with `venv` support
- **GitHub Personal Access Token** with `public_repo` (or equivalent read access to public repos)
- **LLM API key** — [OpenRouter](https://openrouter.ai/) recommended, or any OpenAI-compatible provider

---

## Quick Start

```bash
git clone https://github.com/Mahnoor-Zaffar/Issue_Alert.git
cd Issue_Alert

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env               # add GITHUB_TOKEN and LLM_API_KEY
```

### Run locally

**Option A — helper script**

```bash
chmod +x run.sh
./run.sh
```

**Option B — two terminals** *(recommended for development)*

```bash
# Terminal 1 — daemon
source .venv/bin/activate
python -m daemon.main

# Terminal 2 — dashboard
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**

> **macOS note:** use `python3` or activate `.venv` before running `python`.  
> A bare `python` command often fails with `command not found`.

---

## Configuration

Copy `.env.example` to `.env` and fill in required values:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for Search + Contents API |
| `LLM_API_KEY` | Yes | — | LLM API key (OpenRouter or OpenAI) |
| `LLM_MODEL` | No | `openai/gpt-4o-mini` | Model used for triage |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` | LLM API base URL |
| `POLL_INTERVAL_SECONDS` | No | `60` | Seconds between poll cycles |
| `SEARCH_LOOKBACK_MINUTES` | No | `60` | How far back to search each poll (progressive) |
| `ISSUE_DISCOVERY_WINDOW_MINUTES` | No | `10080` | Initial full scan window (7 days) |
| `MAX_ISSUE_COMMENTS` | No | `2` | Max comments allowed (`0` = untouched only) |
| `MIN_REPO_STARS` | No | `0` | Minimum stars in search query |
| `DATABASE_PATH` | No | `./data/triage.db` | SQLite file location |
| `API_HOST` / `API_PORT` | No | `127.0.0.1` / `8000` | Dashboard bind address |

Search preferences (labels, languages, min stars) can also be changed from the dashboard **Preferences** panel without editing code.

---

## Project Structure

```
Issue_Alert/
├── daemon/           # Background poller, Contents API extraction, AI triage
├── api/              # FastAPI app, REST + SSE routes
├── db/               # Schema, migrations, SQLite store
├── static/           # Glass-morphism dashboard (served locally by FastAPI)
├── docs/             # GitHub Pages build output (generated)
├── scripts/
│   ├── build_pages.sh
│   └── reset_db.py
├── config/settings.py
├── run.sh
├── docker-compose.yml
└── requirements.txt
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/issues` | GET | List issues (`language`, `status`, `label`, `bookmarked_only`, `is_priority`) |
| `/api/issues/priority` | GET | Only priority-tagged issues |
| `/api/issues/{id}` | GET | Single issue with triage report |
| `/api/issues/{id}/bookmark` | POST | Toggle bookmark |
| `/api/issues/{id}/dismiss` | POST | Dismiss / restore issue |
| `/api/priority-repos` | GET / POST | List / add watched repos |
| `/api/priority-repos/{id}` | DELETE | Remove a watched repo |
| `/api/trigger-poll` | POST | Request immediate daemon poll |
| `/api/preferences` | GET / PUT | Search preferences |
| `/api/health` | GET | Service health and poll statistics |
| `/api/events` | GET | SSE stream for live updates |
| `/api/webhooks/github` | POST | Optional webhook receiver |

---

## Priority Repos

Add repos to the **Priority Repos** panel in the sidebar to:
- Watch specific repos that matter most to you
- Get **macOS desktop notifications** when new issues are found
- See them displayed in a separate **🔔 Priority Issues** section at the top of the feed
- Issues from priority repos are tagged and filterable

---

## Triage Reports

Each triaged issue includes a kid-friendly analysis with:

- **🧩 What This Part of the Code Does** — architecture context with real-life analogies
- **🐛 What's Wrong** — the bug or feature explained in plain language
- **📁 Files You'll Need to Edit** — exact files with line references
- **📝 Step-by-Step Plan** — code snippets with ❌ wrong / ✅ correct examples
- **💡 One-Line Fix** — a concise TL;DR of the fix
- **Difficulty badge** — 🟢 Easy / 🟡 Medium / 🔴 Hard

---

## GitHub Pages

The dashboard UI is published on push to `main` via GitHub Actions.

**One-time setup**

1. Go to **Settings → Pages → Build and deployment**
2. Set **Source** to **GitHub Actions** *(not "Deploy from a branch")*

The workflow builds `docs/` from `static/` and deploys with `.nojekyll`.  
GitHub Pages serves the **frontend only** — the daemon and API must run locally for live data.

---

## Operations

### Reset local data

```bash
source .venv/bin/activate
python scripts/reset_db.py
```

Then restart the daemon or click **Poll Now** on the dashboard.

### Rebuild Pages artifact locally

```bash
./scripts/build_pages.sh
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `command not found: python` | venv not activated | `source .venv/bin/activate` or use `.venv/bin/python` |
| `No module named 'sse_starlette'` | Global Python used instead of venv | Activate `.venv` before running uvicorn |
| `address already in use :8000` | Old server still running | `pkill -f "uvicorn api.main"` then restart |
| `0 fetched, 0 new` in logs | Overly restrictive search query | Lower min stars in Preferences; defaults use `help wanted` + `good first issue` |
| Triage status `error` | Invalid or expired LLM API key | Verify `LLM_API_KEY` in `.env` |
| No desktop notifications | Not on macOS or `osascript` unavailable | Non-fatal; issues still process normally |
| Pages deploy fails | Competing deploys or branch source still enabled | In **Settings → Pages**, set Source to **GitHub Actions** only (disable branch deploy). Re-run the workflow if needed. |

---

## Development

```bash
source .venv/bin/activate
pip install -r requirements.txt

# Run with shorter poll interval while testing
POLL_INTERVAL_SECONDS=60 python -m daemon.main
```

---

## License

This project is open source. See the repository for license details.

---

## Author

**Mahnoor Zaffar** — [GitHub](https://github.com/Mahnoor-Zaffar)
