"""Reference model: pvlib gallery "4.7 MW CdTe single-axis tracking (OEDI System 9068)", one inverter.

Follows docs/examples/system-models/plot_oedi_9068.py of pvlib-python (BSD-3-Clause, (c) 2023 pvlib python
Developers; see THIRD_PARTY_NOTICES.md): same system parameters and model chain, with the NSRDB download replaced by
caller-supplied weather. It is a REFERENCE for tests and for the tracker-baseline follow-up (DECISIONS P2-7); it is
NOT a production baseline, and tracker plants still get no deficit alerts (DECISIONS E13).

Deviations from the gallery: (1) the Prilliman cell-temperature model restarts every UTC day (it needs equal time
steps), so the thermal history is lost at 00:00 UTC; (2) night output is the inverter tare loss (negative AC power,
-Pnt) as the gallery's inverter model returns it, not zero.

``weather`` columns (UTC DatetimeIndex, W/m2 / C / m/s / cm): ghi, dni, dhi, temp_air, wind_speed, precipitable_water,
albedo.
"""
from __future__ import annotations

import pandas as pd
import pvlib

LAT, LON = 40.3864, -104.5512
MODULES_PER_STRING, STRINGS_PER_INVERTER = 15, 1344
MODULE_NAME, INVERTER_NAME = "First_Solar__Inc__FS_4117_3", "TMEIC__PVL_L1833GRM"
TEMPERATURE_MODEL = dict(u0=25.0, u1=6.84)  # Faiman
MODULE_UNIT_MASS = 12 / 0.72  # kg/m2
PITCH, AXIS_HEIGHT, MAX_ANGLE = 7.0, 1.5, 60.0
GCR = (4 * 0.6 + 3 * 0.01) / PITCH


def _system():
    module = pvlib.pvsystem.retrieve_sam("CECMod")[MODULE_NAME].copy()
    module["Technology"] = "CdTe"
    inverter = pvlib.pvsystem.retrieve_sam("CECInverter")[INVERTER_NAME]
    mount = pvlib.pvsystem.SingleAxisTrackerMount(axis_tilt=0, axis_azimuth=180, max_angle=MAX_ANGLE, backtrack=False, gcr=GCR)
    array = pvlib.pvsystem.Array(mount, module_parameters=module, temperature_model_parameters=TEMPERATURE_MODEL,
                                 modules_per_string=MODULES_PER_STRING, strings=STRINGS_PER_INVERTER)
    system = pvlib.pvsystem.PVSystem(arrays=[array], inverter_parameters=inverter,
                                     losses_parameters=dict(shading=0, availability=0))
    return module, inverter, system


def ratings() -> dict:
    """STC DC rating and AC rating of the one-inverter block (kW)."""
    module, inverter, _ = _system()
    return {"dc_stc_kw": module["STC"] * MODULES_PER_STRING * STRINGS_PER_INVERTER / 1000.0,
            "paco_kw": float(inverter["Paco"]) / 1000.0, "pnt_kw": float(inverter["Pnt"]) / 1000.0}


def run(weather: pd.DataFrame, altitude: float = 0.0) -> tuple[pd.DataFrame, pd.Series]:
    """(front-side POA components, AC power kW) for one inverter."""
    _, _, system = _system()
    location = pvlib.location.Location(LAT, LON, altitude=altitude)
    times = weather.index
    sp = location.get_solarposition(times)
    tracker = pvlib.tracking.singleaxis(sp["apparent_zenith"], sp["azimuth"], axis_tilt=0, axis_azimuth=180,
                                        max_angle=MAX_ANGLE, backtrack=False, gcr=GCR)
    poa = pvlib.bifacial.infinite_sheds.get_irradiance_poa(
        surface_tilt=tracker["surface_tilt"], surface_azimuth=tracker["surface_azimuth"],
        solar_zenith=sp["apparent_zenith"], solar_azimuth=sp["azimuth"], gcr=GCR, height=AXIS_HEIGHT, pitch=PITCH,
        ghi=weather["ghi"], dhi=weather["dhi"], dni=weather["dni"], albedo=weather["albedo"], model="haydavies",
        dni_extra=pvlib.irradiance.get_extra_radiation(times))
    steady = pvlib.temperature.faiman(poa["poa_global"], weather["temp_air"], weather["wind_speed"], **TEMPERATURE_MODEL)
    cell = pvlib.temperature.prilliman(steady, weather["wind_speed"], unit_mass=MODULE_UNIT_MASS)
    mc = pvlib.modelchain.ModelChain(system, location, spectral_model="first_solar", aoi_model="physical",
                                     losses_model="pvwatts")
    mc.run_model_from_poa(pd.DataFrame({
        "poa_global": poa["poa_global"], "poa_direct": poa["poa_direct"], "poa_diffuse": poa["poa_diffuse"],
        "cell_temperature": cell, "precipitable_water": weather["precipitable_water"]}, index=times))
    return poa, mc.results.ac / 1000.0


def gallery_9068_ac_kw(weather: pd.DataFrame) -> pd.Series:
    """AC power (kW) of one 9068 inverter following the pvlib gallery chain. Night values are the inverter tare loss.

    Each UTC day is run on its own: pvlib's Prilliman cell-temperature model needs equal time steps, so a series
    with gaps is split (every day starts at steady-state temperature).
    """
    return pd.concat([run(g)[1] for _, g in weather.groupby(weather.index.date)]).rename("ac_kw")
