# Seed plan (`make seed`, `scripts/seed.py`, `scripts/import_pvdaq.py`)

Status: design only. Neither script is written because the `plants`/`telemetry`/`alerts` tables arrive with
sd-physics' Alembic revision `0011_*`; the exact columns are not guessed here. Implement once that merges, using the
ORM models (not raw SQL) and `solardoctor.core.auth.create_user`.

## 1. Users
- 1 admin, 1 technician via `create_user` (idempotent: skip if the email exists). Emails/passwords come from
  `SOLARDOCTOR_SEED_ADMIN_EMAIL/PASSWORD` and `SOLARDOCTOR_SEED_TECH_EMAIL/PASSWORD`; when unset, generate random
  passwords and print them once. No default password is committed.
- The technician gets project membership for the seeded plants' projects, and seeded faults/work orders are
  assigned to the technician's email (that is how work-order scoping matches, see `API_AUTH.md`).

## 2. Plants (all `source="SIMULATED"`)
| Plant | Capacity | Location |
|---|---|---|
| Bhadla Block C | 50 MW | Bhadla, Rajasthan |
| PCCoE Rooftop | 120 kW | Pune, Maharashtra |
| Pavagada Unit 4 | 25 MW | Pavagada, Karnataka |

Latitude/longitude/tz (`Asia/Kolkata`), tilt, azimuth, module and inverter counts, temperature coefficient and tariff are
filled from the `plants` model fields and documented in the script with their basis (site coordinates from public
maps; tilt ~ latitude; azimuth 180). Anything not sourced is labelled an assumption in a comment.
Each plant is linked to an Axalon `Park` per the 1:1 link added by sd-physics.

## 3. Irradiance input
1. Fetch NASA POWER hourly (`ALLSKY_SFC_SW_DWN`, `ALLSKY_SFC_SW_DIFF`/`DNI` where available, `T2M`, `WS10M`) for the last
   30 complete days at each coordinate. Cache as CSV under `data/cache/nasa_power_<plant>_<start>_<end>.csv`
   (gitignored). Re-runs read the cache.
2. Offline fallback (network blocked or API error): pvlib clear-sky (Ineichen, Linke turbidity from pvlib's
   lookup) multiplied by a **synthetic cloud model**: a seeded AR(1) daily clearness index plus intra-day
   noise. Every row produced this way carries `irradiance_source="SYNTHETIC_CLEARSKY"`, the seed prints a
   warning, and the UI badge stays `SIMULATED`. The fallback is never described as measured data.

## 4. Telemetry generation (30 days, 15-min steps)
- pvlib `ModelChain`/PVWatts: transposition (Perez) to POA, cell temperature (SAPM/Faiman), DC to AC with
  inverter clipping at AC rating. Fixed RNG seed (`--seed`, default 42) for reproducibility.
- Add measurement noise (~1 % multiplicative) and nighttime zeros.
- Injected, labelled events (also written to a `seed_manifest.json` so tests can assert detection):
  - **Soiling ramps:** per-plant linear loss 0.1-0.3 %/day, reset by a "cleaning" or by a rain day (>2 mm).
  - **String fault (one plant):** one string at 0 current for a fixed window, visible as a deficit on one inverter/string.
  - **Cloudy spell:** 3 consecutive days of reduced clearness index (physics expected power still computed
    from the true irradiance, so this must NOT raise a loss alert; it is the false-positive control).
- All rows `source="SIMULATED"`.

## 5. Alerts and diagnoses
Run the physics module's own anomaly detector over the generated series (do not hand-write alerts): the soiling
ramps and the string fault should produce alerts with severity from the module; the cloudy spell should produce
none. Seed 1-2 resolved alerts for history. Each alert and diagnosis row also carries `source="SIMULATED"`.

## 6. `scripts/import_pvdaq.py`
- Uses `pvdaq_access` (https://github.com/NatLabRockies/pvdaq_access) to download PVDAQ system 9068 (used in
  pvlib's gallery) for a bounded date range; metadata (lat/lon, tilt, azimuth, capacity) from PVDAQ's system
  metadata, not invented.
- Creates a fourth plant with `source="PVDAQ"`, telemetry rows with `source="PVDAQ"`, cached under
  `data/cache/pvdaq_9068_*.csv`. Network failure: exit non-zero with a clear message; no fake fallback.
- Licence: check the dataset terms and add the attribution to `THIRD_PARTY_NOTICES.md` / the UI before shipping.

## 7. Behaviour and tests
- `make seed` is idempotent (`--reset` drops only rows with `source="SIMULATED"`; never touches PVDAQ or user data).
- Refuses to run when `SOLARDOCTOR_ENV=production` unless `--force`.
- Tests: second run adds no duplicates; all rows labelled; injected soiling slope recovered within tolerance;
  AC power never above the AC rating; zero at night; technician can log in and sees only its assigned work orders.
