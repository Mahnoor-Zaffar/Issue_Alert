# GitHub Issue Triage System

A production-grade, local-first observability platform for discovering, enriching, and prioritizing open-source issues across GitHub. The system continuously monitors a configurable corpus of repositories and organizations, extracts repository context, and generates actionable AI-assisted triage reports — all delivered through a real-time single-page application.

[![Deploy GitHub Pages](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml/badge.svg)](https://github.com/Mahnoor-Zaffar/Issue_Alert/actions/workflows/pages.yml)

---

## Overview

The system is architected as two cooperating services that communicate through a shared SQLite datastore:

| Service | Responsibility |
|---------|----------------|
| **Daemon** | Dedicated background worker that polls the GitHub Search API, deduplicates incoming issues, extracts repository context via shallow clone, invokes an LLM for structural analysis, and persists results. |
| **API + Dashboard** | FastAPI backend serving a React 19 / Tailwind CSS v4 SPA. Exposes a REST surface plus a Server-Sent Events (SSE) stream for live updates. |

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

### Ingestion Pipeline

Each issue passes through a deterministic, stateless pipeline:

1. **Discovery** — Enumerates open issues from tracked organizations/repositories plus a curated search query (labels, min stars, language), bounded by a configurable discovery window.
2. **Verification** — Filters out issues with active assignees, existing commentary, or linked pull requests to surface unclaimed work.
3. **Context Extraction** — Retrieves the relevant file tree and source files to ground the analysis in the actual codebase.
4. **Evaluation** — An LLM synthesizes a triage report: architecture context, problem breakdown, and a concrete action plan with file-level references.
5. **Notification** — Desktop notifications dispatched for priority findings.
6. **Delivery** — Results stream to the dashboard in real time over SSE.

---

## Features

- **Multi-level priority tracking** — Watch individual repositories or entire organizations; issues are surfaced in a dedicated, visually distinct priority section.
- **Priority scoring** — Issues are ranked by tracked repos/orgs with scoring baked into the runtime ordering.
- **Configurable discovery** — Language, label, difficulty, and minimum-stars constraints, adjustable at runtime without restarts.
- **LLM-agnostic triage** — Works with OpenAI, OpenRouter, or any OpenAI-compatible endpoint.
- **Real-time delivery** — New issues appear live via SSE; no page refresh required.
- **Full issue lifecycle** — Bookmark, dismiss (with undo), view reports, and track triage status.
- **Draft PR generation** — Auto-create draft pull requests for triaged issues with extracted patch candidates.
- **Bounty detection** — Scans labels and body text for bounty markers and incentives; flagged issues get a dedicated badge and filter.
- **Priority alerts** — Desktop notifications, Web Audio chime, and toast fallback for priority discoveries.
- **Rate-limit awareness** — Exponential backoff, retry state tracking, and a dashboard-visible indicator.
- **Operational tooling** — Daemon log viewer, poll-now trigger, status/stop scripts, and a data reset utility.
- **Persisted state** — Filters, search, and sort preferences survive reloads via URL query parameters.
- **Selective triage** — Batch triage, difficulty assignment, and re-triage with contextual feedback.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Persistence | SQLite (WAL mode) |
| GitHub | Search API, Contents API, source extraction |
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

Run the full stack:

```bash
chmod +x start.sh
./start.sh
```

Open **http://localhost:8000**.

### Development Mode

Run daemon and API in separate terminals:

```bash
# Terminal 1 — daemon
source .venv/bin/activate
python -m daemon.main

# Terminal 2 — API server
source .venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

For frontend development, start the Vite dev server from `react-app/` — it proxies `/api` to `localhost:8000`:

```bash
cd react-app
npm run dev
```

---

## Configuration

Environment-driven configuration via `.env` (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT for Search + Contents API |
| `LLM_API_KEY` | Yes | — | LLM provider key (OpenRouter or OpenAI) |
| `LLM_MODEL` | No | `gpt-4o-mini` | Triage model |
| `LLM_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL |
| `POLL_INTERVAL_SECONDS` | No | `60` | Poll cadence |
| `ISSUE_DISCOVERY_WINDOW_MINUTES` | No | `10080` | Initial scan window (7 days) |
| `MAX_ISSUE_COMMENTS` | No | `5` | Max commentary before considered claimed (`0` = untouched) |
| `MIN_REPO_STARS` | No | `1000` | Star threshold for candidate repos |
| `DATABASE_PATH` | No | `./data/triage.db` | SQLite location |
| `API_HOST` / `API_PORT` | No | `127.0.0.1` / `8000` | Bind address |

Discovery preferences are also editable from the **Preferences** panel at runtime.

---

## Project Structure

```
Issue_Alert/
├── daemon/                  # Background poller, extraction, AI triage
│   ├── main.py              # Entry point; orchestration loop
│   ├── poller.py            # GitHub Search + issue normalization
│   ├── triage.py            # LLM triage engine
│   ├── context_extractor.py # Source-tree extraction
│   ├── rate_limiter.py      # Rate-limit tracking
│   └── notifier.py          # Desktop notifications
├── api/
│   ├── main.py              # App factory, mounting, lifespan
│   └── routes.py            # REST + SSE endpoints
├── db/                      # Schema + data-access layer
├── config/
│   └── settings.py          # Pydantic settings
├── react-app/               # React 19 + Vite + Tailwind SPA
│   └── src/
│       ├── App.jsx          # Orchestrator (SSE, filters, search, sort)
│       ├── api.js           # API client
│       ├── useSSE.js        # SSE hook with exponential reconnect
│       ├── utils.js         # Formatting helpers
│       └── components/      # Sidebar, IssueCard, TriagePanel, Toast, BountyPopup
├── static/                  # Served static assets (react-dist/, favicon)
├── data/                    # Runtime data (gitignored)
├── docs/                    # GitHub Pages build output
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
| `/api/priority-repos` | GET / POST | List / add tracked repos & orgs |
| `/api/priority-repos/{id}` | DELETE | Remove a tracked repo |
| `/api/preferences` | GET / PUT | Discovery preferences |
| `/api/trigger-poll` | POST | Request an immediate poll cycle |
| `/api/rate-limit` | GET | GitHub rate-limit state |
| `/api/daemon-log` | GET | Recent daemon log lines |
| `/api/stats/history` | GET | Per-day stats history |
| `/api/stats/personal` | GET | Personal contribution summary |
| `/api/stats/resume` | GET | Resume-style activity summary |
| `/api/pr-details` | GET | PR details (files, checks, status) |
| `/api/health` | GET | Health + poll statistics |
| `/api/events` | GET | SSE stream |
| `/api/webhooks/github` | POST | Optional webhook receiver |

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

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `p` | Poll now |
| `r` | Refresh feed |
| `Esc` | Close triage panel |

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---------|--------------|------------|
| `command not found: python` | venv not activated | `source .venv/bin/activate` |
| `address already in use :8000` | Stale API process | `./stop.sh` then restart |
| `0 fetched, 0 new` | Overly restrictive discovery query | Lower min stars / broaden labels |
| Triage status `error` | Invalid or expired LLM key | Verify `LLM_API_KEY` |
| Missing desktop notifications | Backend notification bridge unavailable | Non-fatal; issues still process |
| Blank dashboard | Frontend not built | `cd react-app && npm run build` |

---

## License

Open source. See the repository for license details.

---

## Author

**Mahnoor Zaffar** — [GitHub](https://github.com/Mahnoor-Zaffar)