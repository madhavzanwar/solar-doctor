#!/usr/bin/env bash
# HISTORICAL — DEAD INFRASTRUCTURE, DO NOT RUN. The Azure subscription is disabled;
# production is Vercel -> HF Space parakh20/axalon-api. See deploy/azure/README.md
# and docs/DEPLOYMENT.md.
# Usage: PYTHONSAFEPATH=1 bash deploy/azure/01-create-infra.sh
set -euo pipefail

SUB="4374791b-cc03-474a-8237-bddf2f425ce4"
RG="axalon-rg"
LOC="southeastasia"
VM="axalon-vm"
PG="axalon-pg"
PG_USER="axalon"
PG_DB="axalon"
SSH_KEY="$HOME/.ssh/axalon_azure"

az account set --subscription "$SUB"
echo "[1] Subscription set"

az group create --name "$RG" --location "$LOC" --output none
echo "[2] Resource group created"

az network vnet create --resource-group "$RG" --name axalon-vnet \
  --address-prefix 10.0.0.0/16 --subnet-name axalon-subnet \
  --subnet-prefix 10.0.1.0/24 --output none

az network nsg create --resource-group "$RG" --name axalon-nsg --output none
for PORT in 22 8000 80 443; do
  az network nsg rule create --resource-group "$RG" --nsg-name axalon-nsg \
    --name "Allow$PORT" --priority "$((100 + PORT / 10))" \
    --protocol Tcp --direction Inbound --access Allow \
    --source-address-prefixes '*' --destination-port-ranges "$PORT" --output none
done
echo "[3] VNet + NSG created"

az network public-ip create --resource-group "$RG" --name axalon-ip \
  --allocation-method Static --sku Standard --output none
VM_IP=$(az network public-ip show --resource-group "$RG" --name axalon-ip \
  --query ipAddress --output tsv)
echo "[4] Static IP: $VM_IP"

az network nic create --resource-group "$RG" --name axalon-nic \
  --vnet-name axalon-vnet --subnet axalon-subnet \
  --network-security-group axalon-nsg --public-ip-address axalon-ip --output none

[ -f "$SSH_KEY" ] || ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "axalon-azure"
echo "[5] SSH key: $SSH_KEY"

az vm create --resource-group "$RG" --name "$VM" \
  --size Standard_B2ats_v2 \
  --image Canonical:ubuntu-24_04-lts:server-arm64:latest \
  --nics axalon-nic --admin-username ubuntu \
  --ssh-key-values "${SSH_KEY}.pub" \
  --os-disk-size-gb 30 --storage-sku StandardSSD_LRS --output none
echo "[6] VM created (B2ats v2, Ubuntu 24.04 ARM64)"

PG_PW=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 20)
az postgres flexible-server create \
  --resource-group "$RG" --name "$PG" --location "$LOC" \
  --admin-user "$PG_USER" --admin-password "$PG_PW" \
  --sku-name Standard_B1ms --tier Burstable --version 16 \
  --storage-size 32 --database-name "$PG_DB" \
  --public-access 0.0.0.0 --output none
PG_HOST="${PG}.postgres.database.azure.com"
az postgres flexible-server firewall-rule create \
  --resource-group "$RG" --name "$PG" --rule-name axalon-vm \
  --start-ip-address "$VM_IP" --end-ip-address "$VM_IP" --output none
echo "[7] PostgreSQL created: $PG_HOST"

SA="axalonstorage$(openssl rand -hex 3)"
az storage account create --resource-group "$RG" --name "$SA" \
  --location "$LOC" --sku Standard_LRS --kind StorageV2 \
  --access-tier Hot --allow-blob-public-access false --output none
SA_CONN=$(az storage account show-connection-string \
  --resource-group "$RG" --name "$SA" --query connectionString --output tsv)
az storage container create --name track-files \
  --connection-string "$SA_CONN" --output none
echo "[8] Storage: $SA / track-files"

API_KEY=$(openssl rand -hex 32)

cat > deploy/azure/.env.vm <<EOF
AXALON_DB_URL=postgresql+psycopg2://${PG_USER}:${PG_PW}@${PG_HOST}:5432/${PG_DB}?sslmode=require
AXALON_API_KEY=${API_KEY}
AXALON_OUTPUT_DIR=/home/ubuntu/axalon-data/output
PYTHONSAFEPATH=1
AZURE_STORAGE_CONNECTION_STRING=${SA_CONN}
AZURE_TRACK_CONTAINER=track-files
# Fill these in from your existing Supabase project:
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
AXALON_TRACK_BUCKET=track-files
EOF

cat > deploy/azure/.infra-state <<EOF
VM_IP=${VM_IP}
PG_HOST=${PG_HOST}
PG_PW=${PG_PW}
SA=${SA}
SA_CONN=${SA_CONN}
SSH_KEY=${SSH_KEY}
API_KEY=${API_KEY}
EOF

echo ""
echo "=============================="
echo " VM IP  : $VM_IP"
echo " SSH    : ssh -i $SSH_KEY ubuntu@$VM_IP"
echo " PG     : $PG_HOST  pw=$PG_PW"
echo " API key: $API_KEY"
echo "=============================="
echo "Fill SUPABASE_URL + SUPABASE_SERVICE_KEY in deploy/azure/.env.vm"
echo "Then run: PYTHONSAFEPATH=1 bash deploy/azure/02-bootstrap.sh"
