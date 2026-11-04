# Axalon Systems — Hardware Integration Guide
## IEC TS 62446-3:2017 Compliant Drone-Based Thermal Inspection

> **Standard:** IEC TS 62446-3:2017 — Photovoltaic (PV) systems: Outdoor infrared thermography  
> **Version:** 1.0 | **Date:** 2026-05-12  
> **Status:** Engineering Specification

---

## Table of Contents

1. [Overview & Inspection Levels](#1-overview--inspection-levels)
2. [IR Camera — Requirements & Selection](#2-ir-camera--requirements--selection)
3. [RGB / Visual Camera](#3-rgb--visual-camera)
4. [Drone Platform Requirements](#4-drone-platform-requirements)
5. [Environmental Monitoring Equipment](#5-environmental-monitoring-equipment)
6. [Data Acquisition Techniques (IEC §5.4)](#6-data-acquisition-techniques-iec-54)
7. [Pre-Flight Checklist & Environmental Go/No-Go](#7-pre-flight-checklist--environmental-gono-go)
8. [Data Format & File Handoff to Axalon Platform](#8-data-format--file-handoff-to-axalon-platform)
9. [Software Integration Points](#9-software-integration-points)
10. [Calibration & Maintenance Schedule](#10-calibration--maintenance-schedule)
11. [Personnel Qualification (IEC Annex B)](#11-personnel-qualification-iec-annex-b)
12. [Recommended Hardware Stack](#12-recommended-hardware-stack)

---

## 1. Overview & Inspection Levels

IEC 62446-3 defines **two inspection levels** with different hardware and operator requirements:

| Level | Use Case | Absolute Temp? | Personnel | Axalon Support |
|-------|----------|---------------|-----------|----------------|
| **Simplified** | Commissioning, routine screening of whole array | No — patterns only | ISO 9712 Level 1 equivalent | Full — AI handles pattern classification |
| **Detailed** | Periodic inspection, root-cause, underperforming plants | Yes — absolute ΔT required | ISO 9712 Level 2 equivalent | Full — ΔT normalization via `normalize_delta_t()` |

> Drone-based inspection is **always classified as Simplified** for the array survey phase. Detailed inspection is then performed on flagged modules on-ground (IEC §5.4.2).

---

## 2. IR Camera — Requirements & Selection

### 2.1 Minimum Specifications (IEC §4.2, Table 1)

| Parameter | IEC Minimum | Target Spec for Axalon |
|-----------|-------------|------------------------|
| Spectral range | 8–14 µm (LW) **or** 2–5 µm (MW, BOS only) | **8–14 µm (LW-IR)** — MW cannot image through PV glass |
| Object temp range | −20 °C to +120 °C | −20 °C to +150 °C recommended |
| NETD (thermal sensitivity) | ≤ 0.1 K at 30 °C | ≤ 0.05 K preferred |
| Geometric resolution | ≤ 30 mm/pixel on module edge | See §2.2 below — altitude-dependent |
| Absolute accuracy | < ±2 K | < ±2 K (traceable calibration required) |
| Adjustable emissivity | Required | ε = 0.85 default (clean glass, perpendicular) |
| Adjustable T_refl | Required | Set from ground measurement each flight |
| Calibration interval | ≤ 2 years | Log calibration certificate per flight |
| Storage format | Full radiometric (not just JPEG) | RJPEG or TIFF with embedded radiometric data |
| Recommended resolution | ≥ 320 × 240 px | **640 × 512 px** for drone-based standoff |

> **MW-IR (2–5 µm) cameras must NOT be used on PV modules** — glass is transparent in the 3 µm band, causing measurement errors. MW is valid only for BOS components (fuses, junction boxes).

### 2.2 Altitude & Geometric Resolution Calculation (IEC Annex A.1)

The standard requires **≥ 5 × 5 pixels per 6" (152 mm) cell**, i.e. ≤ 30 mm per pixel on the module surface.

```
pixel_size_on_module = IFOV_mrad × distance_m / 1000

Required: pixel_size_on_module ≤ 30 mm
```

**Maximum flying altitude for common camera/lens combinations:**

| Camera Resolution | IFOV (mrad) | Max Altitude (AGL) | Cell Coverage |
|-------------------|------------|-------------------|---------------|
| 320 × 240, 9 mm lens | 3.0 | **10 m** | 5 × 5 px per 6" cell |
| 640 × 512, 13 mm lens | 1.7 | **17 m** | 5 × 5 px per 6" cell |
| 640 × 512, 25 mm lens | 0.9 | **33 m** | 5 × 5 px per 6" cell |
| 1024 × 768, 25 mm lens | 0.6 | **50 m** | 5 × 5 px per 6" cell |

> **Axalon default training altitude:** The YOLOv8s model was trained on 640 × 640 px crops from ≈ 24 × 40 px source images. For best detection confidence, fly at the altitude that produces panel images of approximately this size in the final cropped frame.

### 2.3 Emissivity Configuration (IEC §5.4.3)

Configure the camera before each flight. Do **not** leave at factory default.

| Surface Condition | ε Setting |
|------------------|-----------|
| Clean glass, angle < 5° from nadir | 0.85 |
| Textured / soiled glass | 0.90 |
| Viewing angle 45° from surface | 0.80 |
| Viewing angle 30° from surface | 0.75 |
| Oxidised aluminium frame | 0.50–0.70 |
| Unoxidised/polished metal (BOS) | 0.10–0.30 — **not measurable accurately** |

**Axalon platform integration:** The `irradiance_wm2`, `emissivity`, and `t_refl_c` metadata fields in `site_meta` flow directly into the PDF report's environmental conditions section (IEC §8f). Supply these from the ground sensor log.

### 2.4 Reflected Temperature (T_refl)

Measure once before the flight using the IR camera aimed at a diffuse reflector (crumpled aluminium foil) held parallel to the panel surface:

```
T_refl = mean temperature reading from crumpled foil target
```

Set this value in the camera firmware before imaging. Log it in `site_meta["t_refl_c"]`.

---

## 3. RGB / Visual Camera

### 3.1 Requirements (IEC §4.3)

| Requirement | IEC Spec | Axalon Minimum |
|-------------|----------|----------------|
| Resolution relative to IR | Significantly higher | **≥ 30× IR pixel count** (e.g., 12 MP for 640 × 512 IR) |
| Coverage | Same field of view as IR | Matched FoV, synchronized capture |
| Photo of every thermal abnormality | Required | Automatic — Axalon pairs RGB + thermal per image position |
| Mandatory photo requirement | Every **CoA 3** finding | Full-res RGB saved per detection in report |

> **One visual photo of every safety-relevant abnormality (CoA 3) is mandatory per IEC §4.3.** The Axalon pipeline satisfies this by archiving paired RGB frames for every detection above MEDIUM severity.

### 3.2 Camera Placement

- Separate photo camera and IR camera are **recommended** (not integrated into IR body)
- Matched pixel-accurate overlay requires **hardware trigger synchronization** (1-PPS signal or trigger cable) OR timestamp-based soft sync within ≤ 100 ms
- Axalon's `fusion.py` aligns thermal and RGB using GPS position + timestamp; hardware sync improves overlay quality but is not required for detection

---

## 4. Drone Platform Requirements

### 4.1 Core Requirements from IEC §5.4.2

| Requirement | IEC Clause | Specification |
|-------------|-----------|---------------|
| Moving speed limit | §5.4.2, Figure 1 | **≤ 3 m/s over panel rows** (bolometer smearing threshold) |
| Altitude stability | Annex A.1 | ± 0.5 m AGL variance to maintain pixel resolution |
| Gimbal stabilization | §5.4.1 | ≥ 3-axis, maintains nadir angle ± 5° |
| Viewing angle to module | §5.4.1, A.2 | **≥ 30° from module plane** (i.e., ≤ 60° from nadir for flat roof) |
| GPS tagging of images | §8i | Required — EXIF GPS in all thermal and RGB files |
| Date/time sync | §4.1 | All equipment clocked to same UTC source before flight |

### 4.2 Smearing Avoidance (IEC §5.4.2, Figure 1)

Bolometer-type IR sensors (standard in drone cameras) have a frame integration time that causes motion blur at high speed:

```
max_drone_speed = ifov_mrad × distance_m / (1000 × frame_integration_time_s)

Typical bolometer at 3 m altitude:
  smearing threshold ≈ 3 m/s (IEC §5.4.2)

Typical bolometer at 15 m altitude:
  smearing threshold ≈ 1.5 m/s (more conservative at standoff)
```

**Flight planning rule:** Set mission speed to 60% of the theoretical smearing threshold to maintain a safety margin:

| Altitude AGL | Max Recommended Speed |
|-------------|----------------------|
| 5–10 m | 2.0 m/s |
| 10–20 m | 1.5 m/s |
| 20–35 m | 1.2 m/s |

### 4.3 Viewing Angle — Emissivity and Reflection Management (IEC A.2)

The minimum angle between the IR camera and the PV module plane is **30°**. Below this, glass emissivity drops and reflections of heated objects (sky, buildings) dominate.

For ground-mounted panels tilted at angle θ:
```
Required camera tilt from nadir = 90° − 30° − θ
                                 = 60° − θ

Example: 20°-tilted panels → camera must be tilted ≥ 40° from nadir
         Horizontal panels (flat roof) → camera nadir (0°) is fine
```

Configure gimbal pitch in the flight planning software to comply.

### 4.4 GPS and EXIF Requirements

Every image (thermal and RGB) must contain:
- **GPS latitude, longitude** (WGS84, ≥ 6 decimal places)
- **GPS altitude** (AGL or AMSL, consistent within flight)
- **UTC timestamp** (synchronized to GPS time)
- **Relative altitude** (from takeoff point)
- **Gimbal pitch / yaw / roll** (for 3D reconstruction if orthomosaic is generated)

Axalon's `platform/core/geo.py` reads EXIF GPS tags to geo-locate each detection. Missing EXIF GPS degrades localization from GPS-anchored to grid-only mode.

---

## 5. Environmental Monitoring Equipment

### 5.1 Required Sensors (IEC §4.4, Table 2)

All sensors must be active and logging throughout the flight. Data must be merged with image metadata in the Axalon ingest step.

| Parameter | Equipment | IEC Accuracy | Axalon Field (`site_meta`) |
|-----------|-----------|-------------|---------------------------|
| **Irradiance** (in-plane of PV module) | Silicon cell pyranometer or calibrated reference cell | ± 5 % calibration | `irradiance_wm2` |
| **Ambient (air) temperature** | Shielded, aspirated temperature sensor (shielded from sun + wind) | ± 2 K | `air_temp_c` |
| **Wind speed** | Anemometer or Beaufort visual estimate | Estimation | `wind_speed_bft` |
| **Cloud coverage** | Photo camera (estimate okta) | Estimation | `cloud_coverage_okta` |
| **Soiling degree** | Photo camera (visual) | Estimation | *(noted in report remarks)* |
| **Module/string current** | DC clamp meter or string inverter reading | ± 2 % | *(used for ΔT normalization check)* |

### 5.2 Irradiance Sensor Placement

The pyranometer must be co-planar with the PV modules being inspected (tilted at the same angle and orientation). A horizontal sensor will under-read the actual in-plane irradiance for tilted arrays.

Minimum sampling interval: **1 sample per 30 seconds** during flight, timestamped to UTC.

### 5.3 Go / No-Go Environmental Thresholds (IEC §5.3, Table 3)

| Parameter | Minimum | Maximum | Go? |
|-----------|---------|---------|-----|
| In-plane irradiance | **600 W/m²** | — | Log value each flight |
| Operating current | **≥ 30% of Isc (STC)** | — | Check string current |
| Wind speed | — | **4 Bft (28 km/h)** | Abort if exceeded |
| Cumulus cloud coverage | — | **2 okta** | Delay if exceeded |
| Soiling | — | Low (homogeneous) | Clean first if heavy |

**After any irradiance change > 10% per minute**, wait **15 minutes** before resuming imaging to allow thermal steady state to re-establish.

---

## 6. Data Acquisition Techniques (IEC §5.4)

### 6.1 Simplified Inspection (Pattern-Based)

Used for whole-array drone survey. The Axalon YOLOv8s model operates in this mode.

- No absolute temperatures are determined
- Thermal **patterns** from IEC Annex C are the classification basis
- Axalon's `IEC_COA_MAP` assigns CoA 2 or CoA 3 from the detected class
- Flagged modules are marked for ground-level detailed inspection

**Flight pattern:** Parallel lawnmower rows, perpendicular to panel rows where possible. Overlap ≥ 20% between adjacent swaths for stitching.

### 6.2 Detailed Inspection (Absolute Temperature)

Performed on-ground or at low altitude on modules flagged by the drone survey.

Required measurement technique (IEC §7.2):

**a) Point abnormalities** (e.g., bypass diode hot spot):
```python
# Highest temperature in an area → use "maximum spot" tool in camera software
# Abnormality type: "point", exponent x = 1.5
delta_t_norm = normalize_delta_t(delta_t_measured, irradiance_wm2, "point")
```

**b) Extended area abnormalities** (e.g., full cell, substring, module):
```python
# Arithmetic mean temperature of polygon area → use polygon tool in camera software
# Annex D: polygon measurement is the reference method
# Abnormality type: "extended", exponent x = 1.0
delta_t_norm = normalize_delta_t(delta_t_measured, irradiance_wm2, "extended")
```

**ΔT Normalization formula** (IEC §7.4.1):
```
ΔT₂ = (G₂ / G₁)^x × ΔT₁

Where:
  ΔT₁ = measured temperature difference (hot component − adjacent reference) in K
  G₁  = actual irradiance at measurement time (W/m²)
  G₂  = 1000 W/m² (nominal reference)
  x   = 1.5 for point abnormalities (bypass diode, cell contact)
  x   = 1.0 for extended area (cell, substring, module, string)
```

**Reference correction factors from IEC Table 5:**

| Irradiance (W/m²) | Extended area factor | Point factor (x=1.5) |
|-------------------|---------------------|----------------------|
| 1000 | 1.0 | 1.0 |
| 800 | 1.25 | 1.40 |
| 700 | 1.43 | 1.69 |
| 600 | 1.67 | 2.15 |

### 6.3 Polygon Measurement Technique (IEC Annex D)

For detailed inspections, use polygon ROI tools in the camera software to compute:
- **Mean ΔT** over the affected area vs. a nearby reference polygon on a healthy module
- **Spot maximum ΔT** for point abnormalities

The Axalon platform stores `delta_t_measured` and `delta_t_normalized` per detection in the detection dict. These fields are populated when a detailed inspection is performed and values are entered into the API alongside the image submission.

### 6.4 Junction Box and BOS Inspection

For junction boxes and electrical BOS (fuses, connectors, switchgear):
- Use **MW-IR (2–5 µm)** cameras if metal surfaces dominate (low emissivity glass is not a factor)
- Minimum system load during inspection: **≥ 30% of nominal rating** (≥ 60% recommended)
- Point abnormality (x = 1.6 for BOS per IEC Table 5) applies to contacts and fuses
- Classification follows product standards: IEC 60269-1 (fuses), IEC 61439-1 (switchgear)

---

## 7. Pre-Flight Checklist & Environmental Go/No-Go

### 7.1 Equipment Pre-Flight

- [ ] IR camera calibration certificate valid (≤ 2 years from issue)
- [ ] IR camera emissivity set to 0.85 (or corrected for angle/soiling)
- [ ] T_refl measured and entered in camera firmware
- [ ] All equipment UTC time synchronized (GPS-disciplined clock preferred)
- [ ] Pyranometer co-planar with modules, logging started
- [ ] Anemometer active and reading ≤ 4 Bft
- [ ] DC clamp meter / inverter SCADA connected for string current log
- [ ] Drone firmware updated; gimbal calibrated; camera gimbal pitch set for viewing angle compliance

### 7.2 Site Pre-Flight

- [ ] Visual inspection of array completed; bird droppings, heavy soiling, burn spots documented
- [ ] Cleaning performed if heavy or non-homogeneous soiling observed
- [ ] 15-minute thermal steady-state wait completed after cleaning
- [ ] Irradiance ≥ 600 W/m² confirmed on pyranometer
- [ ] Wind ≤ 4 Bft confirmed
- [ ] Cloud coverage ≤ 2 okta cumulus confirmed
- [ ] Electrical safety briefing from site owner received
- [ ] Second person present (required by IEC §5.1)

### 7.3 Mid-Flight Monitoring

- [ ] Irradiance monitored — pause if change > 10%/min; resume after 15-minute wait
- [ ] Wind speed monitored — land immediately if > 4 Bft
- [ ] Sample thermal frames reviewed for smearing (Figure 1 check) at start of each row
- [ ] DC load monitored — pause if string trips to open circuit or short circuit

---

## 8. Data Format & File Handoff to Axalon Platform

### 8.1 Expected File Structure

```
flight_YYYYMMDD_HHMMSS/
├── thermal/
│   ├── DJI_0001_T.JPG          # Full radiometric RJPEG (with embedded radiometric data)
│   ├── DJI_0002_T.JPG
│   └── ...
├── rgb/
│   ├── DJI_0001_V.JPG          # Visual/RGB, same position, timestamp within 100 ms
│   ├── DJI_0002_V.JPG
│   └── ...
├── sensors/
│   └── irradiance_log.csv      # UTC timestamp, W/m², air_temp_C, wind_bft
└── flight_meta.json            # Site metadata (see §8.2)
```

Thermal files MUST be RJPEG (DJI FLIR format) or radiometric TIFF. Standard JPEG thermal images without embedded radiometry cannot support ΔT normalization.

### 8.2 `flight_meta.json` Schema

```json
{
  "site_name": "Solar Farm Alpha",
  "client": "SolarCo GmbH",
  "location": "Rajasthan, India",
  "lat": 26.9124,
  "lon": 75.7873,
  "capacity_mw": 10.0,
  "flight_date": "2026-05-12",
  "inspection_time": "10:30 UTC",
  "inspection_level": "Simplified",
  "drone_model": "DJI Matrice 350 RTK",
  "ir_camera_model": "FLIR Zenmuse XT2 640",
  "ir_camera_serial": "FLIR-001234",
  "ir_calibration_date": "2025-11-15",
  "rgb_camera_model": "DJI Zenmuse P1",
  "irradiance_wm2": 820,
  "air_temp_c": 38.5,
  "wind_speed_bft": 2,
  "cloud_coverage_okta": 1,
  "emissivity": 0.85,
  "t_refl_c": 22.0,
  "panel_tilt_deg": 25,
  "flying_altitude_m": 15,
  "flying_speed_ms": 1.5,
  "soiling_level": "Low",
  "inspector_name": "J. Sharma",
  "thermographer_cert": "ISO 9712 Level 1"
}
```

All fields map directly to `site_meta` in `platform/reporting/report.py` and appear in the IEC §8 compliant PDF report.

### 8.3 Pairing Logic

Axalon's `platform/pipeline/ingest.py` pairs thermal and RGB images by:

1. **Filename prefix match** — `DJI_0001_T.JPG` ↔ `DJI_0001_V.JPG`
2. **GPS proximity match** — thermal GPS within 5 m of RGB GPS (fallback)
3. **Timestamp match** — UTC timestamp within 200 ms (fallback)

For DJI FLIR drones, naming convention 1 works automatically. For third-party gimbals, ensure consistent filename schemes or rely on GPS matching.

### 8.4 EXIF GPS Tags Required

| EXIF Tag | Field | Example |
|----------|-------|---------|
| `GPS GPSLatitude` | Latitude (DMS) | `26° 54' 44.64" N` |
| `GPS GPSLongitude` | Longitude (DMS) | `75° 47' 14.28" E` |
| `GPS GPSAltitude` | Altitude (m) | `15.2` |
| `EXIF DateTimeOriginal` | UTC timestamp | `2026:05:12 10:32:15` |
| `XMP:RelativeAltitude` | AGL altitude (m) | `15.2` |
| `XMP:GimbalPitchDegree` | Camera pitch | `-90.0` (nadir) |

---

## 9. Software Integration Points

### 9.1 Where Hardware Data Enters the Axalon Pipeline

```
flight_meta.json ──────────────────────────────────────────────► site_meta dict
                                                                       │
                                                                       ▼
                                                         generate_pdf_report()
                                                         generate_excel_report()
                                                         (IEC §8 report fields)

irradiance_log.csv ──► matched to each image by timestamp ──────► det["irradiance_wm2"]
                                                                       │
                                                                       ▼
                                                         normalize_delta_t()
                                                         (det["delta_t_normalized"])

EXIF GPS in thermal JPEG ──► geo.py ────────────────────────────► det["gps_lat/lon"]
                                                                       │
                                                                       ▼
                                                         geojson_writer.py (GeoJSON output)

Radiometric RJPEG ──► (future) FLIR SDK extraction ────────────► det["delta_t_measured"]
                                                                  det["max_temp_c"]
                                                                  det["min_temp_c"]
```

### 9.2 Irradiance Log Merge (To Implement)

The irradiance sensor CSV must be merged with image metadata at ingest time. Implement in `platform/pipeline/ingest.py`:

```python
def match_irradiance(image_utc: datetime, irradiance_log: list[dict]) -> float | None:
    """Return nearest irradiance reading within 60 seconds of image capture."""
    candidates = [
        r for r in irradiance_log
        if abs((r["utc"] - image_utc).total_seconds()) <= 60
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: abs((r["utc"] - image_utc).total_seconds()))["wm2"]
```

### 9.3 Radiometric Data Extraction (To Implement)

FLIR RJPEG files contain embedded radiometric data (Planck constants, emissivity, T_refl, raw ADU values). Extract absolute pixel temperatures using the FLIR SDK or `flyr` Python library:

```python
# pip install flyr
import flyr
thermal = flyr.unpack("DJI_0001_T.JPG")
temp_array = thermal.kelvin - 273.15   # Celsius array, shape (H, W)

# For a detection bbox [x1, y1, x2, y2]:
roi = temp_array[y1:y2, x1:x2]
max_temp = roi.max()
mean_temp = roi.mean()
ref_temp  = temp_array[ref_y1:ref_y2, ref_x1:ref_x2].mean()  # adjacent healthy area
delta_t   = max_temp - ref_temp  # or mean_temp - ref_temp for extended area

det["max_temp_c"]       = float(max_temp)
det["min_temp_c"]       = float(roi.min())
det["delta_t_measured"] = float(delta_t)
det["irradiance_wm2"]   = irradiance_at_capture
det["delta_t_normalized"] = normalize_delta_t(
    delta_t, irradiance_at_capture, det["abnormality_type"]
)
```

### 9.4 IEC Identification Matrix — Cell Position (IEC Annex A.3)

For detailed inspection reports, individual cell positions are identified using the IEC alphanumeric matrix (column A–J, row 1–12 for 60-cell module), viewed from the front with the junction box at the top.

This is optional for drone-based simplified inspection but required for ground-level detailed investigation reports.

---

## 10. Calibration & Maintenance Schedule

### 10.1 IR Camera Calibration (IEC §4.2, Table 1)

| Task | Frequency | Record in |
|------|-----------|-----------|
| Factory traceable calibration | **Every 2 years** (mandatory) | `ir_calibration_date` in `flight_meta.json` |
| NUC (Non-Uniformity Correction) | Every flight, auto-triggered at takeoff | Camera firmware |
| Emissivity verification | Every flight | Flight log |
| T_refl measurement | Every flight (before first takeoff) | Flight log |
| Lens cleaning | Every flight | Visual check |

If absolute temperature error exceeds ±2 K on a traceable reference blackbody, **the camera must be returned to the manufacturer for adjustment before further use** (IEC §4.2j).

### 10.2 Pyranometer / Irradiance Sensor

| Task | Frequency |
|------|-----------|
| Factory calibration | Every 2 years |
| Dome cleaning | Before each flight |
| Levelling check | Before each flight |
| Zero-offset check | At night (before dawn) or under cover |

### 10.3 Drone Gimbal & Camera Alignment

| Task | Frequency |
|------|-----------|
| Gimbal calibration | Monthly or after any crash/hard landing |
| IR–RGB boresight alignment verification | After any lens or camera mount change |
| GPS antenna check | Before each flight |

---

## 11. Personnel Qualification (IEC Annex B)

### 11.1 Simplified Inspection (Drone Survey)

Minimum requirements for the lead inspector:
- Technical knowledge of PV plant operation and failure modes
- IR thermography training equivalent to **ISO 9712 Level 1** in electro-thermography
- Proof of eyesight (ISO 9712)
- Certified drone pilot (local aviation authority licence)
- Access to live electrical installations only by electrically qualified persons

> Two-day thermography training (beyond manufacturer camera training) is the IEC minimum for simplified commissioning inspections.

### 11.2 Detailed Inspection (On-Ground)

- **ISO 9712 Level 2** electro-thermography (minimum Level 1 with Level 2 PV expert co-signer)
- In-depth knowledge of PV failure modes and thermal signatures
- For fire-prevention inspections: inspector must be **independent** (not employed by the owner/operator)

### 11.3 Axalon Platform Operator

No specific IEC certification is required to operate the Axalon software platform. The AI classification (pattern recognition via YOLOv8s) performs the pattern-matching function that would otherwise require thermographer expertise at the simplified level. **The final CoA classification displayed by Axalon is advisory — a qualified thermographer must sign off on all CoA 3 findings before remediation is ordered.**

---

## 12. Recommended Hardware Stack

### 12.1 Tier 1 — Full IEC Compliance, Production Grade

| Component | Model | Notes |
|-----------|-------|-------|
| **Drone** | DJI Matrice 350 RTK | RTK GPS, 55 min flight time, IP55 |
| **IR Camera** | FLIR Zenmuse XT2 640 | 640 × 512, NETD < 50 mK, RJPEG, 13 mm lens |
| **RGB Camera** | DJI Zenmuse P1 | 45 MP, hardware sync with XT2 |
| **Pyranometer** | Kipp & Zonen CMP10 | ISO 9060 Secondary Standard, ± 2% |
| **Air temp sensor** | Vaisala HMP110 | Aspirated, shielded, ± 0.2 K |
| **Anemometer** | Davis Instruments 6410 | ± 5% |
| **Ground station** | DJI Smart Controller Enterprise | Mission planning, live feed |
| **DC clamp meter** | Fluke 376 FC | ± 1%, clamp on string cable |

**Axalon integration:** DJI FLIR naming conventions are natively supported. RJPEG extraction requires `flyr` library (`pip install flyr`).

### 12.2 Tier 2 — Cost-Optimised, Simplified Inspection Only

| Component | Model | Notes |
|-----------|-------|-------|
| **Drone** | DJI Mavic 3 Enterprise | 45 min flight time, ≤ 30 m altitude practical |
| **IR Camera** | FLIR Boson+ 320 | 320 × 256, NETD < 40 mK, CS mount |
| **RGB Camera** | Integrated 48 MP | Soft sync via timestamp |
| **Pyranometer** | Apogee SP-110 | ± 5%, less than CMP10 but IEC compliant |
| **Anemometer** | Kestrel 5500 | Handheld, Bluetooth logging |

> At 320 × 256 IR resolution, maximum compliant altitude is **10 m AGL** (§2.2). Suitable for small farms only.

### 12.3 Minimum Viable (R&D / Prototype Flights)

| Component | Model | Notes |
|-----------|-------|-------|
| **Drone** | DJI Mini 4 Pro | 34 min, lightweight |
| **IR Camera** | FLIR ONE Pro | 160 × 120 — **below IEC resolution minimum** |
| — | — | For internal R&D only; not IEC compliant |

> FLIR ONE Pro (160 × 120) fails the 5×5 pixel per cell requirement at any practical altitude. Use for algorithm development and training data collection only.

---

## Appendix — IEC Clause Cross-Reference

| IEC Clause | Topic | Axalon Implementation |
|-----------|-------|-----------------------|
| §4.1 | Date/time sync | `flight_meta.json` timestamp; EXIF UTC |
| §4.2 / Table 1 | IR camera minimum specs | §2.1 of this document |
| §4.3 | Photo camera requirements | `fusion.py` RGB pairing |
| §4.4 / Table 2 | Environmental equipment | §5 of this document; `site_meta` fields |
| §5.1 | Inspection procedure, intervals | §7 pre-flight checklist |
| §5.3 / Table 3 | Environmental conditions | §5.3 go/no-go table |
| §5.4.1 | Imaging procedure, angle | §4.3 viewing angle calculation |
| §5.4.2 | Drone-based inspection, smearing | §4.2 speed limits |
| §5.4.3 | Emissivity | `site_meta["emissivity"]`; §2.3 |
| §7.3.2 / Table 4 | Classes of Abnormality | `IEC_COA_MAP` in `ml/src/utils.py` |
| §7.4 | Temperature normalization | `normalize_delta_t()` in `ml/src/utils.py` |
| §7.4.1 | Point vs extended area | `IEC_ABNORMALITY_TYPE` in `ml/src/utils.py` |
| §8 | Inspection report contents | `generate_pdf_report()` context fields |
| Annex A.1 | Geometric resolution | §2.2 altitude table |
| Annex A.2 | Angle of view | §4.3 |
| Annex A.3 | Cell position matrix | §9.4 |
| Annex B | Personnel qualification | §11 |
| Annex C | Thermal abnormality matrix | `IEC_DELTA_T_RANGE_K`, `docs/ANOMALY_CLASSES.md` |
| Annex D | Polygon measurement | §6.3; `delta_t_measured` field |
| Annex E | Beaufort scale | `wind_speed_bft` in `site_meta` |
