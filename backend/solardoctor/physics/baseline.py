"""Expected-power baselines for the deficit detector, driven by ``irradiance.resolve_weather`` output.

``pvwatts``: site POA if present, else GHI transposed (Erbs split + Hay-Davies); ``clearsky``: the same
chain on the Ineichen clear-sky GHI (potential); ``hybrid``: the trained SolarPulse LightGBM, when an
artifact exists. Same physics constants as ``solar.expected_power`` so the two agree.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import pvlib
from fastapi import HTTPException

from solardoctor.physics import solar
from solardoctor.physics.registry import get_registry
from solardoctor.physics.tracker import require_fixed_tilt_baseline

Baseline = Literal["clearsky", "pvwatts", "hybrid"]


class BaselineUnavailable(HTTPException):
    def __init__(self, message: str) -> None:
        super().__init__(422, detail={"status": "hybrid_model_unavailable", "message": message})


def _chain(plant, idx: pd.DatetimeIndex, ghi: pd.Series, poa: pd.Series | None, temp_air, wind) -> pd.DataFrame:
    pos = pvlib.solarposition.get_solarposition(idx, plant.lat, plant.lon, altitude=plant.altitude_m or 0.0)
    ghi = ghi.fillna(0.0).clip(lower=0.0)
    erbs = pvlib.irradiance.erbs(ghi, pos["zenith"], idx)
    transposed = pvlib.irradiance.get_total_irradiance(
        plant.tilt, plant.azimuth, pos["zenith"], pos["azimuth"],
        erbs["dni"].fillna(0.0), ghi, erbs["dhi"].fillna(0.0),
        dni_extra=pvlib.irradiance.get_extra_radiation(idx), model="haydavies")["poa_global"]
    poa_global = transposed if poa is None else poa.where(poa.notna(), transposed)  # site POA, no transposition
    poa_global = poa_global.fillna(0.0).clip(lower=0.0)
    tcell = pvlib.temperature.faiman(poa_global, temp_air, wind)
    pdc = pvlib.pvsystem.pvwatts_dc(poa_global, tcell, plant.dc_kw, plant.temp_coeff) * (1 - solar.SYSTEM_LOSS_FRACTION)
    pdc = pdc.clip(lower=0.0).where(pos["elevation"] > 0, 0.0)
    return pd.DataFrame({"p_dc_kw": pdc, "poa_global": poa_global, "cell_temp": tcell,
                         "solar_zenith": pos["zenith"]}, index=idx)


def _hybrid_dc(plant, idx: pd.DatetimeIndex, weather: pd.DataFrame, physics: pd.DataFrame) -> pd.Series:
    try:
        model = get_registry().get_model(plant_id=str(plant.id))
    except FileNotFoundError:
        raise BaselineUnavailable("No trained LightGBM artifact in ml/forecast/artifacts; train one first.") from None
    from ml.forecast.features.feature_pipeline import SolarFeaturePipeline
    erbs = pvlib.irradiance.erbs(weather["ghi"], physics["solar_zenith"], idx)
    wx = pd.DataFrame({
        "ghi_nwp": weather["ghi"], "temp_ambient_nwp": weather["temp_air"], "wind_speed_nwp": weather["wind_speed"],
        # cloud cover is not measured here: derived from the clear-sky index
        "cloud_cover_pct": (100 * (1 - weather["ghi"] / weather["ghi_clearsky"].clip(lower=1.0))).clip(0, 100),
        "dni_nwp": erbs["dni"].fillna(0.0), "dhi_nwp": erbs["dhi"].fillna(0.0)}, index=idx)
    X = SolarFeaturePipeline(solar.plant_config_from_orm(plant)).transform(wx)
    return pd.Series(np.clip(model.predict(X), 0.0, None), index=idx).where(physics["p_dc_kw"] > 0, 0.0)


def expected_power(plant, weather: pd.DataFrame, baseline: Baseline = "pvwatts") -> pd.DataFrame:
    """Expected DC/AC power (kW) for ``plant`` on the ``weather`` frame. Raises 422 for tracker plants and,
    for ``hybrid``, when no trained artifact exists."""
    require_fixed_tilt_baseline(plant)
    idx = weather.index
    if baseline == "clearsky":
        out = _chain(plant, idx, weather["ghi_clearsky"], None, weather["temp_air"], weather["wind_speed"])
    elif baseline in ("pvwatts", "hybrid"):
        out = _chain(plant, idx, weather["ghi"], weather["poa"], weather["temp_air"], weather["wind_speed"])
        if baseline == "hybrid":
            out["p_dc_kw"] = _hybrid_dc(plant, idx, weather, out)
    else:
        raise ValueError(f"unknown baseline {baseline!r}")
    pdc0 = plant.ac_kw / solar.INVERTER_EFFICIENCY
    out["p_ac_kw"] = pvlib.inverter.pvwatts(out["p_dc_kw"], pdc0, eta_inv_nom=solar.INVERTER_EFFICIENCY).clip(lower=0.0)
    return out[["p_dc_kw", "p_ac_kw", "poa_global", "cell_temp", "solar_zenith"]]
