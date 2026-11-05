"""Physics-based telemetry simulation (no DB).

Telemetry = the repo's own pvlib/PVWatts expected-power model (``physics.solar.expected_power``)
evaluated on the *true* (NASA or synthetic) irradiance, then degraded by injected, labelled events:

* plant-wide soiling ramp (linear %/day, reset on cleaning days),
* one string fault (PCCoE S-04) from a start day,
* ~1 % multiplicative measurement noise,
* the cloudy spell is applied to the irradiance itself, so expected power sees it too.

Because the baseline and the generator share the physics model, a performance index of ~1.0 on
healthy strings is by construction; what the seed exercises is the detection pipeline, not model
accuracy.  Every row is labelled SIMULATED.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from solardoctor.physics import solar
from solardoctor.physics.models import Plant
from solardoctor.seed.specs import PlantSpec, SOURCE, TZ

STEP_MIN = 15
NOISE_SIGMA = 0.01


def transient_plant(spec: PlantSpec) -> Plant:
    """Unpersisted Plant ORM object carrying the spec's physical parameters."""
    return Plant(
        name=spec.name, location=spec.location, lat=spec.lat, lon=spec.lon, tz=TZ,
        altitude_m=spec.altitude_m, tilt=spec.tilt, azimuth=spec.azimuth,
        dc_kw=spec.dc_kw, ac_kw=spec.ac_kw, module_count=spec.module_count,
        module_wp=spec.module_wp, temp_coeff=spec.temp_coeff,
        tariff_inr_kwh=spec.tariff_inr_kwh, source=SOURCE,
    )


