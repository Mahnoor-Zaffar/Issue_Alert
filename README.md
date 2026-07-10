# GitHub Issue Triage

A local-first system for discovering unclaimed open-source issues from 1000+ star repos, enriching them with repository context, and producing AI triage reports — delivered through a real-time React+Tailwind dashboard.

[![Deploy GitHub Pages](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml/badge.svg)](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml)

---

## Overview

Two cooperating processes run on your machine:

| Process | Role |
|---------|------|
| **Daemon** | Polls GitHub (Search API + priority repos), deduplicates, extracts repo context via shallow clone, calls LLM for kid-friendly triage, persists to SQLite |
| **API + Dashboard** | FastAPI backend serving a React 19 + Tailwind CSS v4 SPA with SSE live feed, REST endpoints, sidebar panels, and keyboard shortcuts |

```
┌─────────────────┐     poll / triage      ┌──────────────────┐
│  daemon/         │ ─────────────────────► │  data/triage.db  │
│  (background)    │                        │  (SQLite WAL)    │
└─────────────────┘                        └────────┬─────────┘
                                                     │ read
                                                     ▼
┌─────────────────┐     SSE + REST           ┌──────────────────┐
│  Browser         │ ◄─────────────────────── │  api/ + static/  │
│  Dashboard       │                          │  (FastAPI)       │
└─────────────────┘                          └──────────────────┘
```

### Pipeline (per issue)

1. **Discover** — GitHub Search API (`good first issue`, `help wanted`) + priority repos, filtered by language, labels, min stars
2. **Verify** — Skip if already assigned, has comments, or has an open PR (claim verification)
3. **Extract** — Shallow-clone the repo, read file tree + relevant source files
4. **Triage** — LLM generates kid-friendly report: architecture context, issue breakdown, action plan, difficulty badge (🟢/🟡/🔴)
5. **Notify** — Desktop notification via `plyer` (for priority repos)
6. **Display** — Dashboard updates live over Server-Sent Events

---

## Features

- **Priority repos** — watch specific repos with desktop notifications; shown in a dedicated feed section
- **Configurable search** — languages, labels, minimum stars, show/hide dismissed (all adjustable from the dashboard)
- **LLM-agnostic** — works with OpenAI, OpenRouter, or any OpenAI-compatible API
- **Kid-friendly triage** — architecture context, issue breakdown, step-by-step action plan with code snippets
- **Linear-inspired UI** — dark theme, React 19 + Tailwind CSS v4, Inter font, custom design tokens
- **SSE live feed** — new issues appear in real time without page refresh
- **Bookmark, dismiss (with undo), view reports** from the issue feed
- **Auto-create draft PRs** for "easy" issues (search-and-replace patches from triage report)
- **Difficulty cycling** — mark issues easy/medium/hard to track your skill level
- **Re-triage** — re-run LLM analysis with optional feedback message
- **Daemon log viewer** — browse the daemon log right from the sidebar
- **Keyboard shortcuts** — `p` = poll now, `r` = refresh, `Esc` = close panel
- **Rate-limit-aware** GitHub client with exponential backoff + dashboard indicator
- **Poll Now** trigger from the dashboard sidebar
- **Priority notification chime** — Web Audio API tone for priority repo discoveries
- **Filter toolbar** — language, status, difficulty, label, saved, priority; sort by newest/oldest/stars/repo name
- **Search box** — frontend filter by title, body, or repo name
- **URL-persisted filters** — shareable filter state via query params
- **macOS desktop notifications** for priority repo issues

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Persistence | SQLite (WAL mode) |
| GitHub | Search API, Contents API, shallow git clone |
| AI | OpenRouter / OpenAI (`gpt-4o-mini` default) |
| Frontend | React 19, Vite 8, Tailwind CSS v4 |
| Real-time | Server-Sent Events (SSE) |
| Notifications | `plyer` (cross-platform desktop) |
| CI / Pages | GitHub Actions |

