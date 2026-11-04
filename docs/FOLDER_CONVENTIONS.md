# Skydroid C13 Folder Conventions

The ingestion engine auto-detects two folder layouts:

## Layout A — Subdirectory

```
flight_mission/
├── thermal/        ← thermal_001.jpg, thermal_002.jpg ...
└── rgb/            ← rgb_001.jpg, rgb_002.jpg ...
```

Pairing: matched by numeric suffix (thermal_001 ↔ rgb_001).

## Layout B — Flat folder

```
flight_mission/
├── IR_001.jpg, IR_002.jpg ...      ← thermal (IR prefix)
└── RGB_001.jpg, RGB_002.jpg ...    ← RGB (RGB prefix)
```

Pairing: matched by numeric suffix (IR_001 ↔ RGB_001).

## Optional mission metadata

Create `mission_metadata.json` in the flight folder to override defaults:

```json
{
  "altitude_m": 45.0,
  "park_id": "PARK_01",
  "operator": "Axalon Field Team",
  "camera_model": "Skydroid C13"
}
```

## Notes

- Thermal images must be JPEG, PNG, or TIFF
- RGB images are optional — if absent, panel IDs default to `R?-C?`
- File pairing is by numeric suffix only — name prefixes don't matter
- Up to 5,000 image pairs supported in a single batch
