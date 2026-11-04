#!/bin/bash
# Start the Axalon relay + Cloudflare tunnel locally.
# Run once: chmod +x deploy/start-relay-local.sh
# Usage: ./deploy/start-relay-local.sh

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Secrets come from the environment or from $REPO/.env.relay (gitignored).
# Copy deploy/env.relay.example to .env.relay and fill in real values.
ENV_FILE="${RELAY_ENV_FILE:-$REPO/.env.relay}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

for var in DRONE_TOKENS OPS_TOKEN TURN_SECRET; do
  if [ -z "${!var:-}" ]; then
    echo "[relay] $var is not set (export it or add it to $ENV_FILE)" >&2
    exit 1
  fi
done

export TURN_HOST="${TURN_HOST:-relay.axalonsystems.com}"
export PYTHONSAFEPATH=1

echo "[relay] starting uvicorn on :8800..."
cd /tmp
$REPO/.venv-relay/bin/uvicorn drone.relay.server:app \
  --host 0.0.0.0 --port 8800 &
RELAY_PID=$!

sleep 2
echo "[relay] starting cloudflare tunnel..."
$HOME/cloudflared tunnel --config $HOME/.cloudflared/config.yml --protocol http2 run axalon-relay &
TUNNEL_PID=$!

echo "[relay] relay PID=$RELAY_PID  tunnel PID=$TUNNEL_PID"
echo "[relay] press Ctrl+C to stop both"

trap "kill $RELAY_PID $TUNNEL_PID 2>/dev/null; exit" INT TERM
wait
