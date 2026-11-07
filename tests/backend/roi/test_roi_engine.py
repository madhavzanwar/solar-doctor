"""ROI engine tests. Worked example (C&I tariff):

  expected 1000 kWh/day, attributable deficit 8 %      -> recoverable = 1000 x 0.08 = 80 kWh/day
  tariff Rs 6.5/kWh                                    -> 80 x 6.5 = Rs 520/day
  400 modules x Rs 5 = 2000; water 400 x 2 L = 800 L x Rs 0.1 = 80; labour 500
                                                       -> cleaning cost = 2000 + 80 + 500 = Rs 2580
  payback = 2580 / 520 = 4.9615 days
  V (clean production value) = 1000 x 6.5 = Rs 6500/day
"""
import math

import pytest

from solardoctor.roi import (CLEAN_NOW, WAIT, ForecastHour, RoiSettings, TARIFF_PRESETS, cleaning_cost, evaluate,
                             optimal_interval_days, payback_days, rain_outlook)


def settings(**kw):
    base = dict(module_count=400, cleaning_cost_per_module_inr=5, water_l_per_module=2, water_cost_inr_per_l=0.1,
                labour_cost_inr=500)
    base.update(kw)
    return RoiSettings(**base)  # default tariff = C&I preset 6.5


def test_presets():
    assert TARIFF_PRESETS == {"utility_ppa": 2.6, "c_and_i": 6.5, "residential": 8.0}


def test_hand_computed_example():
    r = evaluate(1000, 0.08, settings(soiling_rate_per_day=0.001))
    assert r.recoverable_kwh_day == pytest.approx(80)
    assert r.inr_per_day == pytest.approx(520)
    assert r.cleaning_cost_inr == pytest.approx(2580)
    assert r.water_l_per_clean == 800
    assert r.payback_days == pytest.approx(4.96, abs=0.005)  # 2580 / 520
    assert r.clean_value_inr_per_day == pytest.approx(6500)
    assert r.decision == CLEAN_NOW and not r.never_pays_back
    # T* = sqrt(2 x 2580 / (0.001 x 6500)) = sqrt(793.846) = 28.175 days
    assert r.optimal_interval_days == pytest.approx(28.175, abs=0.005)
    # calendar: 365/15 = 24.333 cleans/yr; smart: 365/28.175 = 12.955; saved = 800 x 11.378 = 9103 L
    assert r.water_saved_l_per_year == pytest.approx(9103, abs=2)


def test_assumptions_are_labelled():
    a = evaluate(1000, 0.08, settings()).assumptions
    assert "user assumption" in a["label"]
    assert a["tariff_inr_per_kwh"] == 6.5 and a["tariff_source"] == "preset:c_and_i"
    assert evaluate(1000, 0.08, RoiSettings(tariff_inr_per_kwh=4.0, tariff_preset=None)).assumptions["tariff_source"] == "custom"


def test_cleaning_cost_formula():
    assert cleaning_cost(settings()) == 2580


def test_wait_when_payback_too_long():
    # deficit 0.1 % -> 1 kWh x 6.5 = Rs 6.5/day; 2580 / 6.5 = 396.9 days > 30
    r = evaluate(1000, 0.001, settings())
    assert r.decision == WAIT and r.payback_days == pytest.approx(396.92, abs=0.01)


def test_tariff_zero_never_pays_back():
    r = evaluate(1000, 0.08, settings(tariff_inr_per_kwh=0.0, tariff_preset=None))
    assert r.decision == WAIT and r.never_pays_back and r.payback_days is None
    assert r.payback_label == "never pays back" and "never pays back" in r.reason
    assert r.optimal_interval_days is None  # V = 0


def test_deficit_zero_never_pays_back():
    r = evaluate(1000, 0.0, settings())
    assert r.recoverable_kwh_day == 0 and r.never_pays_back and r.decision == WAIT


def test_negative_deficit_clamped_to_zero_and_over_one_to_one():
    assert evaluate(1000, -0.2, settings()).never_pays_back
    assert evaluate(1000, 5, settings()).recoverable_kwh_day == 1000


@pytest.mark.parametrize("kwh,frac", [(None, 0.1), (1000, None), (float("nan"), 0.1), (1000, float("nan")),
                                      (float("inf"), 0.1), (-5, 0.1)])
def test_bad_inputs_degrade_to_wait(kwh, frac):
    r = evaluate(kwh, frac, settings())
    assert r.decision == WAIT and "ROI inputs missing" in r.reason and r.payback_days is None and r.incomplete


def test_unconfigured_cleaning_cost_waits_and_is_flagged():
    # Spec decision: a total cost of 0 means "nothing configured", not "free clean, pays back in 0 days".
    for s in (RoiSettings(tariff_inr_per_kwh=6.5), settings(module_count=0, labour_cost_inr=0),
              settings(cleaning_cost_per_module_inr=0, water_cost_inr_per_l=0, labour_cost_inr=0)):
        r = evaluate(1000, 0.08, s, soiling_rate_per_day=0.001)
        assert r.decision == WAIT and r.incomplete and "cleaning cost not configured" in r.reason.lower()
        assert r.payback_days is None and not r.never_pays_back and r.optimal_interval_days is None
    assert not evaluate(1000, 0.08, settings()).incomplete


