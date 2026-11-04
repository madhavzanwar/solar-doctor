# Axalon Drone Relay — Hugging Face Docker Space image.
#
# Build context is the Space repo root, laid out like this repo (see
# deploy/hf-relay/stage.sh):  Dockerfile, README.md, drone/{__init__.py,
# requirements.txt, common/, relay/}.  From this repo you can also build with:
#   docker build -f deploy/hf-relay/Dockerfile -t axalon-relay .
#
# Only the relay is copied — no platform/, ml/ or website code. With no platform/
# directory in the image the stdlib `platform` module can't be shadowed;
# PYTHONSAFEPATH=1 + running from /tmp are kept as belt-and-braces (root Dockerfile).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONSAFEPATH=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

# HF Spaces run the container as uid 1000; match it explicitly.
RUN useradd --create-home --uid 1000 relay
WORKDIR /app

COPY drone/requirements.txt ./drone/requirements.txt
RUN pip install --upgrade pip && pip install -r drone/requirements.txt

COPY drone/__init__.py ./drone/__init__.py
COPY drone/common/ ./drone/common/
COPY drone/relay/ ./drone/relay/

USER relay
EXPOSE 7860

# State is in-memory only (connections, control lock); nothing is written to disk,
# so HF's ephemeral filesystem and sleep/restart are safe.
# --proxy-headers: HF terminates TLS and forwards X-Forwarded-*.
# ws-ping 20/20: protocol-level pings (the agent's websockets client answers them);
# browsers additionally get application-level {"type":"ping"} frames
# every RELAY_PING_INTERVAL_S (default 25 s) so idle sockets survive ~60 s proxy timeouts.
# --no-access-log: tokens travel in WS/HTTP query strings; keep them out of Space logs.
CMD ["sh", "-c", "cd /tmp && exec python -m uvicorn drone.relay.server:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips '*' --ws-ping-interval 20 --ws-ping-timeout 20 --no-access-log"]
