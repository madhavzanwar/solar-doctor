"""
orchestrator.py — Full inspection pipeline orchestrator.

Runs the complete pipeline for one or many image pairs:
  ingest → detect → localize → fuse → store → report
"""

from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path

from ml.src.utils import draw_detections_severity, load_bgr, get_logger

from axalon.core.detector import SolarDetector
from axalon.core.fusion import ImageFusion
from axalon.core.fusion_calibration import resolve_active_calibration
import cv2

from axalon.core.geo import detection_to_gps, extract_gps_exif
from axalon.park.layout import ParkLayoutDetector
from axalon.park.locator import MANUAL_MODE, PANEL_ID_UNKNOWN, locate_faults
from axalon.park.manual_layout import LayoutError, load_park_layout
from axalon.db.session import get_engine, get_session, init_db
from axalon.db.models import Park, Inspection, Detection as DbDetection
from axalon.pipeline.ingest import find_image_pairs, load_mission_metadata, validate_pair
from axalon.core.temp_extractor import (
    TEMP_FIELDS,
    compute_delta_t,
    load_temp_matrix,
    normalize_delta_t,
)
from axalon.pipeline.tracking import dedup_detections, reconcile_inspection

logger = get_logger("axalon.orchestrator")

_UNASSIGNED_PANEL = "R?-C?"


