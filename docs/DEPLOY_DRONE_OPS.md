# Drone Remote Ops — Run & Deploy (Phase 1)

## Local end-to-end with ArduPilot SITL (no hardware)

1. **Install SITL** (once):
   ```bash
   pip install pymavlink mavproxy
   git clone https://github.com/ArduPilot/ardupilot --recursive
   cd ardupilot/ArduCopter && sim_vehicle.py -w   # build + init params
   ```
2. **Start SITL**, forwarding MAVLink to the agent's port:
   ```bash
   sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550 --console --map
   ```
3. **Start the relay**:
   ```bash
   DRONE_TOKENS="sitl-01:dtok" OPS_TOKEN="otok" \
     uvicorn drone.relay.server:app --host 0.0.0.0 --port 8800
   ```
4. **Start the agent**:
   ```bash
   DRONE_ID=sitl-01 DRONE_TOKEN=dtok \
     RELAY_WS_URL=ws://127.0.0.1:8800 \
     MAVLINK_URL=udpin:127.0.0.1:14550 TELEMETRY_HZ=5 \
     python -m drone.agent.main
   ```
5. **Fly it** in the SITL console: `mode guided`, `arm throttle`, `takeoff 40`.
6. **Run the e2e test**:
   ```bash
   RUN_SITL_E2E=1 RELAY_WS_URL=ws://127.0.0.1:8800 OPS_TOKEN=otok DRONE_ID=sitl-01 \
     python -m pytest drone/tests/test_e2e_sitl.py -v
   ```

## Production deploy

### Relay (Oracle A1 VM)
- `/etc/systemd/system/axalon-relay.service`:
  ```ini
  [Unit]
  Description=Axalon Drone Relay
  After=network-online.target
  [Service]
  Environment=DRONE_TOKENS=sitl-01:CHANGE_ME
  Environment=OPS_TOKEN=CHANGE_ME
  ExecStart=/usr/bin/uvicorn drone.relay.server:app --host 0.0.0.0 --port 8800
  WorkingDirectory=/opt/axalon
  Restart=always
  [Install]
  WantedBy=multi-user.target
  ```
- Front with Cloudflare for `wss://relay.axalonsystems.com`.
- Keep-alive cron to avoid Oracle Always-Free idle reclaim:
  `*/15 * * * * curl -s https://relay.axalonsystems.com/health >/dev/null`

### Relay (mounted in the API Space) — current production

**This is how production runs today.** Hugging Face now requires a paid plan to create
new Docker Spaces (`402 Payment Required`), so the relay is not its own Space. The
platform API mounts it at `/relay` (`platform/api/app.py`), inside the existing
`parakh20/axalon-api` Space:

| Setting | Where | Value |
|---|---|---|
| `DRONE_TOKENS` | API Space secret | `drone-01:<token>` |
| `OPS_TOKEN` | API Space secret | operator token |
| `NEXT_PUBLIC_RELAY_WS_URL` | Vercel `axalon-systems` (Production) | `wss://parakh20-axalon-api.hf.space/relay` |
| `NEXT_PUBLIC_RELAY_HTTP_URL` | Vercel `axalon-systems` (Production) | `https://parakh20-axalon-api.hf.space/relay` |
| `NEXT_PUBLIC_OPS_TOKEN` | Vercel `axalon-systems` (Production) | same as `OPS_TOKEN` |
| `RELAY_WS_URL` | Jetson agent env | `wss://parakh20-axalon-api.hf.space/relay` |
| `DRONE_ID` / `DRONE_TOKEN` | Jetson agent env | must match an entry in `DRONE_TOKENS` |

- The API's key/users auth skips `/relay/*`; the relay checks its own tokens.
- The API's CORS middleware covers `/relay` (the mounted relay is built with `cors=False`).
- Relay state is in-process: one uvicorn worker only.
- Caveats: the free Space sleeps after ~48 h without traffic (the drone's heartbeats keep
  it awake while flying), and a heavy inspection batch shares the same CPU as telemetry.
  No TURN on Hugging Face, so video falls back to public STUN.

### Relay (standalone Hugging Face Docker Space) — needs a paid plan for new Spaces

Use this when there is no always-on VM/tunnel origin (e.g. `relay.axalonsystems.com`
returning Cloudflare 530). HF terminates TLS and proxies WebSockets; the relay keeps
all state in memory, so the ephemeral disk is fine. Files live in `deploy/hf-relay/`.

