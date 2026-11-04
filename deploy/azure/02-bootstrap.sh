#!/usr/bin/env bash
# HISTORICAL — DEAD INFRASTRUCTURE, DO NOT RUN. The Azure subscription is disabled;
# production is Vercel -> HF Space parakh20/axalon-api. See deploy/azure/README.md
# and docs/DEPLOYMENT.md.
# Bootstrap Azure VM: install deps, clone repo, configure systemd service.
# Usage: PYTHONSAFEPATH=1 bash deploy/azure/02-bootstrap.sh
set -euo pipefail

source deploy/azure/.infra-state

echo "=== Bootstrapping $VM_IP ==="

echo "Waiting for SSH..."
until ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    ubuntu@"$VM_IP" "echo ok" 2>/dev/null; do sleep 5; done
echo "SSH ready."

scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  deploy/azure/.env.vm ubuntu@"$VM_IP":/home/ubuntu/.env.axalon

scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  deploy/azure/axalon-api.service ubuntu@"$VM_IP":/home/ubuntu/axalon-api.service

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$VM_IP" bash -s <<'REMOTE'
set -euo pipefail

sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip git libgl1 libglib2.0-0 gcc g++

# 2 GB swap — YOLO peaks ~3.5 GB, VM has 4 GB RAM
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  echo "Swap 2 GB enabled"
fi

if [ -d /home/ubuntu/AxalonSystems/.git ]; then
  cd /home/ubuntu/AxalonSystems && git pull
else
  git clone https://github.com/Parakh20/AxalonSystems.git /home/ubuntu/AxalonSystems
fi

cd /home/ubuntu/AxalonSystems
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements_platform.txt -q
pip install psycopg2-binary azure-storage-blob -q
pip install -e . -q

cp /home/ubuntu/.env.axalon .env
mkdir -p /home/ubuntu/axalon-data/output

PYTHONSAFEPATH=1 alembic upgrade head

sudo cp /home/ubuntu/axalon-api.service /etc/systemd/system/axalon-api.service
sudo systemctl daemon-reload
sudo systemctl enable axalon-api
sudo systemctl restart axalon-api
sleep 3
sudo systemctl status axalon-api --no-pager
REMOTE

echo ""
sleep 5
curl -sf "http://${VM_IP}:8000/health" && echo "API is UP ✓" \
  || echo "Not ready yet — check: ssh -i $SSH_KEY ubuntu@$VM_IP 'journalctl -u axalon-api -n 50'"

echo ""
echo "Set in Vercel dashboard → axalonsystems project → Environment Variables:"
echo "  NEXT_PUBLIC_AXALON_API_URL = http://${VM_IP}:8000"
