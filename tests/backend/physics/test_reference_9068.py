"""Golden test of the pvlib-gallery OEDI 9068 chain on SYNTHETIC clear-sky inputs (not measured data).

If pvlib changes numerics, regenerate with tests/backend/physics/make_golden_9068.py and review the diff.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from solardoctor.physics import reference_9068 as ref
from solardoctor.physics.tracker import TRACKER_MARKER, is_tracker_plant

from . import make_golden_9068 as gen

GOLDEN = json.loads((Path(__file__).parent / "golden" / "oedi_9068_gallery.json").read_text())


@pytest.fixture(scope="module")
def run():
    w = gen.synthetic_weather()
    return w, ref.gallery_9068_ac_kw(w)


def test_golden_values_and_metadata(run):
    _, ac = run
    assert GOLDEN["inputs"].startswith("SYNTHETIC") and GOLDEN["pvlib_version"]
    assert [t.isoformat() for t in ac.index] == GOLDEN["ac_kw"]["index"]
    np.testing.assert_allclose(ac.to_numpy(), GOLDEN["ac_kw"]["values"], rtol=1e-6, atol=1e-5)  # atol: file rounds to 1e-6


def test_physical_sanity(run):
    w, ac = run
    r = ref.ratings()
    assert r["paco_kw"] == 1833.0 and ac.max() <= r["paco_kw"]
    poa = pd.concat([ref.run(g)[0]["poa_global"] for _, g in w.groupby(w.index.date)]).fillna(0.0)
    night = poa == 0
    assert night.any() and np.allclose(ac[night], -r["pnt_kw"])  # night: only the inverter tare loss
    for day, a in ac.groupby(ac.index.date):
        h_poa = poa[a.index].sum() * 5 / 60 / 1000          # kWh/m2 on the plane of array
        energy = a.sum() * 5 / 60                           # kWh
        # Bounds from the DC rating: no more than lossless STC yield (PR <= 1) nor than Paco running all day;
        # at least PR 0.6 (14 % pvwatts losses, inverter, temperature, clipping at DC/AC 1.3 all included).
        assert 0.6 * r["dc_stc_kw"] * h_poa <= energy <= min(r["dc_stc_kw"] * h_poa, r["paco_kw"] * 24), day


def test_gallery_geometry_answers_e13_gap():
    assert ref.GCR == pytest.approx(0.3471, abs=1e-4) and ref.MAX_ANGLE == 60 and ref.PITCH == 7
    assert (ref.MODULES_PER_STRING, ref.STRINGS_PER_INVERTER) == (15, 1344)


def test_not_a_production_baseline():
    from types import SimpleNamespace
    from solardoctor.physics import baseline
    from fastapi import HTTPException
    plant = SimpleNamespace(location=f"Colorado {TRACKER_MARKER}", name="9068")
    assert is_tracker_plant(plant)
    with pytest.raises(HTTPException) as e:
        baseline.expected_power(plant, gen.synthetic_weather().head(1), "pvwatts")
    assert e.value.detail["status"] == "baseline_unsupported_for_trackers"