---

## Prerequisites

- **Python 3.11+** with `venv` support
- **Node.js 20+** + npm (for building the frontend)
- **GitHub Personal Access Token** with `public_repo` (or equivalent read access)
- **LLM API key** — [OpenRouter](https://openrouter.ai/) recommended

---

## Quick Start

```bash
git clone https://github.com/Mahnoor-Zaffar/Issue_Alert.git
cd Issue_Alert

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # add GITHUB_TOKEN and LLM_API_KEY

cd react-app
npm install
npm run build               # builds to ../static/react-dist/
cd ..
```

### Run locally

```bash
chmod +x start.sh
./start.sh
```

Open **http://localhost:8000**

Or run in two terminals for development:

```bash
# Terminal 1 — daemon
source .venv/bin/activate
python -m daemon.main

# Terminal 2 — API server
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

For frontend development, start the Vite dev server from `react-app/`:

```bash
cd react-app
npm run dev    # proxies /api to localhost:8000
```

---

## Configuration

Copy `.env.example` to `.env` and fill in required values:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for Search + Contents API |
| `LLM_API_KEY` | Yes | — | LLM API key (OpenRouter or OpenAI) |
| `LLM_MODEL` | No | `gpt-4o-mini` | Model used for triage |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` | LLM API base URL |
| `POLL_INTERVAL_SECONDS` | No | `60` | Seconds between poll cycles |
| `SEARCH_LOOKBACK_MINUTES` | No | `60` | How far back to search each poll |
| `ISSUE_DISCOVERY_WINDOW_MINUTES` | No | `10080` | Initial full scan window (7 days) |
| `MAX_ISSUE_COMMENTS` | No | `5` | Max comments allowed (`0` = untouched only) |
| `MIN_REPO_STARS` | No | `1000` | Minimum stars for repos in search |
| `DATABASE_PATH` | No | `./data/triage.db` | SQLite file location |
| `API_HOST` / `API_PORT` | No | `127.0.0.1` / `8000` | Dashboard bind address |

Search preferences (languages, labels, min stars, show dismissed) can also be changed from the dashboard **Preferences** panel.

---

## Project Structure

```
Issue_Alert/
├── daemon/                # Background poller, context extraction, AI triage
│   ├── main.py            # Daemon entry point + main loop
│   ├── poller.py          # GitHub Search API + issue fetching
│   ├── triage.py          # LLM-based triage engine
│   ├── context_extractor.py  # Shallow clone + file tree extraction
│   ├── rate_limiter.py    # GitHub API rate-limit tracking
│   └── notifier.py        # Desktop notifications (plyer)
├── api/                   # FastAPI backend
│   ├── main.py            # App creation, CORS, static mounts, lifespan
│   └── routes.py          # All REST + SSE endpoints
├── db/                    # Database schema and store
├── config/
│   └── settings.py        # Pydantic settings (loaded from .env)
├── react-app/             # React 19 + Vite + Tailwind frontend
│   └── src/
│       ├── App.jsx        # Orchestrator with SSE, filters, search, sort, pagination
│       ├── api.js         # API client wrappers
│       ├── useSSE.js      # SSE hook with exponential reconnect
│       ├── utils.js       # Time-ago helper
│       └── components/
│           ├── Sidebar.jsx      # Stats, sparkline, rate limit, poll, preferences, logs
│           ├── IssueCard.jsx    # Issue card with badges, actions, hover menu
│           ├── TriagePanel.jsx  # Slide-out triage report panel
│           └── Toast.jsx        # Auto-dismissing toast notifications
├── static/                # Served static assets
│   └── react-dist/        # Production frontend build
├── data/                  # Runtime data (gitignored except .gitkeep)
│   ├── triage.db          # SQLite database
│   ├── rate_limit.json    # GitHub API rate-limit state
│   └── daemon.log         # Rotating daemon log
├── docs/                  # GitHub Pages build output
├── scripts/
│   ├── build_pages.sh
│   └── reset_db.py
├── start.sh               # Launch daemon + API
├── stop.sh                # Stop daemon + API
├── status.sh              # Check running status
├── run.sh                 # Legacy run script
└── docker-compose.yml     # Docker deployment
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/issues` | GET | List issues (filter by language, status, label, difficulty, bookmarked, priority) |
| `/api/issues/{id}` | GET | Single issue with triage report |
| `/api/issues/{id}/bookmark` | POST | Toggle bookmark |
| `/api/issues/{id}/dismiss` | POST | Dismiss / restore issue |
| `/api/issues/{id}/view` | POST | Mark as viewed (removes from feed) |
| `/api/issues/{id}/difficulty` | POST | Set difficulty (easy/medium/hard) |
| `/api/issues/{id}/re-triage` | POST | Re-run LLM triage (optional feedback message) |
| `/api/issues/{id}/open-pr` | POST | Auto-create draft PR from triage (easy issues only) |
| `/api/priority-repos` | GET / POST | List / add watched repos |
| `/api/priority-repos/{id}` | DELETE | Remove a watched repo |
| `/api/preferences` | GET / PUT | Search preferences (languages, labels, min_stars, show_dismissed) |
| `/api/trigger-poll` | POST | Request immediate daemon poll |
| `/api/rate-limit` | GET | Current GitHub API rate-limit state |
| `/api/daemon-log` | GET | Last N lines of daemon log |
| `/api/stats/history` | GET | Daily stats history |
| `/api/pr-details` | GET | Fetch PR details from GitHub (files, checks, status) |
| `/api/health` | GET | Service health and poll statistics |
| `/api/events` | GET | SSE stream for live issue updates |
| `/api/admin/clear-data` | POST | Clear all database data |
| `/api/webhooks/github` | POST | Optional webhook receiver |

---

## Priority Repos

Add repos to the **Priority Repos** panel in the sidebar to:
- Watch specific repos that matter most to you
- Get desktop notifications when new issues are found
- See them in a separate priority section at the top of the feed
- Issues from priority repos are tagged and filterable

---

## Triage Reports

Each triaged issue includes a kid-friendly analysis with:
- **Architecture Context** — what this part of the code does with real-life analogies
- **Issue Breakdown** — the bug or feature explained in plain language
- **Action Plan** — step-by-step with files, line references, and code snippets
- **Difficulty badge** — 🟢 Easy / 🟡 Medium / 🔴 Hard
- **Claim comment** — pre-written GitHub comment to express interest (copy from the panel)

---

## GitHub Pages

The dashboard UI is published on push to `main` via GitHub Actions.

**One-time setup:**
1. Go to **Settings → Pages → Build and deployment**
2. Set **Source** to **GitHub Actions**

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

### Stop the services

```bash
./stop.sh
```

### Check status

```bash
./status.sh
```

### Rebuild frontend

```bash
cd react-app
npm run build
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `p` | Poll now |
| `r` | Refresh feed |
| `Esc` | Close triage panel |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `command not found: python` | venv not activated | `source .venv/bin/activate` |
| `address already in use :8000` | Old server still running | `./stop.sh` then restart |
| `0 fetched, 0 new` in logs | Overly restrictive search query | Lower min stars in Preferences |
| Triage status `error` | Invalid or expired LLM API key | Verify `LLM_API_KEY` in `.env` |
| No desktop notifications | `plyer` backend unavailable | Non-fatal; issues still process |
| React app shows blank page | Frontend not built | `cd react-app && npm run build` |
| Pages deploy fails | Branch source still enabled | Set **Source** to **GitHub Actions** only |

---

## License

This project is open source. See the repository for license details.

---

## Author

**Mahnoor Zaffar** — [GitHub](https://github.com/Mahnoor-Zaffar)
