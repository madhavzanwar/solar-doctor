"""map router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import JobMapOut

router = APIRouter(tags=["map"])

@router.get("/map/{job_id}", response_model=JobMapOut)
def get_job_map(job_id: str, principal: Principal = Depends(current_principal)):
    """Return combined GPS map data for a batch job.

    Aggregates every image's capture position + every anomaly's GPS into a
    single payload the frontend can render on Leaflet. When EXIF GPS is
    missing, generates deterministic synthetic positions so the map remains
    populated.
    """
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id)
    job = _get_job(job_id)
    report = _read_inspection_report(job_id)

    if job is None and report is None:
        raise HTTPException(status_code=404, detail="Job not found")

    source = report or job or {}
    # Batch jobs expose a `results` list; single-pair `/inspect` jobs flatten
    # the result into the top-level dict — normalize both into a list.
    if "results" in source and isinstance(source["results"], list):
        results = source["results"]
    elif "detections" in source:
        results = [source]
    else:
        results = []

    park_id = source.get("park_id") or "unknown"
    flight_date = source.get("flight_date", "")

    images_out: list[dict] = []
    anomalies_out: list[dict] = []
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    lats: list[float] = []
    lons: list[float] = []

    for idx, result in enumerate(results):
        altitude = float(result.get("altitude_m") or 40.0)
        img_gps = result.get("image_gps")
        if not img_gps or "lat" not in img_gps or "lon" not in img_gps:
            img_gps = _synthetic_image_gps(idx, altitude)

        image_id = result.get("image_id") or f"img-{idx:04d}"
        detections = result.get("detections", [])
        image_critical = sum(
            1 for d in detections if (d.get("severity") or "").upper() == "CRITICAL"
        )

        thermal_path = result.get("annotated_thermal") or ""
        rgb_path = result.get("annotated_rgb") or ""
        thermal_filename = Path(thermal_path).name if thermal_path else ""
        rgb_filename = Path(rgb_path).name if rgb_path else ""

        images_out.append({
            "image_id": image_id,
            "lat": img_gps["lat"],
            "lon": img_gps["lon"],
            "altitude_m": altitude,
            "detection_count": len(detections),
            "critical_count": image_critical,
            "synthetic": bool(img_gps.get("synthetic")),
            "thermal_filename": thermal_filename,
            "rgb_filename": rgb_filename,
        })
        lats.append(img_gps["lat"])
        lons.append(img_gps["lon"])

        for det in detections:
            sev = (det.get("severity") or "LOW").upper()
            if sev in summary:
                summary[sev] += 1

            gps = det.get("gps") or det.get("detection_gps")
            if not gps or "lat" not in gps or "lon" not in gps:
                gps = _synthetic_detection_gps(
                    img_gps, det.get("bbox", [0, 0, 0, 0]),
                    result.get("image_size", [640, 512]),
                )

            anomalies_out.append({
                "id": f"{image_id}-{len(anomalies_out):04d}",
                "image_id": image_id,
                "lat": gps["lat"],
                "lon": gps["lon"],
                "severity": sev,
                "class": det.get("class", ""),
                "class_id": det.get("class_id", -1),
                "confidence": round(float(det.get("confidence") or 0.0), 3),
                "panel_id": det.get("panel_id", "N/A"),
                "color": _SEVERITY_COLOR.get(sev, "#0284c7"),
                "synthetic": bool(gps.get("synthetic")),
                "thermal_filename": thermal_filename,
            })
            lats.append(gps["lat"])
            lons.append(gps["lon"])

    bounds = None
    if lats and lons:
        bounds = {
            "south": min(lats),
            "north": max(lats),
            "west":  min(lons),
            "east":  max(lons),
            "center": {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)},
        }

    synthetic = any(img.get("synthetic") for img in images_out)

    return {
        "job_id": job_id,
        "park_id": park_id,
        "flight_date": flight_date,
        "total_images": len(images_out),
        "total_anomalies": len(anomalies_out),
        "summary": summary,
        "bounds": bounds,
        "synthetic": synthetic,
        "images": images_out,
        "anomalies": anomalies_out,
    }