1. **Create the Space**: huggingface.co → New Space → SDK **Docker** (blank template),
   hardware **CPU basic (free)**, visibility **Public** (a private Space needs an HF
   token on every request, which the browser and the Jetson can't send). The Space
   URL is `https://<user>-<space>.hf.space`.
2. **Upload the files** (only the relay, no ML/platform code):
   ```bash
   git clone https://huggingface.co/spaces/<user>/<space> /tmp/axalon-relay-space
   deploy/hf-relay/stage.sh /tmp/axalon-relay-space
   cd /tmp/axalon-relay-space && git add -A && git commit -m "Deploy relay" && git push
   ```
   The Space repo ends up with: `Dockerfile`, `README.md` (front matter `sdk: docker`,
   `app_port: 7860`), `drone/__init__.py`, `drone/requirements.txt`, `drone/common/`,
   `drone/relay/`. Rerun the same three commands to redeploy after relay changes.
3. **Settings → Variables and secrets** (names only; generate values with
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`):

   | Name | Kind | Required | Notes |
   |------|------|----------|-------|
   | `DRONE_TOKENS` | Secret | yes | `drone-01:<token>[,drone-02:<token>]` |
   | `OPS_TOKEN` | Secret | yes | must equal Vercel `NEXT_PUBLIC_OPS_TOKEN` |
   | `RELAY_CORS_ORIGINS` | Variable | no | default `https://axalonsystems.com,https://www.axalonsystems.com`; add preview/localhost origins comma-separated |
   | `RELAY_PING_INTERVAL_S` | Variable | no | default `25`; app-level ping to browsers, keep < 60 |
   | `TURN_HOST` | Variable | no | only if a coturn runs elsewhere (see caveat) |
   | `TURN_SECRET` | Secret | no | coturn `static-auth-secret`, only with `TURN_HOST` |

   Changing a secret restarts the Space.
4. **Verify**:
   ```bash
   curl -s https://<user>-<space>.hf.space/health            # {"status":"ok"}
   curl -si -H 'Origin: https://axalonsystems.com' \
     "https://<user>-<space>.hf.space/turn-credentials?token=$OPS_TOKEN&name=probe" \
     | grep -i access-control-allow-origin
   ```
5. **Vercel** (website project → Environment Variables → Production, then redeploy;
   `NEXT_PUBLIC_*` values are inlined at build time):
   - `NEXT_PUBLIC_RELAY_WS_URL=wss://<user>-<space>.hf.space` (no trailing slash; the
     client appends `/ws/ops/<drone>`)
   - `NEXT_PUBLIC_RELAY_HTTP_URL=https://<user>-<space>.hf.space`
   - `NEXT_PUBLIC_OPS_TOKEN` = the Space's `OPS_TOKEN`
6. **Jetson agent**: the agent reads its relay base URL from `RELAY_WS_URL`
   (`drone/agent/config.py`, used by `AgentConfig.ops_url()`). In the agent's systemd
   unit set `RELAY_WS_URL=wss://<user>-<space>.hf.space` and make `DRONE_ID` /
   `DRONE_TOKEN` match an entry in the Space's `DRONE_TOKENS`, then
   `sudo systemctl restart axalon-drone-agent`.

**Keepalive.** Proxies drop WebSockets idle for ~60 s. The drone socket is never idle
(agent heartbeats at `HEARTBEAT_HZ`, echoed by the relay); uvicorn sends protocol
pings every 20 s; and the relay sends `{"type":"ping","ts":…}` data frames to every
operator socket every `RELAY_PING_INTERVAL_S`, which the browser client ignores.

**Caveats.**
- **Sleep:** free Spaces sleep after ~48 h without traffic and cold-start on the next
  HTTP request (tens of seconds); WebSocket clients just reconnect with backoff. Don't
  rely on open WebSockets counting as activity: ping `/health` from a cron or uptime
  monitor (e.g. every 6 h), or upgrade the Space hardware (paid Spaces can disable sleep).
  A restart drops all sockets and the in-memory control lock; operators re-acquire.
- **No TURN:** coturn needs UDP/TCP 3478 ingress, which HF does not provide. With no
  `TURN_HOST`, `/turn-credentials` returns public STUN (`stun:stun.l.google.com:19302`)
  so WebRTC video works only when a direct/STUN path exists between browser and
  Jetson (fails behind symmetric NAT/CGNAT such as many LTE links). Telemetry and
  commands go over the WebSocket and are unaffected. For reliable video, point
  `TURN_HOST`/`TURN_SECRET` at a coturn on a VM.
- Only one replica: all drones and operators must hit the same Space.

### Agent (Jetson Orin Nano)
- `/etc/systemd/system/axalon-drone-agent.service` with `DRONE_ID`, `DRONE_TOKEN`,
  `RELAY_WS_URL=wss://relay.axalonsystems.com`, `MAVLINK_URL` pointing at the real
  Cube (e.g. `serial:/dev/ttyTHS1:921600`). `Restart=always`.

## Phase 2 — commands over SITL

Agent gains command handling + a deadman (RTL on relay-link loss). New agent env:
`MIN_ALT_M=5 MAX_ALT_M=120 HEARTBEAT_HZ=2 DEADMAN_TIMEOUT_S=5`.

Run the command e2e (with SITL + relay + agent up):
```bash
RUN_SITL_E2E=1 RELAY_WS_URL=ws://127.0.0.1:8800 OPS_TOKEN=otok DRONE_ID=sitl-01 \
  python -m pytest drone/tests/test_e2e_commands_sitl.py -v
```
Watch the SITL console: the vehicle should arm. Try TAKEOFF (`{"alt":40}`), then RTL.

## Phase 3 — video (Jetson GStreamer + relay coturn)

### Jetson packages (NOT pip)
```bash
sudo apt-get install -y \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-nice \
  python3-gi gir1.2-gst-plugins-bad-1.0
# webrtcbin lives in gstreamer1.0-plugins-bad; nvv4l2h264enc ships with JetPack.
```

### Agent video env
`VIDEO_ENABLED=1 WEBCAM_DEVICE=/dev/video0 THERMAL_DEVICE=/dev/video1 VIDEO_BITRATE_BPS=4000000`
For a no-camera demo: `VIDEO_TEST_PATTERN=1`.

### coturn on the Oracle A1 VM
```bash
sudo apt-get install -y coturn
sudo tee /etc/turnserver.conf >/dev/null <<'EOF'
listening-port=3478
fingerprint
use-auth-secret
static-auth-secret=CHANGE_ME_LONG_RANDOM
realm=relay.axalonsystems.com
total-quota=100
no-tls
no-dtls
EOF
sudo systemctl enable --now coturn
```

Open UDP/TCP 3478 (and the relay port) in the Oracle security list + the VM firewall.

Relay env must match coturn:
`TURN_HOST=relay.axalonsystems.com TURN_SECRET=CHANGE_ME_LONG_RANDOM`
(same value as `static-auth-secret`). Browser fetches creds from
`GET /turn-credentials`; the agent uses the same endpoint or its own env.

For production TLS, terminate `turns:` via Cloudflare Spectrum or a cert on coturn
(`cert`/`pkey` + remove `no-tls`/`no-dtls`). Phase 3 ships plain STUN/TURN; harden
in the Phase 3.1 pass.

## Phase 6 — real hardware bring-up

### Wiring & serial
- Connect the Cube's TELEM2 (or a spare UART) to the Jetson UART (e.g. `/dev/ttyTHS1`)
  or via USB (`/dev/ttyACM0`). Set the Cube's `SERIALx_PROTOCOL=2` (MAVLink2),
  `SERIALx_BAUD=921`.
- Agent env for hardware:
  `MAVLINK_URL=serial:/dev/ttyTHS1:921600` (replace the SITL `udpin:` URL).

### udev (stable device name)
```bash
# /etc/udev/rules.d/99-axalon.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", SYMLINK+="cube"   # example Cube VID
```
Then use `MAVLINK_URL=serial:/dev/cube:921600`.

### ArduPilot pre-flight params (set once, via Mission Planner / MAVProxy)
- `FENCE_ENABLE=1`, `FENCE_ALT_MAX`, `FENCE_RADIUS` — geofence is the hard boundary.
- `FS_GCS_ENABLE` + a sensible `FS_OPTIONS` so the autopilot also fails safe if it
  loses the companion link (defense in depth alongside the agent deadman).
- Battery failsafe (`BATT_LOW_VOLT`, `BATT_FS_LOW_ACT=2` RTL).
- Calibrate: accel, compass, RC, ESC — standard ArduCopter first-flight checklist.

### systemd on the Jetson
Reuse the `axalon-drone-agent.service` from Phase 1 with the hardware env:
`MAVLINK_URL=serial:/dev/cube:921600`, `VIDEO_ENABLED=1`, `RECORDING_ENABLED=1`,
`CAPTURE_DIR=/data/captures`, `PARK_ID=<park>`, `PLATFORM_API_URL=<HF backend>`,
`PLATFORM_TOKEN=<token>`. `Restart=always`.

> The capture handoff POSTs a ZIP of `CAPTURE_DIR` (frames + per-frame GPS sidecars)
> to the platform's `POST /batch` (multipart: `images` ZIP + `park_id` + `altitude_m`,
> `Authorization: Bearer PLATFORM_TOKEN`). `PLATFORM_TOKEN` must equal the backend's
> `AXALON_API_KEY`.

### First-flight safety checklist
1. Props OFF: confirm telemetry on `/platform` Live Ops, confirm ARM/DISARM acks.
2. Props OFF: confirm RTL/LAND mode changes reflect in the HUD.
3. Tethered/low hover: confirm GREEN tier on-site, manual pad translates + hovers on release.
4. Confirm geofence + battery failsafe trigger as configured.
5. Full mission: upload from planner, fly AUTO, watch telemetry + video, land →
   confirm a batch job appears in the platform.
