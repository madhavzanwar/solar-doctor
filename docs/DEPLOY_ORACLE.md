> **HISTORICAL — NOT THE LIVE DEPLOYMENT. Do not follow this for production.**
> Production never ran on Oracle Cloud; this was a plan that was never adopted.
> The actual path is Vercel `axalon-systems` → Hugging Face Space
> `parakh20/axalon-api` → Postgres. See [`DEPLOYMENT.md`](DEPLOYMENT.md).
> Kept only for reference.

# Deploying the Axalon Backend on Oracle Cloud (Always Free)

This runs the FastAPI + YOLO11m backend 24/7 on a free Oracle ARM VM, backed by
Supabase Postgres, reachable by the Vercel-hosted `/platform` frontend.

```
Vercel (axalonsystems.com/platform)  →  Oracle ARM VM (FastAPI + YOLO)  →  Supabase Postgres
```

---

## 0. Stay on Always Free

- Shape: **VM.Standard.A1.Flex (Ampere ARM)** — Always Free up to **4 OCPU / 24 GB RAM**.
  Choose **2 OCPU / 12 GB** (enough) or up to 4/24.
- **Do NOT** pick `VM.Standard.E2.1.Micro` (AMD, 1 GB RAM) — too small for PyTorch.
- Image: **Ubuntu 22.04 (aarch64)**.
- Boot volume: default ~50 GB (Always Free allows up to 200 GB total).
- A credit card is needed for verification; Always Free shapes are never billed.
- If you see "out of host capacity," retry or switch Availability Domain/region.

---

## 1. Create the VM

1. OCI Console → **Compute → Instances → Create instance**
2. Image & shape: Ubuntu 22.04, shape **VM.Standard.A1.Flex**, set 2 OCPU / 12 GB
3. Add your **SSH public key** (or let OCI generate one and download it)
4. Create. Note the **public IP**.

## 2. Open the firewall (two layers)

**a) OCI Security List / NSG** (Console → VCN → Security Lists):
- Add **Ingress** rule: source `0.0.0.0/0`, TCP, dest port **8000** (API) — and **443/80** if you terminate TLS here.

**b) On the VM** (Ubuntu's iptables is restrictive by default):
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install dependencies

```bash
ssh ubuntu@<PUBLIC_IP>
sudo apt update && sudo apt install -y python3-venv python3-pip git libgl1 libglib2.0-0
# libgl1/libglib2.0-0 are needed by OpenCV (cv2)

git clone https://github.com/Parakh20/AxalonSystems.git
cd AxalonSystems
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements_platform.txt
pip install -e .
pip install psycopg2-binary           # Postgres driver for Supabase
```

> ARM note: PyTorch/Ultralytics install CPU `aarch64` wheels automatically. First
> `import torch` may take a moment. No CUDA on this VM — CPU inference is fine.

## 4. Configure environment

```bash
cp .env.example .env
nano .env
```
Set at minimum:
- `AXALON_DB_URL=postgresql+psycopg2://postgres:PW@db.REF.supabase.co:5432/postgres`
- `AXALON_API_KEY=<long-random-secret>`
- `AXALON_USE_ENGINE=false`

Create the tables in Supabase (once):
```bash
set -a && source .env && set +a
PYTHONSAFEPATH=1 alembic upgrade head
```

> `PYTHONSAFEPATH=1` is required: the repo's `platform/` package otherwise shadows
> Python's stdlib `platform` module (alembic adds the repo root to `sys.path`),
> which crashes SQLAlchemy with `module 'platform' has no attribute 'python_implementation'`.

## 5. Get the model weights onto the VM

`ml/checkpoints/best.pt` is tracked in git, so the clone already includes it.
Verify:
```bash
ls -lh ml/checkpoints/best.pt     # ~21 MB
```

## 6. Run it as a service (24/7, auto-restart)

```bash
sudo cp deploy/axalon-api.service /etc/systemd/system/axalon-api.service
# paths in the unit already assume /home/ubuntu/AxalonSystems and .venv — adjust if different
sudo systemctl daemon-reload
sudo systemctl enable --now axalon-api
systemctl status axalon-api
journalctl -u axalon-api -f        # live logs
```

Smoke test from your laptop:
```bash
curl http://<PUBLIC_IP>:8000/health
# {"status":"ok","model":"YOLO11m","db":"ok"}
```

## 7. Give it a real HTTPS address

The frontend is HTTPS, so the backend must be HTTPS too (browsers block HTTPS→HTTP).
Two options:

**Option A — Cloudflare Tunnel (no TLS setup, free):**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cf.deb
sudo dpkg -i cf.deb
cloudflared tunnel login
cloudflared tunnel create axalon-api
cloudflared tunnel route dns axalon-api api.axalonsystems.com
# config ~/.cloudflared/config.yml → service: http://localhost:8000, then:
sudo cloudflared service install
```
Backend is now at `https://api.axalonsystems.com`.

**Option B — Caddy reverse proxy (auto Let's Encrypt TLS):**
Point an `api.axalonsystems.com` A-record at the VM's public IP, then:
```bash
sudo apt install -y caddy
echo 'api.axalonsystems.com { reverse_proxy localhost:8000 }' | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

## 8. Point the frontend at it

In Vercel → Project → Settings → Environment Variables:
```
NEXT_PUBLIC_AXALON_API_URL = https://api.axalonsystems.com
```
Redeploy. Open `axalonsystems.com/platform`, enter the `AXALON_API_KEY` in the login
gate, and teammates anywhere can use it.

---

## Updating after code changes

```bash
ssh ubuntu@<PUBLIC_IP>
cd AxalonSystems && git pull
source .venv/bin/activate
pip install -r requirements_platform.txt   # if deps changed
PYTHONSAFEPATH=1 alembic upgrade head       # if migrations changed
sudo systemctl restart axalon-api
```

## Cost guardrails

- Everything above uses **Always Free** shapes only → $0/month.
- Watch Supabase free limits: 500 MB DB, 1 GB storage, 7-day idle auto-pause.
- Don't "upgrade" the OCI account or add paid shapes.
