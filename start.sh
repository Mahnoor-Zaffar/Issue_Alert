#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "Starting daemon..."
nohup .venv/bin/python -m daemon.main > /dev/null 2>&1 &
echo $! > .daemon.pid

echo "Starting API server..."
nohup .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &
echo $! > .api.pid

sleep 2
echo "Ready at http://localhost:8000"
