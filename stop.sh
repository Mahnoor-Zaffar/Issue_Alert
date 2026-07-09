#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ -f .daemon.pid ]; then
  kill $(cat .daemon.pid) 2>/dev/null && echo "Daemon stopped" || echo "Daemon was not running"
  rm -f .daemon.pid
else
  pkill -f "daemon.main" 2>/dev/null && echo "Daemon stopped" || echo "Daemon was not running"
fi

if [ -f .api.pid ]; then
  kill $(cat .api.pid) 2>/dev/null && echo "API stopped" || echo "API was not running"
  rm -f .api.pid
else
  pkill -f "uvicorn" 2>/dev/null && echo "API stopped" || echo "API was not running"
fi
