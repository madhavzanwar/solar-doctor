"""Generalized single-axis tracker baseline model.

Extends the PVDAQ 9068 reference model to arbitrary single-axis tracker solar plants
using pvlib's astronomical solar position, backtracking, and singleaxis tracking geometry.
"""
from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd
import pvlib


def compute_tracker_expected_power(
    plant,
    times: pd.DatetimeIndex,
    ghi: pd.Series,
    dni: Optional[pd.Series] = None,
    dhi: Optional[pd.Series] = None,
    temp_air: Optional[pd.Series] = None,
    wind_speed: Optional[pd.Series] = None,
    axis_tilt: float = 0.0,
    axis_azimuth: float = 180.0,
    max_angle: float = 60.0,
    gcr: float = 0.35,
    backtrack: bool = True,
) -> pd.DataFrame:
    """Compute expected AC and DC power for a single-axis tracker plant across times.

    Returns DataFrame indexed by times with columns:
    [ghi, poa_global, tracker_tilt, tracker_azimuth, cell_temp, p_dc_kw, p_ac_kw].
    """
    lat = getattr(plant, "latitude", None) or getattr(plant, "lat", 18.65)
    lon = getattr(plant, "longitude", None) or getattr(plant, "lon", 73.76)
    alt = getattr(plant, "altitude_m", 0.0) or 0.0
    dc_kw = getattr(plant, "capacity_kw", None) or getattr(plant, "dc_kw", 100.0)
    ac_kw = getattr(plant, "inverter_capacity_kw", None) or getattr(plant, "ac_kw", 90.0)

    if times.tz is None:
        times = times.tz_localize("UTC")
    else:
        times = times.tz_convert("UTC")

    loc = pvlib.location.Location(lat, lon, altitude=alt)
    sp = loc.get_solarposition(times)

    # Decompose GHI if DNI/DHI not provided
    if dni is None or dhi is None:
        erbs = pvlib.irradiance.erbs(ghi, sp["apparent_zenith"], times)
        dni = erbs["dni"].fillna(0.0)
        dhi = erbs["dhi"].fillna(0.0)

    tracker = pvlib.tracking.singleaxis(
        sp["apparent_zenith"],
        sp["azimuth"],
        axis_tilt=axis_tilt,
        axis_azimuth=axis_azimuth,
        max_angle=max_angle,
        backtrack=backtrack,
        gcr=gcr,
    )

    surface_tilt = tracker["surface_tilt"].fillna(0.0)
    surface_azimuth = tracker["surface_azimuth"].fillna(axis_azimuth)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        solar_zenith=sp["apparent_zenith"],
        solar_azimuth=sp["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
    )

    t_amb = 25.0 if temp_air is None else temp_air
    w_spd = 1.5 if wind_speed is None else wind_speed

    cell_temp = pvlib.temperature.faiman(poa["poa_global"], t_amb, w_spd)
    gamma = getattr(plant, "temp_coeff", -0.004) or -0.004

    pdc = pvlib.pvsystem.pvwatts_dc(poa["poa_global"], cell_temp, dc_kw, gamma)
    pdc = pdc.clip(lower=0.0)
    pdc[sp["apparent_zenith"] >= 90.0] = 0.0

    inverter_eff = 0.96
    pac = (pdc * inverter_eff).clip(upper=ac_kw)

    return pd.DataFrame({
        "ghi": ghi,
        "poa_global": poa["poa_global"],
        "tracker_tilt": surface_tilt,
        "tracker_azimuth": surface_azimuth,
        "cell_temp": cell_temp,
        "p_dc_kw": pdc,
        "p_ac_kw": pac,
    }, index=times)
