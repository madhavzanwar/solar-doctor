"""pvlib physics baseline: clear-sky irradiance, POA, cell temperature, PVWatts DC and clipped AC.

This is the "expected power" SolarDoctor compares telemetry against. It reuses SolarPulse's
pvlib feature pipeline (``ml.forecast.features.pvlib_features``: Ineichen clear-sky, Erbs split,
Hay-Davies transposition, Faiman cell temperature) and adds the PVWatts DC model
(``pvlib.pvsystem.pvwatts_dc``) plus AC clipping at the plant rating.

No network access: clear-sky uses pvlib's bundled Linke-turbidity table.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import pvlib

from ml.forecast.config import PlantConfig
from ml.forecast.features.pvlib_features import compute_pvlib_features
from solardoctor.physics.tracker import require_fixed_tilt_baseline

# PVWatts default aggregate DC system losses (soiling excluded, handled separately) and inverter.
SYSTEM_LOSS_FRACTION = 0.14
INVERTER_EFFICIENCY = 0.96


def plant_config_from_orm(plant) -> PlantConfig:
    """Build the ml.forecast PlantConfig from a ``physics.models.Plant`` row (or compatible)."""
    return PlantConfig(
        plant_id=str(plant.id),
        name=plant.name,
        latitude=plant.lat,
        longitude=plant.lon,
        altitude=plant.altitude_m or 0.0,
        tilt_deg=plant.tilt,
        azimuth_deg=plant.azimuth,
        capacity_dc_kw=plant.dc_kw,
        ac_export_limit_kw=plant.ac_kw,
    )


def _utc_index(times) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(times)
    return idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")


def clearsky_irradiance(lat: float, lon: float, times, altitude_m: float = 0.0) -> pd.DataFrame:
    """Ineichen clear-sky ghi/dni/dhi (W/m2) at the given times."""
    loc = pvlib.location.Location(lat, lon, altitude=altitude_m or 0.0)
    return loc.get_clearsky(_utc_index(times), model="ineichen")


def expected_power(
    plant,
    times,
    ghi: Optional[pd.Series] = None,
    temp_air: Optional[pd.Series] = None,
    wind_speed: Optional[pd.Series] = None,
    soiling_loss: float = 0.0,
) -> pd.DataFrame:
    """Expected DC/AC power for ``plant`` at ``times``.

    ``ghi`` (W/m2, indexed like ``times``) overrides clear-sky when measured/forecast irradiance
    is available; otherwise the result is the clear-sky ceiling. Returns columns
    ``ghi, poa_global, cell_temp, solar_elevation, p_dc_kw, p_ac_kw``. Night -> 0.
    Raises ``BaselineUnsupportedForTrackers`` (HTTP 422) for single-axis tracker plants.
    """
    require_fixed_tilt_baseline(plant)
    idx = _utc_index(times)
    cfg = plant_config_from_orm(plant)
    cs = clearsky_irradiance(cfg.latitude, cfg.longitude, idx, cfg.altitude)
    wx = pd.DataFrame(index=idx)
    if ghi is None:
        wx["ghi_nwp"], wx["dni_nwp"], wx["dhi_nwp"] = cs["ghi"], cs["dni"], cs["dhi"]
    else:
        wx["ghi_nwp"] = pd.Series(np.asarray(ghi, dtype=float), index=idx)
    wx["temp_ambient_nwp"] = 25.0 if temp_air is None else np.asarray(temp_air, dtype=float)
    wx["wind_speed_nwp"] = 1.5 if wind_speed is None else np.asarray(wind_speed, dtype=float)

    feats = compute_pvlib_features(wx, cfg)
    gamma = getattr(plant, "temp_coeff", -0.004)
    # Positional: the first argument was renamed across pvlib releases (g_poa_effective -> effective_irradiance).
    pdc = pvlib.pvsystem.pvwatts_dc(feats["poa_global"], feats["cell_temp"], plant.dc_kw, gamma)
    pdc = pdc * (1.0 - SYSTEM_LOSS_FRACTION) * (1.0 - float(np.clip(soiling_loss, 0.0, 1.0)))
    pdc = pdc.clip(lower=0.0)
    pdc[feats["solar_elevation"] <= 0] = 0.0
    pac = (pdc * INVERTER_EFFICIENCY).clip(upper=plant.ac_kw)
    return pd.DataFrame({
        "ghi": wx["ghi_nwp"], "poa_global": feats["poa_global"], "cell_temp": feats["cell_temp"],
        "solar_elevation": feats["solar_elevation"], "p_dc_kw": pdc, "p_ac_kw": pac,
    }, index=idx)
