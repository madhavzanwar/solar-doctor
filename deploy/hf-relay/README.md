---
title: Axalon Drone Relay
emoji: 🛰️
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Axalon Drone Relay

WebSocket relay between the Axalon drone agent (Jetson) and operators in the
browser (`/platform` Live Ops).

| Path | Purpose |
|------|---------|
| `GET /health`, `GET /` | Readiness probe, returns `{"status":"ok"}` |
| `GET /turn-credentials?token=…&name=…` | ICE servers for WebRTC (operator token) |
| `WS /ws/drone/{drone_id}?token=…` | Drone agent |
| `WS /ws/ops/{drone_id}?token=…&operator=…` | Browser operator |

Configure under **Settings → Variables and secrets** (names only; never commit values):

- Secrets: `DRONE_TOKENS` (`id:token,id2:token2`), `OPS_TOKEN`, optional `TURN_SECRET`
- Variables: optional `RELAY_CORS_ORIGINS` (default
  `https://axalonsystems.com,https://www.axalonsystems.com`), optional
  `RELAY_PING_INTERVAL_S` (default 25), optional `TURN_HOST`

coturn cannot run on Hugging Face (no UDP/3478 ingress), so without an external
`TURN_HOST` the relay hands out public STUN only. Full runbook:
`docs/DEPLOY_DRONE_OPS.md` in the AxalonSystems repo.
