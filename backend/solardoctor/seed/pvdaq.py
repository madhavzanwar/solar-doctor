"""PVDAQ (NREL/DOE, OEDI data lake) import: file download, pure mapping, DB write.

Real data, labelled ``source="PVDAQ"``.  Supports the 2023 DOE *Solar Data Prize* systems (2105, 2107,
7333, 9068, 9069), whose OEDI layout is ``pvdaq/2023-solar-data-prize/<id>_OEDI/{data,metadata}``.
Note: ``pvdaq_access.downloadData`` (v0.1.2) looks under ``pvdaq/csv/pvdata/system_id=<id>`` which does
not contain 9068 (it is a Solar Data Prize system), and ``downloadSolarPrizeData`` downloads every
file of the system (several GB).  We therefore use the same anonymous S3 access pattern
(boto3 with request signing disabled, bucket ``oedi-data-lake``) but fetch only the three files needed.

Assumptions (documented, not measured): PVDAQ ``measured_on`` timestamps are local standard time with a
fixed UTC offset equal to the metadata ``timezone_code`` (9068: 7 -> UTC-7); 5-minute samples are
averaged to 15-minute bins; plant AC power is the sum of the ``inverter_<n>_ac_power`` columns; POA is the
mean of the (non temperature-compensated) pyranometer POA columns.  ``p_expected_kw`` is left empty:
these sites are single-axis trackers, which the fixed-tilt physics baseline does not model.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from solardoctor.physics.models import Inverter, Plant, SOURCE_PVDAQ, Telemetry

BUCKET = "oedi-data-lake"
PRIZE_PREFIX = "pvdaq/2023-solar-data-prize/{sid}_OEDI/"
STEP = "15min"

_INV_AC = re.compile(r"^inverter_(\d+)_ac_power_\(kw\)")
_POA = re.compile(r"poa_irradiance_\(w/m2\)_o_")


class PvdaqUnavailable(RuntimeError):
    """The OEDI data lake could not be reached or does not hold the requested system."""


# ------------------------------------------------------------------ download
def download_prize_files(system_id: int, dest: Path, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Path]:
    """Download metadata + AC-power + irradiance CSVs for a Solar Data Prize system into ``dest``."""
    try:
        import boto3
        import botocore
        from botocore.handlers import disable_signing
    except ImportError as exc:  # pragma: no cover
        raise PvdaqUnavailable("boto3/pvdaq_access not installed: pip install pvdaq_access") from exc
    dest.mkdir(parents=True, exist_ok=True)
    try:
        s3 = boto3.resource("s3")
        s3.meta.client.meta.events.register("choose-signer.s3.*", disable_signing)
        bucket = s3.Bucket(BUCKET)
        keys = [o.key for o in bucket.objects.filter(Prefix=PRIZE_PREFIX.format(sid=system_id))]
        if not keys:
            raise PvdaqUnavailable(
                f"system {system_id} has no files under {PRIZE_PREFIX.format(sid=system_id)} in s3://{BUCKET} "
                "(only DOE Solar Data Prize systems are supported by this importer)")

        def pick(kind: str) -> str:
            cands = [k for k in keys if k.endswith(".csv") and f"_{kind}_data" in k]
            if not cands:
                raise PvdaqUnavailable(f"no {kind} CSV for system {system_id}")
            ranged = []
            for k in cands:  # e.g. 9068_ac_power_data_20240101_20250430.csv
                m = re.search(r"_(\d{8})_(\d{8})\.csv$", k)
                if m and pd.Timestamp(m.group(1)) <= start.tz_localize(None) and pd.Timestamp(m.group(2)) >= end.tz_localize(None):
                    ranged.append(k)
            return min(ranged, key=lambda k: len(k)) if ranged else min(cands, key=len)

        wanted = {"ac": pick("ac_power"), "irr": pick("irradiance")}
        meta = [k for k in keys if k.endswith("_system_metadata.json")]
        if not meta:
            raise PvdaqUnavailable(f"no system metadata JSON for system {system_id}")
        wanted["meta"] = meta[0]
        out = {}
        for name, key in wanted.items():
            path = dest / Path(key).name
            if not path.exists():
                bucket.download_file(key, str(path))
            out[name] = path
        return out
    except PvdaqUnavailable:
        raise
    except Exception as exc:
        raise PvdaqUnavailable(f"could not reach s3://{BUCKET}: {type(exc).__name__}: {exc}") from exc


# ------------------------------------------------------------------ mapping (pure)
@dataclass
class Mapped:
    plant: dict
    inverters: list[dict]           # name, ac_kw, column key
    telemetry: pd.DataFrame         # index UTC; columns plant_ac, poa, inv_<n> ...
    meta_notes: list[str]


def _utc_offset_hours(meta: dict) -> float:
    return float(meta["System"].get("timezone_code", 0))


def map_pvdaq(ac_csv: Path, irr_csv: Path, meta_json: Path, start: pd.Timestamp, end: pd.Timestamp) -> Mapped:
    meta = json.loads(Path(meta_json).read_text())
    system, site = meta["System"], meta["Site"]
    off = _utc_offset_hours(meta)

    def read(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = (pd.DatetimeIndex(df.index) + pd.Timedelta(hours=off)).tz_localize("UTC")  # local standard time -> UTC
        return df.loc[(df.index >= start) & (df.index < end + pd.Timedelta(days=1))]

    ac, irr = read(ac_csv), read(irr_csv)
    if ac.empty:
        raise PvdaqUnavailable(f"{ac_csv.name} has no rows between {start:%Y-%m-%d} and {end:%Y-%m-%d} (UTC)")
    inv_cols = {int(m.group(1)): c for c in ac.columns if (m := _INV_AC.match(c))}
    if not inv_cols:
        raise PvdaqUnavailable("no inverter_<n>_ac_power_(kw) columns found in the AC power CSV")
    inv_ac = pd.DataFrame({f"inv_{n}": ac[c] for n, c in sorted(inv_cols.items())})
    inv_ac = inv_ac.clip(lower=0.0).resample(STEP, closed="left", label="left").mean()
    plant_ac = inv_ac.sum(axis=1, min_count=inv_ac.shape[1])
    poa_cols = [c for c in irr.columns if _POA.search(c) and "temp_compensated" not in c]
    poa = irr[poa_cols].mean(axis=1).clip(lower=0.0).resample(STEP, closed="left", label="left").mean() if poa_cols else None

    tel = inv_ac.copy()
    tel["plant_ac"] = plant_ac
    tel["poa"] = poa if poa is not None else np.nan
    tel = tel.dropna(subset=["plant_ac"])

    invs_meta = list(meta.get("Inverters", {}).values())
    inverters = []
    for n in sorted(inv_cols):
        im = invs_meta[n - 1] if n - 1 < len(invs_meta) else {}
        inverters.append(dict(name=im.get("name", f"inverter_{n}"), ac_kw=im.get("AC capacity(kW)"), key=f"inv_{n}"))
    ac_kw = sum(i["ac_kw"] or 0.0 for i in inverters) or float(plant_ac.max())
    mod = next(iter(meta.get("Modules", {}).values()), {})
    mount = next(iter(meta.get("Mount", {}).values()), {})
    coeff = mod.get("temperature coefficient of maximum power(%C)")
    notes = [
        f"timestamps shifted by +{off:g} h (metadata timezone_code interpreted as UTC-{off:g}, local standard time)",
        "5-min samples averaged to 15 min; plant AC = sum of inverter AC columns; POA = mean of non-compensated pyranometers",
        f"mount: {mount.get('type', '?')} (tracking={mount.get('tracking', '?')}); fixed-tilt physics baseline not applied",
    ]
    plant = dict(
        name=f"PVDAQ {system['system_id']} {system.get('public_name', '')}".strip(),
        location=site.get("location"), lat=float(site["latitude"]), lon=float(site["longitude"]),
        tz="America/Denver" if abs(off - 7) < 1e-9 else "UTC",  # assumption: only used for display
        altitude_m=float(site.get("elevation(m)", 0.0) or 0.0),
        tilt=float(mount.get("tilt", 0.0) or 0.0), azimuth=float(mount.get("azimuth", 180.0) or 180.0),
        dc_kw=float(system["power(kW DC)"]), ac_kw=float(ac_kw),
        module_count=mod.get("quantity"), module_wp=mod.get("nameplate capacity(W)"),
        temp_coeff=(float(coeff) / 100.0) if coeff is not None else -0.004,
        tariff_inr_kwh=None, source=SOURCE_PVDAQ,
    )
    return Mapped(plant, inverters, tel, notes)


# ------------------------------------------------------------------ DB write
def write_mapped(db: Session, m: Mapped) -> dict:
    """Idempotently create/update the PVDAQ plant and replace its telemetry in the imported span."""
    plant = db.query(Plant).filter(Plant.name == m.plant["name"]).first()
    if plant is not None and plant.source != SOURCE_PVDAQ:
        raise RuntimeError(f"a non-PVDAQ plant named {plant.name!r} exists; refusing to overwrite it")
    if plant is None:
        plant = Plant(**m.plant)
        db.add(plant)
        db.flush()
    inv_ids = {}
    existing = {i.name: i for i in db.query(Inverter).filter(Inverter.plant_id == plant.id)}
    for inv in m.inverters:
        row = existing.get(inv["name"]) or Inverter(plant_id=plant.id, name=inv["name"], ac_kw=inv["ac_kw"], vendor="PVDAQ")
        if row.id is None:
            db.add(row)
            db.flush()
        inv_ids[inv["key"]] = row.id
    t0, t1 = m.telemetry.index.min().to_pydatetime(), m.telemetry.index.max().to_pydatetime()
    db.execute(delete(Telemetry).where(Telemetry.plant_id == plant.id, Telemetry.source == SOURCE_PVDAQ,
                                       Telemetry.ts >= t0, Telemetry.ts <= t1))
    rows = []

    def f(x):
        return None if pd.isna(x) else round(float(x), 4)

    for ts, r in m.telemetry.iterrows():
        base = dict(ts=ts.to_pydatetime(), plant_id=plant.id, poa_wm2=f(r["poa"]), source=SOURCE_PVDAQ)
        rows.append(dict(base, p_ac_kw=f(r["plant_ac"]), inverter_id=None))
        for inv in m.inverters:
            rows.append(dict(base, p_ac_kw=f(r[inv["key"]]), inverter_id=inv_ids[inv["key"]]))
    for i in range(0, len(rows), 5000):
        db.execute(Telemetry.__table__.insert(), rows[i:i + 5000])
    db.commit()
    return dict(plant_id=plant.id, name=plant.name, rows=len(rows), start=t0, end=t1)
