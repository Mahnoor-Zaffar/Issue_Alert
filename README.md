# GitHub Issue Triage Daemon + Dashboard

A lightweight local system that polls GitHub for open-source contribution opportunities, extracts repository context, runs AI triage, sends desktop notifications, and displays results on a live web dashboard.

## Features

- Polls GitHub Search API every 5 minutes for issues labeled `good first issue`, `help wanted`, or `open-source` in JavaScript, Python, Go, and Rust
- Native desktop push notifications via plyer when new issues are found
- Shallow git clone + extraction of the 3 most recently modified files for context
- OpenAI-powered triage with architecture context, issue breakdown, and PR action plan
- Vanilla HTML/CSS/JS dashboard with anime.js animations and SSE live updates

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

Two separate processes share state via SQLite (WAL mode):

```bash
# Terminal 1 — background daemon
python -m daemon.main

# Terminal 2 — web dashboard
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in your browser.

## Architecture

```
daemon/     → polls GitHub, clones repos, runs AI triage, writes to SQLite
api/        → FastAPI server serving REST + SSE + static dashboard
db/         → shared SQLite persistence layer
static/     → vanilla frontend (HTML, CSS, JS + anime.js)
```

## Configuration

See `.env.example` for all environment variables.