def _match_panel_id(detection: dict, panel_map: dict) -> str:
    """Return the nearest panel_id for a detection bbox center, or 'R?-C?'."""
    if not panel_map:
        return "R?-C?"
    bbox = detection["bbox"]
    det_cx = (bbox[0] + bbox[2]) / 2
    det_cy = (bbox[1] + bbox[3]) / 2
    best_id = "R?-C?"
    best_dist = float("inf")
    for pid, info in panel_map.items():
        pcx, pcy = info["center"]
        dist = ((det_cx - pcx) ** 2 + (det_cy - pcy) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_id = pid
    return best_id


def _load_rgb_frames(pairs: list[dict]) -> tuple[list, list]:
    """Load every pair's RGB frame and its EXIF GPS (for auto-grid fitting)."""
    rgb_images, rgb_gps_list = [], []
    for pair in pairs:
        rgb_path = pair.get("rgb")
        if rgb_path and Path(rgb_path).exists():
            img = load_bgr(rgb_path)
            if img is not None:
                rgb_images.append(img)
                rgb_gps_list.append(extract_gps_exif(rgb_path))
    return rgb_images, rgb_gps_list


def assign_panel_ids(detections: list[dict], park_layout: dict) -> list[dict]:
    """Return detections with ``panel_id`` / ``panel_confidence`` attached.

    GPS-anchored locator first. For auto-grid layouts an unmatched detection
    falls back to the image-pixel nearest-centre heuristic; manual layouts have
    no image-space panels, so an unmatched detection stays unassigned.
    """
    panel_map = park_layout.get("panel_map") or {}
    is_manual = park_layout.get("mode") == MANUAL_MODE
    located = locate_faults(detections, park_layout)
    out = []
    for det, lf in zip(detections, located):
        if lf.panel_id != PANEL_ID_UNKNOWN:
            panel_id = lf.panel_id
        elif is_manual:
            panel_id = _UNASSIGNED_PANEL
        else:
            panel_id = _match_panel_id(det, panel_map)
        out.append({**det, "panel_id": panel_id, "panel_confidence": lf.confidence})
    return out


def _ensure_park(session, park_id: str, layout: dict | None) -> None:
    """Insert park record if it doesn't exist yet."""
    existing = session.query(Park).filter_by(id=park_id).first()
    if existing:
        return
    rows = layout["rows"] if layout else 0
    total = layout["total_panels"] if layout else 0
    park = Park(
        id=park_id,
        name=park_id,
        mode=layout["mode"] if layout else "auto",
        total_panels=total,
        rows=rows,
        cols=total // max(rows, 1),
    )
    session.add(park)
    session.commit()


class InspectionOrchestrator:
    """Runs the full solar inspection pipeline."""

    def __init__(
        self,
        weights_path: str | Path | None = None,
        conf: float = 0.25,
        device: str = "0",
        output_dir: str | Path = "output",
        park_mode: str = "auto",
        db_url: str | None = None,
    ) -> None:
        self.detector = SolarDetector(
            **({"weights_path": weights_path} if weights_path is not None else {}),
            conf=conf,
            device=device,
        )
        self.fusion = ImageFusion(mode="auto")
        self.output_dir = Path(output_dir)
        self.park_mode = park_mode
        if db_url is None:
            # Use the app's configured database (AXALON_DB_URL). init_db() would
            # rebuild the process-wide engine, and the API constructs this lazily
            # on the first batch job — repointing every later write mid-job.
            get_engine()
        else:
            init_db(db_url)
        self.layout_detector = ParkLayoutDetector()

    def inspect_pair(
        self,
        thermal_path: str | Path,
        rgb_path: str | Path | None = None,
        park_id: str = "unknown",
        altitude_m: float = 40.0,
        panel_map: dict | None = None,
        inspection_id: str | None = None,
        temp_raw_path: str | Path | None = None,
        irradiance_wm2: float | None = None,
        park_layout: dict | None = None,
    ) -> dict:
        """Run full pipeline on a single thermal+RGB pair.

        ``park_layout`` (full layout dict incl. ``mode``) takes precedence over
        the bare ``panel_map`` so manual layouts keep their polygon matching.

        Returns:
            Inspection result dict (matches AXALON_PLATFORM_SPEC output format).
        """
        thermal_path = Path(thermal_path)
        rgb_path = Path(rgb_path) if rgb_path else None

        # Detect anomalies in thermal image
        detections = self.detector.predict(thermal_path)

        # Load images for visualization
        thermal_bgr = load_bgr(thermal_path)
        img_h, img_w = thermal_bgr.shape[:2]

        # GPS enrichment — rotate pixel offsets by the camera heading when the
        # image carries one; without it we can only assume north-up.
        image_gps = extract_gps_exif(thermal_path)
        for det in detections:
            if image_gps:
                det["gps"] = detection_to_gps(
                    det["bbox"], img_w, img_h, image_gps, altitude_m,
                    heading_deg=image_gps.get("heading", 0.0),
                )

        # Temperature enrichment — requires _temp.raw companion from iTL612R Pro
        if temp_raw_path is not None:
            try:
                temp_matrix = load_temp_matrix(temp_raw_path)
                for det in detections:
                    temps = compute_delta_t(temp_matrix, det["bbox"])
                    det["min_temp"] = temps["min_temp"]
                    det["max_temp"] = temps["max_temp"]
                    det["avg_temp"] = temps["avg_temp"]
                    det["reference_temp"] = temps["reference_temp"]
                    det["delta_t_measured"] = temps["delta_t_measured"]
                    det["irradiance_wm2"] = irradiance_wm2
                    if temps["delta_t_measured"] is not None and irradiance_wm2:
                        det["delta_t_normalized"] = normalize_delta_t(
                            temps["delta_t_measured"], irradiance_wm2
                        )
            except Exception:
                logger.warning("Temperature extraction failed for %s", thermal_path.name)

        detections = assign_panel_ids(
            detections, park_layout if park_layout is not None else {"panel_map": panel_map or {}}
        )

        # Annotated thermal output
        annotated_thermal = draw_detections_severity(thermal_bgr, detections)
        job_id = f"AXL-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{thermal_path.stem}"
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        thermal_out = job_dir / f"{thermal_path.stem}_annotated.jpg"
        cv2.imwrite(str(thermal_out), annotated_thermal)

        # RGB fusion overlay
        rgb_out = None
        fusion_mode = None
        if rgb_path and rgb_path.exists():
            rgb_bgr = load_bgr(rgb_path)
            rgb_gps = extract_gps_exif(rgb_path)
            fused = self.fusion.align(
                thermal_bgr, rgb_bgr, detections,
                thermal_gps=image_gps, rgb_gps=rgb_gps
            )
            fusion_mode = fused.mode
            rgb_out = job_dir / f"{thermal_path.stem}_rgb_annotated.jpg"
            cv2.imwrite(str(rgb_out), fused.image)

        summary = self.detector.detection_summary(detections)

        result = {
            "job_id": job_id,
            "park_id": park_id,
            "image_id": thermal_path.stem,
            "thermal_path": str(thermal_path),
            "rgb_path": str(rgb_path) if rgb_path else None,
            "flight_date": date.today().isoformat(),
            "image_gps": image_gps,
            "image_size": [img_w, img_h],
            "altitude_m": altitude_m,
            "detections": detections,
            "summary": summary,
            "annotated_thermal": str(thermal_out),
            "annotated_rgb": str(rgb_out) if rgb_out else None,
            "fusion_mode": fusion_mode,
            "total_detections": len(detections),
        }

        # Persist detections to DB if inspection_id provided
        if inspection_id:
            session = get_session()
            try:
                for det in detections:
                    db_det = DbDetection(
                        inspection_id=inspection_id,
                        image_id=thermal_path.stem,
                        panel_id=det.get("panel_id", "R?-C?"),
                        class_=det.get("class"),
                        class_id=det.get("class_id"),
                        severity=det.get("severity"),
                        confidence=det.get("confidence"),
                        bbox=json.dumps(det.get("bbox")),
                        gps=json.dumps(det.get("gps")) if det.get("gps") else None,
                        **{field: det.get(field) for field in TEMP_FIELDS},
                    )
                    session.add(db_det)
                session.commit()
            finally:
                session.close()

        return result

    def _resolve_layout(self, park_id: str, load_rgb) -> dict | None:
        """Manual layout when one is stored for the park, else auto-grid.

        ``load_rgb`` is a zero-arg callable returning ``(rgb_images, gps_list)``;
        it is only called when auto-grid is needed, so parks with a manual
        layout never hold every RGB frame in memory. A stored layout that no
        longer validates raises LayoutError rather than silently localising
        against a grid the operator already said is wrong.
        """
        session = get_session()
        try:
            manual = load_park_layout(session, park_id)
        finally:
            session.close()
        if manual is not None:
            logger.info("Park %s: manual layout, %d panels in %d tables",
                        park_id, manual.total_panels, manual.table_count)
            return manual.to_locator_layout()

        rgb_images, rgb_gps_list = load_rgb()
        if not rgb_images:
            return None
        layout = self.layout_detector.build_layout(rgb_images, rgb_gps_list)
        logger.info("Park grid: %d panels, %d rows", layout["total_panels"], layout["rows"])
        return layout

    def inspect_folder(
        self,
        folder: str | Path,
        park_id: str = "unknown",
        altitude_m: float = 40.0,
        progress_callback=None,
        site_meta: dict | None = None,
    ) -> dict:
        """Run full pipeline on an entire flight folder.

        Args:
            folder:            Flight mission folder (expects thermal/ + rgb/ subdirs).
            park_id:           Solar park identifier.
            altitude_m:        Drone altitude for GSD calculation.
            progress_callback: Optional callable(processed, total) for progress updates.

        Returns:
            Batch inspection result dict.
        """
        pairs = find_image_pairs(folder)
        mission_meta = load_mission_metadata(folder)
        site_meta = site_meta or {}
        irradiance_wm2 = site_meta.get("irradiance_wm2")
        try:
            irradiance_wm2 = float(irradiance_wm2) if irradiance_wm2 else None
        except (TypeError, ValueError):
            irradiance_wm2 = None
        total = len(pairs)
        logger.info("Starting batch: %d pairs, park=%s", total, park_id)

        # Re-resolve the rig calibration per batch so an upload via the API
        # applies to the next batch without restarting the long-lived API.
        active_calibration = resolve_active_calibration()
        if active_calibration.error:
            logger.warning("Fusion calibration unusable (%s): %s",
                           active_calibration.source, active_calibration.error)
        self.fusion = ImageFusion(
            mode=self.fusion.mode,
            camera_offset=self.fusion.camera_offset,
            calibration=active_calibration.calibration,
        )

        # PHASE 1: Park layout — stored manual layout, else auto-grid from RGB
        layout = self._resolve_layout(park_id, load_rgb=lambda: _load_rgb_frames(pairs))
        panel_map = layout["panel_map"] if layout else {}

        # Ensure park record exists in DB
        session = get_session()
        try:
            _ensure_park(session, park_id, layout)
        finally:
            session.close()

        # Create inspection record BEFORE phase 2 so FK holds for streaming detections
        batch_id = f"BATCH-{park_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        flight_date = date.today().isoformat()

        session = get_session()
        try:
            def _safe_float(val):
                try:
                    return float(val) if val not in (None, "") else None
                except (TypeError, ValueError):
                    return None

            insp = Inspection(
                id=batch_id,
                park_id=park_id,
                flight_date=flight_date,
                total_images=total,
                total_detections=0,
                summary="{}",
                client=site_meta.get("client") or None,
                location=site_meta.get("location") or None,
                capacity_mw=_safe_float(site_meta.get("capacity_mw")),
                inspection_type=site_meta.get("inspection_type", "maintenance"),
                inspection_level=site_meta.get("inspection_level", "simplified"),
                irradiance_wm2=_safe_float(site_meta.get("irradiance_wm2")),
                wind_speed_bft=_safe_float(site_meta.get("wind_speed_bft")),
                cloud_coverage_okta=_safe_float(site_meta.get("cloud_coverage_okta")),
            )
            session.add(insp)
            session.commit()
        finally:
            session.close()

        # PHASE 2: Process each image pair, stream detections to DB
        all_detections = []
        all_results = []
        for i, pair in enumerate(pairs):
            warnings = validate_pair(pair)
            for w in warnings:
                logger.warning("[%s] %s", pair["id"], w)
            result = self.inspect_pair(
                thermal_path=pair["thermal"],
                rgb_path=pair.get("rgb"),
                park_id=park_id,
                altitude_m=mission_meta.get("altitude_m", altitude_m),
                panel_map=panel_map,
                park_layout=layout,
                inspection_id=batch_id,
                temp_raw_path=pair.get("temp_raw"),
                irradiance_wm2=irradiance_wm2,
            )
            all_results.append(result)
            all_detections.extend(result["detections"])
            if progress_callback:
                progress_callback(i + 1, total)

        # PHASE 3: Dedup, reconcile with PanelFault history, update inspection record
        deduped = dedup_detections(all_detections)
        summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for det in deduped:
            sev = det.get("severity", "LOW")
            if sev in summary:
                summary[sev] += 1

        session = get_session()
        try:
            fault_counts = reconcile_inspection(
                session,
                park_id=park_id,
                inspection_id=batch_id,
                flight_date=flight_date,
                detections=deduped,
            )
            insp = session.query(Inspection).filter_by(id=batch_id).first()
            insp.total_detections = len(deduped)
            insp.summary = json.dumps(summary)
            session.commit()
        finally:
            session.close()

        return {
            "batch_id": batch_id,
            "park_id": park_id,
            "flight_date": flight_date,
            "total_images": total,
            "total_detections": len(deduped),
            "raw_detections": len(all_detections),
            "summary": summary,
            "fault_tracking": fault_counts,
            "fusion_calibration": {
                "source": active_calibration.source,
                "rig_id": getattr(active_calibration.calibration, "rig_id", None),
                "error": active_calibration.error,
            },
            "layout": layout,
            "results": all_results,
        }
