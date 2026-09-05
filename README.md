# GitHub Issue & PR Triage System

A production-grade, local-first observability platform for discovering, enriching, triaging, and **reviewing** open-source work across GitHub. The system continuously monitors a configurable corpus of repositories and organizations, extracts repository context, and generates AI-assisted triage reports and PR reviews — delivered through a real-time single-page application with a REST + SSE surface.

[![Deploy GitHub Pages](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml/badge.svg)](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Operations](#operations)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

The platform is architected as **two cooperating services** that communicate through a shared SQLite datastore running in WAL mode:

| Service | Responsibility |
|---------|----------------|
| **Daemon** | Dedicated background worker that polls the GitHub Search/Pulls API, deduplicates incoming work, extracts repository context, invokes a configurable LLM for triage and PR review, and persists results. |
| **API + Dashboard** | FastAPI backend serving a React 19 / Tailwind CSS v4 SPA. Exposes a versioned REST surface plus a Server-Sent Events (SSE) stream for live updates. |

```
┌─────────────────┐   poll / triage / review   ┌──────────────────┐
│  daemon/         │ ─────────────────────────► │  data/triage.db  │
│  (background)    │                            │  (SQLite WAL)    │
└─────────────────┘                            └────────┬─────────┘
                                                        │ read
                                                        ▼
┌─────────────────┐        SSE + REST           ┌──────────────────┐
│  Browser         │ ◄───────────────────────── │  api/ + static/  │
│  Dashboard       │                            │  (FastAPI)       │
└─────────────────┘                            └──────────────────┘
```

### Ingestion Pipeline

Each issue passes through a deterministic, stateless pipeline:

1. **Discovery** — Enumerates open issues from tracked repositories/organizations plus a curated search query (labels, min stars, language), bounded by a configurable discovery window.
2. **Verification** — Filters out issues with active assignees, existing commentary, or linked pull requests to surface unclaimed work.
3. **Context Extraction** — Retrieves the relevant file tree and source files to ground analysis in the actual codebase.
4. **Evaluation** — An LLM synthesizes a triage report: architecture context, problem breakdown, and a concrete action plan with file-level references.
5. **Notification** — Desktop notifications dispatched for priority findings.
6. **Delivery** — Results stream to the dashboard in real time over SSE.

### PR Review Pipeline

Open pull requests are scanned separately and can be reviewed by the LLM:

1. **Discovery** — Monitors open PRs in priority and general repositories, with a per-repo cap.
2. **Queue** — Users request a review from the dashboard (manual), or the daemon auto-queues fresh, never-reviewed PRs.
3. **Review** — The LLM reads the diff, CI check status, and changed files to produce a grounded review comment.
4. **Delivery** — Ready reviews stream back; users can copy them or **post directly to GitHub** as a public comment.

**Guardrails:**

- **Archived / read-only repositories are skipped** at every ingress point (scan, poll, webhook) and rejected in the reviewer before any LLM call or rate-limit spend.
- **Daily auto-review cap** (default 20/day, 5/cycle) prevents runaway background spend; manual queueing is never limited.

---

## Features

**Triage & Discovery**
- **Multi-level priority tracking** — Watch individual repositories or entire organizations; issues surface in a dedicated priority section.
- **Priority scoring** — Issues are ranked by tracked repos/orgs with scoring baked into runtime ordering.
- **Configurable discovery** — Language, label, difficulty, and minimum-stars constraints adjustable at runtime without restarts.
- **LLM-agnostic triage** — Works with OpenAI, OpenRouter, or any OpenAI-compatible endpoint.
- **Selective triage** — Batch triage, difficulty assignment, and re-triage with contextual feedback.

**Pull Request Reviews**
- Per-PR LLM review with diff + CI-aware context.
- **Copy review** or **post directly to GitHub** as a public comment.
- Live review panel that polls and surfaces ready reviews without a refresh.

**Delivery & UX**
- **Real-time delivery** — New issues appear live via SSE; no page refresh required.
- **Full issue lifecycle** — Bookmark, dismiss (with undo), view reports, track triage status.
- **Draft PR generation** — Auto-create draft pull requests for triaged issues with extracted patch candidates.
- **Priority alerts** — Desktop notifications, Web Audio chime, and toast fallback.
- **Persisted state** — Filters, search, and sort preferences survive reloads via URL query parameters.

**Robustness & Operations**
- **Rate-limit awareness** — Exponential backoff, retry state tracking, and a dashboard-visible indicator.
- **Webhook ingestion** — Optional GitHub webhook receiver surfaces new issues/PRs instantly.
- **Operational tooling** — Daemon log viewer, poll-now trigger, status/stop scripts, and a data reset utility.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Persistence | SQLite (WAL mode) |
| GitHub | Search API, Pulls API, Contents API, webhooks |
| AI | OpenAI / OpenRouter (`gpt-4o-mini` default) |
| Frontend | React 19, Vite 8, Tailwind CSS 4 |
| Real-time | Server-Sent Events |
| Notifications | Web Audio API + desktop notification bridge |
| CI / Pages | GitHub Actions |

---

## Prerequisites

- **Python 3.11+** with `venv`
- **Node.js 20+** with npm
- **GitHub Personal Access Token** with `public_repo` scope (or equivalent read access)
- **LLM API key** — [OpenRouter](https://openrouter.ai/) recommended

---

## Quick Start

```bash
git clone https://github.com/Mahnoor-Zaffar/Issue_Alert.git
cd Issue_Alert

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # add GITHUB_TOKEN and LLM_API_KEY

cd react-app
npm install
npm run build                 # emits to ../static/react-dist/
cd ..
```

Run the full stack (daemon + API):

```bash
chmod +x start.sh
./start.sh
```

Open **http://localhost:8090**.

> **Note:** `start.sh` resets the `viewed_at` state on each run. To restart processes without resetting state, stop and relaunch manually (see [Operations](#operations)).

### Development Mode

Run daemon and API in separate terminals:

```bash
# Terminal 1 — daemon
source .venv/bin/activate
python -m daemon.main

# Terminal 2 — API server
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8090
```

For frontend development, start the Vite dev server from `react-app/` — it proxies `/api` to `localhost:8090`:

```bash
cd react-app
npm run dev
```

---

## Configuration

Environment-driven configuration via `.env` (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for Search + Pulls + Contents API |
| `LLM_API_KEY` | Yes | — | LLM provider key (OpenRouter or OpenAI) |
| `LLM_MODEL` | No | `gpt-4o-mini` | Triage / review model |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL |
| `POLL_INTERVAL_SECONDS` | No | `60` | Poll cadence |
| `ISSUE_DISCOVERY_WINDOW_MINUTES` | No | `10080` | Initial scan window (7 days) |
| `MAX_ISSUE_COMMENTS` | No | `5` | Max commentary before considered claimed (`0` = untouched) |
| `MIN_REPO_STARS` | No | `1000` | Star threshold for candidate repos |
| `DATABASE_PATH` | No | `./data/triage.db` | SQLite location |
| `API_HOST` / `API_PORT` | No | `127.0.0.1` / `8090` | Bind address |

Discovery preferences are also editable from the **Preferences** panel at runtime. Repository scope is split into **priority repos** (tracked first) and **general repos** (secondary breadth).

---

## Project Structure

```
Issue_Alert/
├── daemon/                    # Background worker (poller, triage, review)
│   ├── main.py                # Entry point; orchestration loop, daily-cap logic
│   ├── poller.py              # GitHub Search + issue normalization
│   ├── pr_discovery.py        # PR scanning + webhook ingestion + archived-repo guard
│   ├── reviewer.py            # LLM PR review engine (ArchivedRepoError guard)
│   ├── archived.py            # Payload helpers for archived/read-only detection
│   ├── triage.py              # LLM triage engine
│   ├── context_extractor.py   # Source-tree extraction
│   ├── rate_limiter.py        # Rate-limit tracking
│   └── notifier.py            # Desktop notifications
├── api/
│   ├── main.py                # App factory, mounting, lifespan
│   └── routes.py              # REST + SSE endpoints
├── db/
│   └── store.py               # Schema, migrations, data-access layer
├── config/
│   └── settings.py            # Pydantic settings
├── react-app/                 # React 19 + Vite + Tailwind SPA
│   └── src/
│       ├── App.jsx            # Orchestrator (SSE, filters, search, sort)
│       ├── api.js             # API client
│       ├── useSSE.js          # SSE hook with exponential reconnect
│       ├── utils.js           # Formatting helpers
│       └── components/        # IssueCard, PrCard, PrReviewPanel, TriagePanel, …
├── static/                    # Served static assets (react-dist/, favicon)
├── data/                      # Runtime data (gitignored)
├── docs/                      # GitHub Pages build output
├── scripts/
│   ├── build_pages.sh
│   └── reset_db.py
├── start.sh / stop.sh / status.sh
└── docker-compose.yml
```

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/issues` | GET | List issues; filter by language, status, label, difficulty, bookmark, priority, bounty |
| `/api/issues/{id}` | GET | Single issue incl. triage report |
| `/api/issues/{id}/bookmark` | POST | Toggle bookmark |
| `/api/issues/{id}/dismiss` | POST | Dismiss / restore |
| `/api/issues/{id}/view` | POST | Mark viewed (removes from feed) |
| `/api/issues/{id}/difficulty` | POST | Assign difficulty |
| `/api/issues/{id}/re-triage` | POST | Re-run triage with optional feedback |
| `/api/issues/{id}/open-pr` | POST | Create draft PR from triage action plan |
| `/api/issues/batch-triage` | POST | Queue multiple issues for triage |
| `/api/prs` | GET | List open PRs (fresh/needing-review first) |
| `/api/prs/{pull_id}` | GET | Single PR incl. latest review + status |
| `/api/prs/{pull_id}/reviews` | POST | Queue (or regenerate) an LLM review |
| `/api/prs/{pull_id}/reviews/{review_id}/post` | POST | Post a ready review to GitHub as a comment |
| `/api/prs/{pull_id}/review-log` | GET | Latest review error detail for a PR |
| `/api/pr-details` | GET | PR details (files, checks, status) |
| `/api/priority-repos` | GET / POST | List / add tracked repos & orgs |
| `/api/priority-repos/{id}` | DELETE | Remove a tracked repo |
| `/api/general-repos` | GET / POST | List / add general (broad-scope) repos |
| `/api/general-repos/{id}` | DELETE | Remove a general repo |
| `/api/preferences` | GET / PUT | Discovery preferences |
| `/api/trigger-poll` | POST | Request an immediate poll cycle |
| `/api/rate-limit` | GET | GitHub rate-limit state |
| `/api/daemon-log` | GET | Recent daemon log lines |
| `/api/stats/history` | GET | Per-day stats history |
| `/api/stats/personal` | GET | Personal contribution summary |
| `/api/stats/resume` | GET | Resume-style activity summary |
| `/api/health` | GET | Health + poll statistics |
| `/api/events` | GET | SSE stream |
| `/api/webhooks/github` | POST | GitHub webhook receiver (issue + pull_request) |

---

## Triage Model

Triage reports are structured to be immediately actionable:

- **Architecture context** — what the affected subsystem does
- **Issue breakdown** — the behavior deviation, grounded in evidence
- **Action plan** — step-by-step remediation with file/line references
- **Difficulty estimate** — easy / medium / hard
- **Claim comment** — a prepared GitHub comment to signal intent

Reports are grounded in the extracted repository context; the system refuses to speculate where evidence is insufficient.

---

## Operations

### Manual restart (preserves state)

`start.sh` resets `viewed_at`; to restart without resetting state:

```bash
kill "$(cat .daemon.pid)" 2>/dev/null
find . -type d -name __pycache__ -exec rm -rf {} +
nohup .venv/bin/python -m daemon.main > data/daemon.out.log 2>&1 &

nohup .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8090 \
  > data/api.out.log 2>&1 &
```

### Reset local data

```bash
source .venv/bin/activate
python scripts/reset_db.py
```

Restart the daemon or trigger **Poll Now** afterwards.

### Stop / status / rebuild

```bash
./stop.sh
./status.sh

cd react-app && npm run build
```

### Maintenance

- **Archived repos** are auto-purged (PRs + reviews) when detected; no manual cleanup required.
- **Rate limits**: monitor via the dashboard indicator or `/api/rate-limit`; backoff is automatic.

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---------|--------------|------------|
| `command not found: python` | venv not activated | `source .venv/bin/activate` |
| `address already in use :8090` | Stale API process | `./stop.sh` then restart |
| `0 fetched, 0 new` | Overly restrictive discovery query | Lower min stars / broaden labels |
| Triage status `error` | Invalid or expired LLM key | Verify `LLM_API_KEY` |
| Missing desktop notifications | Backend notification bridge unavailable | Non-fatal; issues still process |
| Blank dashboard | Frontend not built | `cd react-app && npm run build` |
| PR shows "No review generated" | Review still queued or auto-cap reached | Wait for the poll cycle; manual queueing always works |

---

## License

Open source. See the repository for license details.

---

## Author

**Mahnoor Zaffar** — [GitHub](https://github.com/Mahnoor-Zaffar)
