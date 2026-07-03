#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env — add your GITHUB_TOKEN and OPENAI_API_KEY before running."
  exit 1
fi

mkdir -p data

echo "Starting daemon..."
python -m daemon.main &
DAEMON_PID=$!

echo "Starting dashboard on http://127.0.0.1:8000 ..."
uvicorn api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

cleanup() {
  echo "Shutting down..."
  kill "$DAEMON_PID" "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Both services running. Press Ctrl+C to stop."
wait
