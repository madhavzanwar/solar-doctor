> **HISTORICAL — DEAD INFRASTRUCTURE. Do not run these scripts.**
> The Azure deployment (VM `axalon-vm` + Azure PostgreSQL) went down when its
> subscription was disabled, and the resources cannot be started.
> Production is now Vercel `axalon-systems` → Hugging Face Space
> `parakh20/axalon-api` → Postgres. See [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md).

# deploy/azure (historical)

These files provisioned and bootstrapped the old Azure backend. They are kept for reference only.

| File | What it did |
|---|---|
| `01-create-infra.sh` | Created the resource group, VNet, VM, and Azure PostgreSQL server with `az` |
| `02-bootstrap.sh` | Used SSH to install dependencies, clone the repo, and install the systemd unit on the VM |
| `axalon-api.service` | systemd unit that ran uvicorn on port 8000 |
