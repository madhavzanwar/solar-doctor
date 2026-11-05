#!/usr/bin/env bash
# SolarDoctor dev runner: API + frontend together, stopped cleanly on Ctrl-C / SIGTERM.
# Loads .env (if present) into the environment of both processes.
# Ports: API_PORT (default 8000), WEB_PORT (default 3000).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYBIN="${PYBIN:-$ROOT/.venv/bin/python}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

if [ -f .env ]; then set -a; . ./.env; set +a; fi
export PYTHONSAFEPATH=1
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:$API_PORT}"

[ -x "$PYBIN" ] || { echo "dev.sh: $PYBIN not found - run 'make setup' first" >&2; exit 1; }
[ -d frontend/node_modules ] || { echo "dev.sh: frontend/node_modules missing - run 'make setup' first" >&2; exit 1; }

port_busy() {
  "$PYBIN" -I -c '
import socket, sys
p = int(sys.argv[1])
for fam, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
    try:
        s = socket.socket(fam, socket.SOCK_STREAM)
    except OSError:  # e.g. IPv6 unavailable in containers
        continue
    s.settimeout(0.5)
    try:
        if s.connect_ex((host, p)) == 0:
            sys.exit(0)
    except OSError:
        pass
    finally:
        s.close()
sys.exit(1)
' "$1"
}
for p in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$p"; then
    echo "dev.sh: port $p is already in use. Stop the other process or pick ports: make dev API_PORT=8010 WEB_PORT=3010" >&2
    exit 1
  fi
done

pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null || true; done
  sleep 1
  for pid in "${pids[@]:-}"; do [ -n "$pid" ] && kill -KILL -- "-$pid" 2>/dev/null || true; done
}
trap cleanup INT TERM EXIT

# setsid gives each child its own process group so the whole tree (reloader, next-server) can be signalled.
# The API runs from /tmp so a stray ./solardoctor package never shadows the installed one.
(cd /tmp && exec setsid "$PYBIN" -m uvicorn solardoctor.api.app:app --host 0.0.0.0 --port "$API_PORT" \
   --reload --reload-dir "$ROOT/backend") &
pids+=($!)
(cd frontend && exec setsid npm run dev -- -p "$WEB_PORT") &
pids+=($!)

echo "dev.sh: API http://localhost:$API_PORT/docs   UI http://localhost:$WEB_PORT   (Ctrl-C to stop)"
wait -n || true
