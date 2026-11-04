# How to Use Axalon Solar Inspection Platform

Axalon has three operator entry points:

- `./run.sh platform` — Next.js platform UI on :3000
- `./run.sh api` — FastAPI server on :8000
- `./run.sh all` — API + platform UI together
- `python main.py ...` — CLI workflows
- `./run.sh doctor` — quick environment check
- `./run.sh setup` — install local dependencies

`run.sh` is the easiest local workflow because it checks dependencies, avoids the local `platform/` naming trap, and writes logs to `logs/`.

## Option 1: Platform UI (recommended)

```bash
./run.sh doctor
./run.sh all
```

Open `http://localhost:3000/platform`.

Daily operator flow:

1. Enter a park ID and a local flight folder path
2. Review the mission preflight summary
3. Run the batch inspection
4. Inspect the park map and download JSON, Excel, GeoJSON, and PDF reports

Notes:

- The UI calls the FastAPI backend on `:8000` for inference.
- PDF download depends on WeasyPrint system libraries from `docs/INSTALLATION.md`.

## Option 2: CLI

```bash
# Inspect one thermal + RGB pair
python main.py inspect \
  --thermal /path/to/thermal_001.jpg \
  --rgb /path/to/rgb_001.jpg \
  --park-id PARK_01 \
  --altitude 45

# Inspect an entire mission folder
python main.py batch \
  --folder /path/to/flight_mission/ \
  --park-id PARK_01 \
  --altitude 45

# Start the REST API
python main.py api --host 0.0.0.0 --port 8000
```

CLI batch writes reports to `output/{batch_id}/`.

## Option 3: REST API directly

```bash
./run.sh api
```

Open API docs at `http://localhost:8000/docs`.

Common API flow:

1. `POST /batch` with a ZIP archive of a mission folder
2. Poll `GET /status/{job_id}`
3. Download `pdf`, `excel`, `json`, or `geojson` from `GET /report/{job_id}`

Example:

```bash
curl -X POST http://localhost:8000/batch \
  -F "images=@/absolute/path/to/mission.zip" \
  -F "park_id=PARK_01" \
  -F "altitude_m=45"

curl http://localhost:8000/status/batch-1234abcd

curl "http://localhost:8000/report/batch-1234abcd?format=pdf" -o inspection_report.pdf
```

## Output Files

Batch jobs write to `output/{batch_id}/`:

- `inspection_report.json`
- `inspection_report.xlsx`
- `park_anomaly_map.geojson`
- `inspection_report.pdf` if PDF dependencies are installed

Single-image CLI runs write to `output/{job_id}/` and include JSON plus annotated imagery.
