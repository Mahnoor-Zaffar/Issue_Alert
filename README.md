# GitHub Issue Triage Daemon + Dashboard

A lightweight local system that polls GitHub for open-source contribution opportunities, extracts repository context, runs AI triage, sends desktop notifications, and displays results on a live web dashboard.

## Features

- Polls GitHub Search API for issues labeled `good first issue`, `help wanted`, `open source`, or `open-source`
- Filters by JavaScript, Python, Go, and Rust (configurable in dashboard)
- Native desktop push notifications via plyer
- Shallow git clone + extraction of the 3 most recently modified files
- OpenAI-powered triage with architecture context, issue breakdown, and PR action plan
- Live dashboard with SSE updates, filters, bookmark/dismiss, export, and poll-now trigger
- Optional GitHub webhook endpoint for real-time issue ingestion

## Prerequisites

- Python 3.11+
- `git` CLI on PATH
- GitHub Personal Access Token
- OpenAI API Key

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your GITHUB_TOKEN and OPENAI_API_KEY
```

## Running

### Option A — Single script

```bash
chmod +x run.sh
./run.sh
```

### Option B — Two terminals

```bash
# Terminal 1 — daemon
python -m daemon.main

# Terminal 2 — dashboard
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

### Option C — Docker Compose

```bash
docker compose up --build
```

## Testing / Reset

Clear all issue data for a fresh run:

```bash
python scripts/reset_db.py
```

Then click **Poll Now** on the dashboard or restart the daemon.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/issues` | GET | List issues (supports `language`, `status`, `label`, `bookmarked_only` filters) |
| `/api/issues/{id}` | GET | Single issue |
| `/api/issues/{id}/bookmark` | POST | Bookmark/unbookmark |
| `/api/issues/{id}/dismiss` | POST | Dismiss/restore |
| `/api/trigger-poll` | POST | Request immediate poll from daemon |
| `/api/preferences` | GET/PUT | Search preferences |
| `/api/webhooks/github` | POST | GitHub webhook receiver |
| `/api/events` | GET | SSE live feed |
| `/api/health` | GET | Stats + last poll info |

## Configuration

See `.env.example` for all environment variables.

Dashboard **Preferences** panel lets you adjust languages, labels, and min repo stars without editing code.

## Architecture

```
daemon/     → polls GitHub, clones repos, runs AI triage, writes to SQLite
api/        → FastAPI server serving REST + SSE + static dashboard
db/         → shared SQLite persistence layer (WAL mode)
static/     → vanilla frontend (HTML, CSS, JS + anime.js)
```
