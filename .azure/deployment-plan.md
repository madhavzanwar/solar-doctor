# Axalon Platform — Azure Deployment Plan

**Status**: `Complete` (migrated 2026-06-15)
**Created**: 2026-06-15
**Subscription ID**: `4374791b-cc03-474a-8237-bddf2f425ce4`
**Plan**: Azure for Students (Owner)

---

## 1. Mode

**MIGRATE** — Moving existing FastAPI + YOLO11m backend from Oracle Always Free ARM VM
to Azure, keeping Vercel frontend unchanged.

Current stack:
```
Vercel (axalonsystems.com/platform) → Oracle ARM VM (FastAPI + YOLO, 2 OCPU / 12 GB) → Supabase Postgres
```

Target stack:
```
Vercel (axalonsystems.com/platform) → Azure VM B2ats v2 (FastAPI + YOLO, 2 vCPU / 4 GB) → Azure PostgreSQL B1MS
```

---

## 2. Requirements

| Requirement | Detail |
|-------------|--------|
| Runtime | Python 3.12, FastAPI + Uvicorn, YOLO11m (CPU inference) |
| Database | PostgreSQL (SQLAlchemy + psycopg2) |
| File storage | Azure Blob Storage (for /track uploads) |
| Auth | Bearer token (AXALON_API_KEY env var) |
| Frontend | Vercel-hosted Next.js — unchanged |
| Budget | Free tier only (Azure for Students) |
| Availability | 24/7 (750 h/month free covers full month) |

---

## 3. Architecture

### Compute: Azure VM — Standard_B2ats_v2

- ARM64 (Ampere Altra), 2 vCPU, 4 GiB RAM — free 750 h/month
- B1s rejected: 1 GiB RAM insufficient for PyTorch + YOLO11m (~3 GB peak)
- OS: Ubuntu 22.04 LTS (ARM64)
- Disk: 30 GB Standard SSD
- Public IP: Static

### Database: Azure PostgreSQL Flexible Server — B1MS

- 1 vCPU, 2 GiB RAM — free 750 h/month + 32 GB storage
- PostgreSQL 16, password auth
- Public access with firewall rule for VM IP

### Storage: Azure Blob Storage (Hot LRS)

- 5 GB free — replaces Supabase Storage for /track uploads
- Container: track-files (private)

### Region: centralindia (Mumbai)

Lowest latency from IIT Bombay.

---

## 4. Recipe: AZCLI

Direct az CLI commands. No azd overhead for a simple VM + managed DB migration.

Steps:
1. Create resource group `axalon-rg` in `centralindia`
2. Create VNet + subnet + NSG (ports 22, 8000, 80, 443)
3. Create VM (B2ats v2, Ubuntu 22.04 ARM64, generate SSH keypair)
4. Create PostgreSQL Flexible Server (B1MS)
5. Create Storage Account + Blob container `track-files`
6. Bootstrap VM: Python, git, venv, clone repo, .env, systemd

---

## 5. Resources to Create

| Resource | Type | Free Tier |
|----------|------|-----------|
| axalon-rg | Resource Group | Free |
| axalon-vnet | Virtual Network | Free |
| axalon-nsg | Network Security Group | Free |
| axalon-ip | Public IP Static | 1,500 h/mo free |
| axalon-vm | VM Standard_B2ats_v2 | 750 h/mo free |
| axalon-pg | PostgreSQL Flexible B1MS | 750 h/mo free |
| axalonstorage | Storage Account Hot LRS | 5 GB free |

---

## 7. Validation Proof

_To be populated by azure-validate_

---

## 8. Checklist

- [x] Resource group created (southeastasia — centralindia blocked by IIT Bombay tenant policy)
- [x] VNet + NSG created
- [x] VM created (Standard_B2ats_v2, Ubuntu 24.04 x64 — NOT ARM64)
- [x] SSH key generated: ~/.ssh/axalon_azure
- [x] PostgreSQL Flexible Server created (B1MS, PG16, 7 migrations applied)
- [x] Storage Account + container created (axalonstorageeb0c19 / track-files)
- [x] VM bootstrapped (Python, git, venv, matplotlib, azure-storage-blob)
- [x] .env configured on VM (DB, API key, Supabase creds, blob storage conn string)
- [x] alembic migrations run against Azure PostgreSQL (0001→0007)
- [x] systemd service installed + enabled (axalon.api.app:app — NOT platform.api.app:app)
- [x] API health check passes: {"status":"ok","model":"YOLO11m","db":"ok"}
- [x] NEXT_PUBLIC_AXALON_API_URL updated in Vercel → http://104.215.194.187:8000
- [x] /platform tested end-to-end (HTTP 200)
- [x] /track password set (axalon1234 in Azure PG app_config)

**Open items post-migration:**
- [ ] Wire /track/files uploads to Azure Blob (currently local disk — ephemeral)
- [ ] Add HTTPS to Azure VM (currently HTTP — Cloudflare tunnel or Caddy)
- [ ] Update GitHub Actions db-migrate.yml to point at Azure PG (currently Supabase)
