"""SIMULATED hard scenarios for the deficit detector (see deficit_synth.py for the easy suite).

Everything is synthetic (source="SIMULATED"). Harder than the easy suite: 2.5 % multiplicative noise on
every string's power, 1.5 % on the GHI sensor, and a messier world per scenario. Truth is defined explicitly
in ``truth_for``. Truth model = ``solar.expected_power`` (original pvlib chain); detector = ``baseline`` chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy import insert

from solardoctor.physics import deficit, solar
from solardoctor.physics.models import Inverter, Plant, PvString, Telemetry

from . import deficit_synth as ds

NOISE_P, NOISE_G = 0.025, 0.015
SCENARIOS = ("control_hard", "slow_soiling", "just_under", "partly_cloudy", "clipping_day", "clipping_string",
             "gaps_and_stuck", "time_offset", "one_of_many", "jitter", "control_nasa", "cloudy_nasa")
SOILING_DAYS, SOILING_FINAL = 14, 0.08
FAULT = {"just_under": 0.03, "one_of_many": 0.08, "jitter": 0.20, "clipping_string": 0.10}
ONE_OF_MANY_STRINGS = 24
SENSOR_LAG_MIN = 7  # partly_cloudy: the GHI sensor sits away from the array, clouds reach it later


@dataclass
class Truth:
    strings: dict[int, float] = field(default_factory=dict)  # string index -> fractional loss
    soiling: bool = False
    t4: pd.Timestamp | None = None   # slow soiling: true plant loss reaches 4 % (earlier alerts are premature)
    t5: pd.Timestamp | None = None   # ... reaches 5 % (alert expected from here)
    peer_notice_ok: bool = False     # just_under: an INFO peer notice on the faulty string is not a false positive
    offset_min: int = 0


def make_plant(db, n_strings: int = 8):
    plant = Plant(name="Synthetic plant (SIMULATED)", lat=18.52, lon=73.86, tz="Asia/Kolkata", altitude_m=560.0,
                  tilt=20.0, azimuth=180.0, dc_kw=400.0, ac_kw=360.0, module_count=n_strings * ds.MODULES,
                  source=ds.SOURCE, location="Pune")
    db.add(plant)
    db.flush()
    n_inv = 2 if n_strings == 8 else 3
    invs = [Inverter(plant_id=plant.id, name=f"INV-{i + 1}", ac_kw=360.0 / n_inv) for i in range(n_inv)]
    db.add_all(invs)
    db.flush()
    per = n_strings // n_inv
    strs = [PvString(plant_id=plant.id, inverter_id=invs[min(i // per, n_inv - 1)].id, name=f"S-{i + 1:02d}",
                     module_count=ds.MODULES) for i in range(n_strings)]
    db.add_all(strs)
    db.flush()
    return plant, invs, strs


def _days(scenario):
    return SOILING_DAYS if scenario == "slow_soiling" else 4 if scenario == "partly_cloudy" else 3


def _broken_clouds(rng, plant, times):
    """1-minute AR(1) cloud field (ramps of minutes); returns (array GHI at 15-min label, sensor GHI) both
    averaged over a 15-minute window centred on the label."""
    mins = pd.date_range(times[0] - pd.Timedelta(minutes=8), times[-1] + pd.Timedelta(minutes=8), freq="1min")
    z = np.zeros(len(mins))
    for i in range(1, len(mins)):
        z[i] = 0.97 * z[i - 1] + rng.normal(0, 0.25)
    k = np.clip(0.6 + 0.9 * z, 0.12, 1.0)
    ghi = pd.Series(k * ds.irradiance_clearsky(plant, mins), index=mins)
    avg = lambda s: s.rolling(15, center=True, min_periods=1).mean().reindex(times)
    return avg(ghi), avg(ghi.shift(SENSOR_LAG_MIN, fill_value=0.0))


def nasa_fetch_for(plant, ghi_true: pd.Series, t_air, rng):
    """NASA-style hourly mocked product: hourly mean of the true GHI with a satellite-like error that grows
    with cloudiness (3 % clear, up to ~33 % overcast). Assumption of this simulation, not a NASA statistic."""
    hourly = ghi_true.resample("1h").mean()
    cs = ds.irradiance_clearsky(plant, hourly.index)
    kc = (hourly / np.maximum(cs, 20.0)).clip(0, 1.2)
    sigma = 0.03 + 0.3 * (1 - kc.clip(0, 1))
    ghi = hourly * (1 + rng.normal(0, 1, len(hourly)) * sigma)
    df = pd.DataFrame({"ghi": ghi.clip(lower=0), "temp_air": pd.Series(t_air, index=ghi_true.index).resample("1h").mean(),
                       "wind_speed": 2.0, "precip_mm": 0.0}, index=hourly.index)
    return lambda *a, **k: df



def populate(db, plant, invs, strs, scenario: str, seed: int):
    """Insert telemetry for ``scenario``; return (Truth, nasa_fetch or None)."""
    rng = np.random.default_rng(seed)
    n_days = _days(scenario)
    times = pd.date_range(ds.START, periods=n_days * 96, freq="15min")
    n, ns = len(times), len(strs)
    truth = Truth()
    nasa = None

    if scenario == "partly_cloudy":
        ghi_arr, ghi_sensor = _broken_clouds(rng, plant, times)
        ghi_arr, ghi_sensor = ghi_arr.to_numpy(), ghi_sensor.to_numpy()
    else:
        k = ds.clearness(rng, times, (1,) if scenario == "cloudy_nasa" else ())
        ghi_arr = ghi_sensor = k * ds.irradiance_clearsky(plant, times)
    ghi_sensor = ghi_sensor * (1 + rng.normal(0, NOISE_G, n))
    t_air = 25 + 8 * np.sin((times.hour + times.minute / 60 - 6) / 24 * 2 * np.pi)
    wind = np.full(n, 2.0)
    cfg = plant
    if scenario == "clipping_day" or scenario == "clipping_string":
        plant.dc_kw = 560.0  # DC/AC 1.56: the inverters clip around midday
    ex = solar.expected_power(cfg, times, ghi=pd.Series(ghi_arr, index=times), temp_air=t_air, wind_speed=wind)

    loss_t = np.zeros(n)
    if scenario == "slow_soiling":
        frac = np.arange(n) / (SOILING_DAYS * 96)
        loss_t = SOILING_FINAL * frac
        truth.soiling = True
        truth.t4 = times[0] + pd.Timedelta(days=SOILING_DAYS * 0.04 / SOILING_FINAL)
        truth.t5 = times[0] + pd.Timedelta(days=SOILING_DAYS * 0.05 / SOILING_FINAL)
    if scenario in FAULT:
        truth.strings[int(rng.integers(ns))] = FAULT[scenario]
        truth.peer_notice_ok = scenario == "just_under"
    if scenario == "time_offset":
        truth.offset_min = 60

    share = ex["p_dc_kw"].to_numpy() / ns
    s_dc = np.array([share * (1 - truth.strings.get(i, 0.0)) * (1 - loss_t) * rng.normal(1.0, NOISE_P, n)
                     for i in range(ns)])
    n_inv = len(invs)
    per = ns // n_inv
    inv_of = [min(i // per, n_inv - 1) for i in range(ns)]
    limit = 360.0 / n_inv
    for j in range(n_inv):  # an inverter at its AC limit pulls the DC operating point down
        sel = [i for i in range(ns) if inv_of[i] == j]
        f = np.minimum(1.0, limit / np.maximum(s_dc[sel].sum(axis=0) * solar.INVERTER_EFFICIENCY, 1e-9))
        s_dc[sel] *= f
    s_ac = s_dc * solar.INVERTER_EFFICIENCY
    inv_ac = [s_ac[[i for i in range(ns) if inv_of[i] == j]].sum(axis=0) for j in range(n_inv)]
    plant_ac = sum(inv_ac)

    nan = {}  # channel -> boolean mask of NaN samples
    day = np.asarray((times - times[0].normalize()) / pd.Timedelta(days=1)).astype(int)
    hr = times.hour.to_numpy() + times.minute.to_numpy() / 60
    all_nan = np.zeros(n, bool)
    ghi_nan = np.zeros(n, bool)
    if scenario == "gaps_and_stuck":
        gap = lambda d, h0, h1: (day == d) & (hr >= h0) & (hr < h1)
        all_nan = gap(0, 3, 7)                                     # logger outage, 4 h
        for i in rng.choice(ns, 3, replace=False):                 # channel dropouts 2-3 h
            nan[("string", int(i))] = gap(1, 2, 4.5)
        ghi_nan = gap(2, 5, 7)
        stuck = gap(1, 4, 10)                                      # GHI sensor flatlined half a day
        ghi_sensor = ghi_sensor.copy()
        ghi_sensor[stuck] = ghi_sensor[np.flatnonzero(stuck)[0]]
        i_stuck = int(rng.integers(ns))                            # one string's power channel flatlined 5 h
        fl = np.flatnonzero(gap(2, 7.5, 12.5))
        s_dc[i_stuck, fl] = s_dc[i_stuck, fl[0]]
        s_ac[i_stuck, fl] = s_ac[i_stuck, fl[0]]

    shift = pd.Timedelta(hours=1) if scenario == "time_offset" else pd.Timedelta(0)
    chan = [(None, None, plant_ac, None, "plant")] + [(invs[j].id, None, inv_ac[j], None, "inv") for j in range(n_inv)]
    chan += [(strs[i].inverter_id, strs[i].id, s_ac[i], s_dc[i], ("string", i)) for i in range(ns)]
    frames = []
    for inv_id, sid, ac, dc, tag in chan:
        m = all_nan | nan.get(tag, np.zeros(n, bool)) if isinstance(tag, tuple) else all_nan
        off = (rng.integers(0, 60, n) if scenario == "jitter" else np.zeros(n, int))
        frames.append(pd.DataFrame({
            "ts": [(t + shift + pd.Timedelta(seconds=int(o))).to_pydatetime() for t, o in zip(times, off)],
            "plant_id": plant.id, "inverter_id": inv_id, "string_id": sid,
            "p_ac_kw": np.where(m, np.nan, ac), "p_dc_kw": np.nan if dc is None else np.where(m, np.nan, dc),
            "ghi_wm2": np.nan if scenario.endswith("nasa") else np.where(all_nan | ghi_nan, np.nan, ghi_sensor),
            "t_amb": t_air, "wind_ms": 2.0, "curtailed": False, "source": ds.SOURCE}))
    df = pd.concat(frames, ignore_index=True)
    recs = [{k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()}
            for r in df.to_dict("records")]
    db.execute(insert(Telemetry), recs)
    db.commit()
    if scenario.endswith("nasa"):
        nasa = nasa_fetch_for(plant, pd.Series(ghi_arr, index=times), t_air, rng)
    return truth, nasa


def scan(db, plant, scenario: str, nasa=None, baseline: str = "pvwatts"):
    def down(*a, **k):
        raise TimeoutError("NASA POWER down (simulated)")
    return deficit.scan_and_persist(db, plant.id, ds.START, ds.START + pd.Timedelta(days=_days(scenario)) + pd.Timedelta(hours=2),
                                    baseline, now=ds.NOW, nasa_fetch=nasa or down)


def run(scenario: str, seed: int, db=None):
    """Fresh plant + telemetry + scan. Returns (result, truth, string_ids, plant)."""
    db = db or ds.temp_session()
    ds._KEEP.append(db)
    plant, invs, strs = make_plant(db, ONE_OF_MANY_STRINGS if scenario == "one_of_many" else ds.N_STRINGS)
    truth, nasa = populate(db, plant, invs, strs, scenario, seed)
    return scan(db, plant, scenario, nasa), truth, [s.id for s in strs], plant


def judge(scenario, res, truth, sids) -> dict:
    """Apply the truth rules. Returns tp/fp/fn counts for 'any severity' and 'WARNING+', peer notices, delay."""
    ev = res["events"]
    want = {("string", sids[i]) for i in truth.strings} if scenario != "just_under" else set()
    if truth.soiling:
        want = {("plant", None)}
    out = {"notice": 0, "delay_days": None, "premature": False}
    for mode, keep in (("any", lambda e: True), ("warn", lambda e: e.severity != "INFO")):
        got = {}
        for e in ev:
            if not keep(e):
                continue
            key = (e.scope, e.scope_id)
            if truth.peer_notice_ok and e.severity == "INFO" and key == ("string", sids[next(iter(truth.strings))]):
                continue
            if truth.soiling and e.start < truth.t4:
                out["premature"] = True
                continue  # premature: false positive, and the plant is not validly detected
            got[key] = e
        out[mode] = {"tp": len(want & set(got)), "fp": len(set(got) - want), "fn": len(want - set(got)),
                     "fp_premature": int(out["premature"])}
        if out["premature"]:
            out[mode]["fp"] += 1
            out[mode]["fn"] = len(want)
    if truth.peer_notice_ok:
        out["notice"] = sum(1 for e in ev if e.severity == "INFO" and e.scope == "string" and
                            e.scope_id == sids[next(iter(truth.strings))])
    if truth.soiling:
        plant_ev = [e for e in ev if e.scope == "plant"]
        if plant_ev:
            out["delay_days"] = (min(e.start for e in plant_ev) - truth.t5) / pd.Timedelta(days=1)
    out["qc_status"] = res.get("qc_status")
    return out
