# GitHub Issue Triage

A local-first system for discovering open-source contribution opportunities, enriching them with repository context, and producing actionable AI triage reports — delivered through a real-time web dashboard and optional desktop notifications.

[![Deploy GitHub Pages](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml/badge.svg)](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml)

**Live UI preview:** [mahnoor-zaffar.github.io/Issue_Alert](https://mahnoor-zaffar.github.io/Issue_Alert/) *(static frontend only)*  
**Full experience:** run locally at `http://127.0.0.1:8000`

---

## Overview

GitHub Issue Triage runs as two cooperating processes on your machine:

| Process | Role |
|---------|------|
| **Daemon** | Polls GitHub, deduplicates issues, clones repos, calls OpenAI, persists results |
| **API + Dashboard** | Serves the UI, REST endpoints, and SSE live feed |

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

1. **Discover** — GitHub Search API (`good first issue`, `help wanted`)
2. **Notify** — native desktop alert via plyer *(when supported on your OS)*
3. **Extract** — shallow `git clone`, read 3 most recently modified files
4. **Triage** — OpenAI produces architecture context, issue breakdown, and PR action plan
5. **Display** — dashboard updates live over Server-Sent Events

---

## Features

- Configurable search: labels, languages, minimum repo stars
- Issue scoring and sorting by relevance
- Bookmark, dismiss, and export triage reports as Markdown
- Manual **Poll Now** trigger from the dashboard
- Rate-limit-aware GitHub client with exponential backoff
- Graceful degradation when git clone or LLM calls fail
- Optional GitHub webhook ingestion
- GitHub Pages deployment for static UI preview

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Persistence | SQLite (WAL) |
| GitHub | Search API, REST Repos API |
| AI | OpenAI (`gpt-4o-mini` by default) |
| Frontend | Vanilla HTML, CSS, JavaScript, [anime.js](https://animejs.com/) |
| Real-time | Server-Sent Events (SSE) |
| Notifications | plyer |
| CI / Pages | GitHub Actions |

---

## Prerequisites

- **Python 3.11+** with `venv` support
- **git** on your `PATH`
- **GitHub Personal Access Token** with `public_repo` (or equivalent read access to public repos)
- **OpenAI API key** with access to your configured model

---

## Quick Start

```bash
git clone https://github.com/Mahnoor-Zaffar/Issue_Alert.git
cd Issue_Alert

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env               # add GITHUB_TOKEN and OPENAI_API_KEY
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

### Docker

```bash
docker compose up --build
```

---

## Configuration

Copy `.env.example` to `.env` and fill in required values:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for Search + Repos API |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model used for triage |
| `POLL_INTERVAL_SECONDS` | No | `60` | Seconds between poll cycles |
| `ISSUE_DISCOVERY_WINDOW_MINUTES` | No | `10` | Only fetch issues created within this window |
| `GIT_CLONE_TIMEOUT_SECONDS` | No | `60` | Timeout for shallow clones |
| `MAX_FILE_BYTES` | No | `20000` | Max bytes read per repo file |
| `MIN_REPO_STARS` | No | `0` | Minimum stars in search query |
| `DATABASE_PATH` | No | `./data/triage.db` | SQLite file location |
| `API_HOST` / `API_PORT` | No | `127.0.0.1` / `8000` | Dashboard bind address |

Search preferences (labels, languages, min stars) can also be changed from the dashboard **Preferences** panel without editing code.

---

## Project Structure

```
Issue_Alert/
├── daemon/           # Background poller, git extraction, AI triage
├── api/              # FastAPI app, REST + SSE routes
├── db/               # Schema, migrations, SQLite store
├── static/           # Dashboard (served locally by FastAPI)
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
| `/api/health` | GET | Service health and poll statistics |
| `/api/issues` | GET | List issues (`language`, `status`, `label`, `bookmarked_only`) |
| `/api/issues/{id}` | GET | Single issue with triage report |
| `/api/issues/{id}/bookmark` | POST | Toggle bookmark |
| `/api/issues/{id}/dismiss` | POST | Dismiss / restore issue |
| `/api/trigger-poll` | POST | Request immediate daemon poll |
| `/api/preferences` | GET / PUT | Search preferences |
| `/api/events` | GET | SSE stream for live updates |
| `/api/webhooks/github` | POST | Optional webhook receiver |

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
| Triage status `error` | Invalid or expired OpenAI key | Verify `OPENAI_API_KEY` in `.env` |
| No desktop notifications | plyer unsupported in environment | Non-fatal; issues still process normally |
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