def window_index(start: pd.Timestamp, days: int = 30) -> pd.DatetimeIndex:
    start = pd.Timestamp(start)
    start = start.tz_localize("UTC") if start.tz is None else start.tz_convert("UTC")
    return pd.date_range(start.normalize(), periods=days * 24 * 60 // STEP_MIN, freq=f"{STEP_MIN}min")


def soiling_fraction(spec: PlantSpec, times: pd.DatetimeIndex) -> np.ndarray:
    """Soiling loss (fraction) at each time: linear ramp, reset at the start of each cleaning day."""
    t0 = times[0].normalize()
    days = np.asarray((times - t0) / pd.Timedelta(days=1), dtype=float)
    since = days.copy()
    level0 = spec.soiling_start_pct
    out = (level0 + spec.soiling_rate_pct_day * since)
    for c in sorted(spec.cleaning_days):
        m = days >= c
        out = np.where(m, spec.soiling_rate_pct_day * (days - c), out)
    return np.clip(out / 100.0, 0.0, 0.5)


@dataclass
class GroupSeries:
    name: str          # string name, or "ALL"
    inverter: int
    share: float       # module share of the plant
    p_dc_kw: np.ndarray
    p_expected_dc_kw: np.ndarray  # clean-physics share, per group


@dataclass
class PlantSim:
    spec: PlantSpec
    times: pd.DatetimeIndex
    clean: pd.DataFrame            # physics expected (clean, no soiling): ghi, poa_global, cell_temp, p_dc_kw, p_ac_kw
    temp_air: np.ndarray
    wind: np.ndarray
    soiling: np.ndarray
    groups: list[GroupSeries] = field(default_factory=list)
    inv_ac_kw: dict[int, np.ndarray] = field(default_factory=dict)
    plant_ac_kw: np.ndarray = field(default_factory=lambda: np.zeros(0))
    plant_dc_kw: np.ndarray = field(default_factory=lambda: np.zeros(0))


def simulate_plant(spec: PlantSpec, times: pd.DatetimeIndex, irr: pd.DataFrame, seed: int) -> PlantSim:
    rng = np.random.default_rng(seed)
    plant = transient_plant(spec)
    clean = solar.expected_power(plant, times, ghi=irr["ghi"], temp_air=irr["temp_air"],
                                 wind_speed=irr["wind_speed"])
    s = soiling_fraction(spec, times)
    day_no = np.asarray((times - times[0].normalize()) / pd.Timedelta(days=1), dtype=float)

    groups_spec = spec.strings or ()
    if not groups_spec:
        from solardoctor.seed.specs import StringSpec
        groups_spec = (StringSpec("ALL", 0, spec.module_count),)
    total_modules = sum(g.modules for g in groups_spec)
    sim = PlantSim(spec=spec, times=times, clean=clean, temp_air=irr["temp_air"].to_numpy(),
                   wind=irr["wind_speed"].to_numpy(), soiling=s)
    dc_clean = clean["p_dc_kw"].to_numpy()
    for g in groups_spec:
        share = g.modules / total_modules
        fault = np.where(day_no >= g.fault_start_day, g.fault_loss, 0.0) if g.fault_loss else 0.0
        noise = rng.normal(1.0, NOISE_SIGMA, len(times))
        p_dc = np.where(dc_clean > 0, dc_clean * share * (1.0 - s) * (1.0 - fault) * noise, 0.0)
        sim.groups.append(GroupSeries(g.name, g.inverter, share, np.clip(p_dc, 0.0, None), dc_clean * share))

    n_inv = max(1, max(g.inverter for g in groups_spec) + 1) if spec.strings else 1
    ac_per_inv = spec.ac_kw / n_inv
    plant_ac = np.zeros(len(times))
    for inv in range(n_inv):
        dc = sum(g.p_dc_kw for g in sim.groups if g.inverter == inv)
        ac = np.minimum(dc * solar.INVERTER_EFFICIENCY, ac_per_inv)
        sim.inv_ac_kw[inv] = ac
        plant_ac += ac
    sim.plant_ac_kw = plant_ac
    sim.plant_dc_kw = sum(g.p_dc_kw for g in sim.groups)
    return sim


def telemetry_rows(sim: PlantSim, plant_id: int, inverter_ids: dict[int, int], string_ids: dict[str, int]) -> list[dict]:
    """Flat telemetry rows (plant, inverter and string level) for bulk insert."""
    t = sim.times
    c = sim.clean
    common = dict(poa=c["poa_global"].to_numpy(), ghi=c["ghi"].to_numpy(),
                  tmod=c["cell_temp"].to_numpy(), tamb=sim.temp_air, wind=sim.wind)
    ts_py = [x.to_pydatetime() for x in t]
    exp_ac = c["p_ac_kw"].to_numpy()

    def f(x):
        return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

    rows: list[dict] = []

    def add(i, inv_id, str_id, p_ac, p_dc, p_exp):
        rows.append(dict(
            ts=ts_py[i], plant_id=plant_id, inverter_id=inv_id, string_id=str_id,
            p_ac_kw=f(p_ac), p_dc_kw=f(p_dc), v=None, i=None,
            poa_wm2=f(common["poa"][i]), ghi_wm2=f(common["ghi"][i]), t_amb=f(common["tamb"][i]),
            t_mod=f(common["tmod"][i]), wind_ms=f(common["wind"][i]),
            p_expected_kw=f(p_exp), source=SOURCE,
        ))

    string_level = bool(sim.spec.strings)
    for i in range(len(t)):
        add(i, None, None, sim.plant_ac_kw[i], sim.plant_dc_kw[i], exp_ac[i])
    if string_level:
        n_inv = len(sim.inv_ac_kw)
        for inv, ac in sim.inv_ac_kw.items():
            dc_inv = sum(g.p_dc_kw for g in sim.groups if g.inverter == inv)
            exp_inv = np.minimum(sum(g.p_expected_dc_kw for g in sim.groups if g.inverter == inv)
                                 * solar.INVERTER_EFFICIENCY, sim.spec.ac_kw / n_inv)
            for i in range(len(t)):
                add(i, inverter_ids[inv], None, ac[i], dc_inv[i], exp_inv[i])
        for g in sim.groups:
            sid = string_ids[g.name]
            exp_dc = g.p_expected_dc_kw  # clean physics DC (system losses already included by solar.expected_power)
            for i in range(len(t)):
                add(i, inverter_ids[g.inverter], sid, g.p_dc_kw[i] * solar.INVERTER_EFFICIENCY, g.p_dc_kw[i],
                    exp_dc[i] * solar.INVERTER_EFFICIENCY)
    return rows