def test_string_scope_saving_is_not_divided_by_module_share():
    # String: 100 kWh/day expected, PI 0.90 -> fraction 0.10 -> 10 kWh x 6.5 = Rs 65/day.
    # If the string's 10 % module share were applied again it would be Rs 6.5/day.
    r = evaluate(100, 1 - 0.90, settings(module_count=40))
    assert r.recoverable_kwh_day == pytest.approx(10) and r.inr_per_day == pytest.approx(65)


def test_nan_rate_override_falls_back_to_settings():
    r = evaluate(1000, 0.08, settings(soiling_rate_per_day=0.001), soiling_rate_per_day=float("nan"))
    assert r.soiling_rate_per_day == 0.001 and r.optimal_interval_days == pytest.approx(28.175, abs=0.005)


def test_payback_nan():
    assert payback_days(100, float("nan")) is None and payback_days(float("nan"), 5) is None


def test_soiling_rate_source_label_carried():
    r = evaluate(1000, 0.08, settings(), soiling_rate_per_day=0.002, soiling_rate_source="pvlib_kimber assumed default")
    assert r.soiling_rate_source == "pvlib_kimber assumed default"
    assert evaluate(1000, 0.08, settings(soiling_rate_per_day=0.002)).soiling_rate_source == "plant settings"


def test_payback_helper():
    assert payback_days(100, 0) is None and payback_days(100, -1) is None and payback_days(100, None) is None
    assert payback_days(100, 25) == 4


# ---- T* guards
def test_tstar_value_and_guards():
    assert optimal_interval_days(2, 0.5, 1) == pytest.approx(math.sqrt(8))  # sqrt(2*2 / (0.5*1))
    for bad in [(100, 0, 10), (100, -0.1, 10), (100, 0.01, 0), (100, 0.01, -5), (100, None, 10), (100, 0.01, None),
                (float("nan"), 0.01, 10), (-1, 0.01, 10)]:
        assert optimal_interval_days(*bad) is None


def test_tstar_zero_rate_through_evaluate():
    r = evaluate(1000, 0.08, settings(soiling_rate_per_day=0.0))
    assert r.optimal_interval_days is None and r.water_saved_l_per_year is None
    assert evaluate(1000, 0.08, settings()).optimal_interval_days is None  # rate unknown


def test_rate_override_beats_settings():
    r = evaluate(1000, 0.08, settings(soiling_rate_per_day=0.001), soiling_rate_per_day=0.004)
    assert r.optimal_interval_days == pytest.approx(math.sqrt(2 * 2580 / (0.004 * 6500)), abs=0.01)


def test_tstar_is_the_minimum_of_average_cost():
    c, r, v = 2580.0, 0.002, 6500.0
    f = lambda t: r * v * t / 2 + c / t
    t = optimal_interval_days(c, r, v)
    assert f(t) < f(t * 0.9) and f(t) < f(t * 1.1)


# ---- rain
def fc(hours, prob, temp=None):
    return [ForecastHour(h, p, temp) for h, p in zip(hours, prob)]


def test_rain_exactly_60_waits():
    r = evaluate(1000, 0.08, settings(), fc([10], [60]))
    assert r.decision == WAIT and r.rain_wait and r.rain_peak_probability_pct == 60 and r.rain_peak_hours_ahead == 10


def test_rain_59_does_not_wait():
    assert evaluate(1000, 0.08, settings(), fc([10], [59.9])).decision == CLEAN_NOW


def test_rain_at_72h_counts_73h_does_not():
    assert evaluate(1000, 0.08, settings(), fc([72], [90])).decision == WAIT
    r = evaluate(1000, 0.08, settings(), fc([73], [90]))
    assert r.decision == CLEAN_NOW and not r.rain_wait


def test_rain_ignores_bad_rows_and_past_hours():
    f = [ForecastHour(1, None), ForecastHour(2, float("nan")), ForecastHour(float("nan"), 99), ForecastHour(-1, 99)]
    assert rain_outlook(f, 60, 72) == (False, None, None)
    assert rain_outlook(None, 60, 72) == (False, None, None)


def test_rain_beats_payback_even_when_never_pays():
    assert "Rain" in evaluate(1000, 0.0, settings(), fc([5], [80])).reason


def test_settings_validation():
    for kw in (dict(tariff_inr_per_kwh=-1), dict(tariff_inr_per_kwh=float("nan")), dict(module_count=-1),
               dict(calendar_interval_days=0), dict(rain_prob_threshold_pct=101)):
        with pytest.raises(ValueError):
            RoiSettings(**kw)
