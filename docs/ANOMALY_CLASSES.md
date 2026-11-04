# Anomaly Classes — YOLOv8s Model (IEC TS 62446-3:2017 aligned)

11 classes detected in thermal IR imagery. Class IDs are fixed (0–10).

Classification follows **IEC TS 62446-3:2017 Annex C** — Matrix for thermal abnormalities of PV modules.

## Class Reference

| ID | Class | Severity | IEC CoA | Abnormality Type | ΔT at 1 000 W/m² | IEC Pattern (Annex C) |
|----|-------|----------|---------|-----------------|-------------------|-----------------------|
| 0  | cell | MEDIUM | CoA 2 | Extended area | 10–40 K | Single cell with temp difference (Ex. 7a) |
| 1  | cell-multi | MEDIUM | CoA 2 | Extended area | 10 K+ | Multi-cell variation of Ex. 7 |
| 2  | module | MEDIUM | CoA 2 | Extended area | 2–7 K | Module thermal anomaly |
| 3  | string | CRITICAL | CoA 3 | Extended area | 2–7 K | String / module open circuit (Ex. 1–3) |
| 4  | bypass-diode | CRITICAL | CoA 3 | **Point** | ≥ 3 K | Bypass diode / junction box failure (Ex. 10–12) |
| 5  | offline-module | HIGH | CoA 2 | Extended area | 2–7 K | Module in open circuit (Ex. 1–3) |
| 6  | vegetation-shading | LOW | CoA 2 | Extended area | variable | Vegetation shading (related to Ex. 8) |
| 7  | soiling | LOW | CoA 2 | Extended area | 0–7 K | Soiling / partial shading (Ex. 8) |
| 8  | short-circuit | HIGH | CoA 2 | Extended area | 2–7 K | Module in short circuit (Ex. 2) |
| 9  | hot-spot-low | HIGH | CoA 2 | Extended area | 10–40 K | Single cell hot spot (Ex. 7a) |
| 10 | hot-spot-high | CRITICAL | CoA 3 | Extended area | > 40 K | Single cell hot spot — irreversible damage risk (Ex. 9b) |

## IEC Classes of Abnormality (Table 4)

| CoA | Label | Recommended Action |
|-----|-------|--------------------|
| CoA 1 | No Abnormality | No action required. |
| CoA 2 | Thermal Abnormality (tA) | Check the cause and, if necessary, rectify in a reasonable period. |
| CoA 3 | Safety-Relevant Thermal Abnormality (dtA) | Prompt interruption of operation, check the cause and rectify in a reasonable period. |

## Severity Definitions (internal)

- **CRITICAL (CoA 3):** Immediate shutdown and inspection required. Fire/safety risk.
- **HIGH (CoA 2–3):** Repair within 1 week. Significant power loss or failure risk.
- **MEDIUM (CoA 2):** Schedule for next maintenance cycle.
- **LOW (CoA 2):** Monitor and address during routine maintenance.

## Temperature Normalization (IEC §7.4)

All reported ΔT values are normalized to **1 000 W/m²** using:

```
ΔT₂ = (G₂ / G₁)^x × ΔT₁
```

| Abnormality Type | Exponent x | Classes |
|-----------------|------------|---------|
| Point | 1.5 (PV modules) | bypass-diode |
| Extended area | 1.0 (linear) | all others |

Use `ml.src.utils.normalize_delta_t()` for all temperature normalization.

## Inspection Conditions (IEC §5.3)

Required for valid thermal inspection:
- Irradiance: ≥ 600 W/m² (in-plane of PV module)
- Wind speed: ≤ 4 Bft (≤ 28 km/h)
- Cloud coverage: ≤ 2 okta cumulus clouds
- Soiling: none or low

## Emissivity Reference (IEC §5.4.3)

| Surface | Emissivity (ε) |
|---------|----------------|
| PV module glass (perpendicular) | ~0.85 |
| PV module glass (45°) | ~0.80 |
| PV module glass (30°) | ~0.75 |
| Oxidized aluminium frame | 0.4–0.7 |
| Insulation synthetics / ceramics | ~0.90 |
| Unoxidized / polished metal | 0.1–0.3 |

Default emissivity used in analysis: **ε = 0.85** (clean glass, perpendicular view).
