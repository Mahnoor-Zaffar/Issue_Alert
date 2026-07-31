#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Kill any existing processes on port 8000
lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true

# Kill existing daemon
[ -f .daemon.pid ] && kill $(cat .daemon.pid) 2>/dev/null || true
[ -f .api.pid ] && kill $(cat .api.pid) 2>/dev/null || true
sleep 1

# Clear stale bytecode
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Reset viewed_at so issues never vanish
.venv/bin/python -c "
from db.store import init_db, get_connection; init_db()
with get_connection() as c:
    c.execute('UPDATE issues SET viewed_at = NULL')
" 2>/dev/null || true

echo "Starting daemon..."
nohup .venv/bin/python -m daemon.main > /dev/null 2>&1 &
echo $! > .daemon.pid

echo "Starting API server..."
nohup .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &
echo $! > .api.pid

sleep 2
echo "Ready at http://localhost:8000"
