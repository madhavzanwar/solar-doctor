"""Harder SIMULATED scenarios (deficit_synth_hard.py): fast deterministic seed per scenario + review-fix regressions."""
from functools import cache

import pytest

from . import deficit_synth_hard as hs

SEED = 100


@cache
def _run(scenario, seed=SEED):
    return hs.run(scenario, seed)


def test_timestamp_jitter_is_binned_and_string_fault_found():
    res, truth, sids, _ = _run("jitter")
    (idx,) = truth.strings
    assert res["provenance"] == {"site_sensor": res["provenance"]["site_sensor"]}  # site GHI matched, not NASA/model
    assert [(e.scope, e.scope_id, e.severity) for e in res["events"]] == [("string", sids[idx], "CRITICAL")]
