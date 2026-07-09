#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

api_alive=0
daemon_alive=0

curl -sf http://127.0.0.1:8000/api/health > /dev/null 2>&1 && api_alive=1
pgrep -f "daemon.main" > /dev/null 2>&1 && daemon_alive=1

echo "─"$(printf '─%.0s' $(seq 1 40))"─"
printf " %-20s │ %s\n" "Component" "Status"
echo "─"$(printf '─%.0s' $(seq 1 40))"─"
printf " %-20s │ %s\n" "API Server"  "$( [ $api_alive -eq 1 ] && echo '● Running' || echo '○ Stopped' )"
printf " %-20s │ %s\n" "Daemon"      "$( [ $daemon_alive -eq 1 ] && echo '● Running' || echo '○ Stopped' )"

if [ $api_alive -eq 1 ]; then
  echo ""
  curl -sf http://127.0.0.1:8000/api/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  Total issues: {d[\"total\"]}')
print(f'  Triaged:      {d[\"complete\"]}')
print(f'  Pending:      {d[\"pending\"]}')
print(f'  Last poll:    {d.get(\"last_poll_message\", \"-\")}')
"
fi
echo "─"$(printf '─%.0s' $(seq 1 40))"─"
