"""Regenerate golden/oedi_9068_gallery.json (SYNTHETIC clear-sky inputs through the pvlib-gallery 9068 chain).

    PYTHONSAFEPATH=1 PYTHONPATH="backend;." python tests/backend/physics/make_golden_9068.py
"""
import json
from pathlib import Path

import pandas as pd
import pvlib

from solardoctor.physics import reference_9068 as ref

DAYS = {"june": "2024-06-21", "december": "2024-12-21", "march": "2024-03-20"}
ALTITUDE_M = 0.0
PATH = Path(__file__).parent / "golden" / "oedi_9068_gallery.json"


def synthetic_weather() -> pd.DataFrame:
    """Three UTC days at 5 min: Ineichen clear-sky at the site, albedo 0.2, pw 1.0 cm, 20 C, 2 m/s."""
    times = pd.DatetimeIndex([t for d in DAYS.values() for t in pd.date_range(d, periods=288, freq="5min", tz="UTC")])
    cs = pvlib.location.Location(ref.LAT, ref.LON, altitude=ALTITUDE_M).get_clearsky(times, model="ineichen")
    return pd.DataFrame({"ghi": cs["ghi"], "dni": cs["dni"], "dhi": cs["dhi"], "temp_air": 20.0, "wind_speed": 2.0,
                         "precipitable_water": 1.0, "albedo": 0.2}, index=times)


def build() -> dict:
    w = synthetic_weather()
    ac = ref.gallery_9068_ac_kw(w)
    return {"inputs": "SYNTHETIC clear-sky (pvlib Ineichen), not measured data", "pvlib_version": pvlib.__version__,
            "site": {"lat": ref.LAT, "lon": ref.LON, "altitude_m": ALTITUDE_M},
            "weather": {"albedo": 0.2, "precipitable_water_cm": 1.0, "temp_air_c": 20.0, "wind_ms": 2.0},
            "days": DAYS, "freq": "5min", "ratings": ref.ratings(),
            "ac_kw": {"index": [t.isoformat() for t in ac.index], "values": [round(float(v), 6) for v in ac]}}


if __name__ == "__main__":
    data = build()
    PATH.write_text(json.dumps(data, separators=(",", ":")))
    print("wrote", PATH, len(data["ac_kw"]["values"]), "points; pvlib", data["pvlib_version"], data["ratings"])
