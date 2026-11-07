"""One test per decision-table row, precedence tests, and edge cases."""
import pytest

from solardoctor.fusion import (CLASSES, FusionSettings, PhotoEvidence, Severity, TelemetryEvidence, fuse,
                                load_rules)
from solardoctor.roi import ForecastHour, RoiSettings

ROI = RoiSettings.from_preset("c_and_i", module_count=400, cleaning_cost_per_module_inr=5, water_l_per_module=2,
                              water_cost_inr_per_l=0.1, labour_cost_inr=500)
S = FusionSettings(roi=ROI)


def tel(deficit="WARNING", **kw):
    base = dict(status="ok", usable_clear_hours=6, deficit_severity=deficit, deviation_percent=8.0,
                expected_kwh_day=1000, attributable_deficit_fraction=0.08)
    base.update(kw)
    return TelemetryEvidence(**base)


def ph(cls, conf=0.9, **kw):
    return PhotoEvidence(predicted_class=cls, confidence=conf, **kw)


def test_table_matches_spec_rows():
    spec = [r["id"] for r in load_rules() if r["precedence"] < 100]
    assert spec == ["unclear_photo", "inconclusive", "soiling_confirmed", "snow_loss", "electrical_suspected",
                    "hardware_fault", "early_soiling", "latent_damage"]
    assert load_rules() is load_rules()  # loaded once


# ---- one test per row
@pytest.mark.parametrize("cls", ["dusty", "bird_drop"])
def test_row_soiling_clean_now(cls):
    v = fuse(tel(), ph(cls), S)
    assert (v.rule_id, v.verdict, v.action) == ("soiling_confirmed", "Soiling confirmed", "CLEAN NOW")
    assert v.severity is Severity.HIGH and v.roi is not None and v.roi.decision == "CLEAN NOW"
    assert v.confidence == 0.9 and "8.0%" in v.reason


def test_row_soiling_wait_when_rain():
    v = fuse(tel(), ph("dusty"), S, forecast=[ForecastHour(12, 70)])
    assert v.rule_id == "soiling_confirmed" and v.action == "WAIT" and v.severity is Severity.LOW
    assert "Rain" in v.reason


def test_row_soiling_critical_telemetry_with_clean_now_is_critical():
    assert fuse(tel("CRITICAL"), ph("dusty"), S).severity is Severity.CRITICAL


def test_critical_telemetry_with_rain_wait_is_not_critical():
    v = fuse(tel("CRITICAL"), ph("dusty"), S, forecast=[ForecastHour(12, 70)])
    assert v.action == "WAIT" and v.severity is Severity.LOW


def test_soiling_rate_source_reaches_roi():
    v = fuse(tel(soiling_loss_rate_per_day=0.001, soiling_rate_source="pvlib_kimber assumed default"), ph("dusty"), S)
    assert v.roi.soiling_rate_source == "pvlib_kimber assumed default"


def test_nan_usable_hours_is_unknown():
    nan = float("nan")
    assert fuse(TelemetryEvidence(usable_clear_hours=nan), ph("dusty"), S).rule_id == "inconclusive"
    assert fuse(TelemetryEvidence(usable_clear_hours=nan, deficit_severity="WARNING"), ph("clean"), S).rule_id         == "electrical_suspected"


def test_rules_are_immutable():
    row = load_rules()[0]
    with pytest.raises(TypeError):
        row["verdict"] = "x"
    assert isinstance(load_rules()[2]["photo"], tuple)


def test_soiling_uses_telemetry_rate_for_tstar():
    v = fuse(tel(soiling_loss_rate_per_day=0.001), ph("dusty"), S)
    assert v.roi.optimal_interval_days == pytest.approx(28.18, abs=0.01)


def test_row_snow_wait_on_melt_forecast():
    v = fuse(tel(), ph("snow_covered"), S, forecast=[ForecastHour(6, 0, 5.0)])
    assert (v.rule_id, v.verdict, v.action, v.severity) == ("snow_loss", "Snow loss", "WAIT", Severity.MEDIUM)


def test_row_snow_clear_if_safe_without_melt():
    cold = fuse(tel(), ph("snow_covered"), S, forecast=[ForecastHour(6, 0, -3.0)])
    none = fuse(tel(), ph("snow_covered"), S)
    far = fuse(tel(), ph("snow_covered"), S, forecast=[ForecastHour(60, 0, 10.0)])  # beyond 48 h window
    assert cold.action == none.action == far.action == "CLEAR IF SAFE"


def test_snow_melt_threshold_inclusive():
    assert fuse(tel(), ph("snow_covered"), S, forecast=[ForecastHour(1, 0, 2.0)]).action == "WAIT"
    assert fuse(tel(), ph("snow_covered"), S, forecast=[ForecastHour(1, 0, 1.9)]).action == "CLEAR IF SAFE"


def test_row_electrical_suspected():
    v = fuse(tel(), ph("clean"), S)
    assert v.rule_id == "electrical_suspected" and v.action == "FIELD CHECK" and v.severity is Severity.HIGH
    assert "inverter" in v.reason and "IV" in v.reason
    assert fuse(tel("CRITICAL"), ph("clean"), S).severity is Severity.CRITICAL


@pytest.mark.parametrize("cls", ["electrical_damage", "physical_damage"])
def test_row_hardware_fault(cls):
    v = fuse(tel(), ph(cls), S)
    assert (v.rule_id, v.verdict, v.action, v.severity) == ("hardware_fault", "Hardware fault",
                                                           "REPLACE / WARRANTY CLAIM", Severity.CRITICAL)
    assert "Safety warning" in v.reason


@pytest.mark.parametrize("cls", ["dusty", "bird_drop"])
def test_row_early_soiling(cls):
    v = fuse(tel(None), ph(cls), S)
    assert (v.rule_id, v.action, v.severity) == ("early_soiling", "WAIT", Severity.LOW)
    assert "7 days" in v.reason
    assert "3 days" in fuse(tel(None), ph(cls), FusionSettings(roi=ROI, recheck_days=3)).reason


def test_row_latent_damage():
    v = fuse(tel(None), ph("physical_damage"), S)
    assert (v.rule_id, v.verdict, v.action) == ("latent_damage", "Latent damage", "FIELD CHECK")


@pytest.mark.parametrize("t", [
    TelemetryEvidence(status="no_telemetry"),
    TelemetryEvidence(status="ok", usable_clear_hours=0),
    TelemetryEvidence(status="ok", usable_clear_hours=0, deficit_severity="CRITICAL"),  # alert without QC data
    TelemetryEvidence(status="ok"),  # coverage unknown, no alert
    None,
])
def test_row_inconclusive(t):
    v = fuse(t, ph("dusty"), S)
    assert (v.rule_id, v.verdict, v.action, v.confidence) == ("inconclusive", "Inconclusive",
                                                             "RE-CHECK NEXT CLEAR DAY", 0.0)


def test_row_unclear_photo_ood():
    v = fuse(tel(), ph("dusty", 0.99, is_ood=True), S)
    assert v.confidence == 0.0
    assert (v.rule_id, v.verdict, v.action) == ("unclear_photo", "Unclear photo", "NEEDS FIELD CHECK")


def test_row_unclear_photo_low_confidence():
    assert fuse(tel(), ph("dusty", 0.59), S).rule_id == "unclear_photo"


# ---- precedence
def test_unclear_beats_inconclusive():
    v = fuse(TelemetryEvidence(status="no_telemetry"), ph("dusty", 0.2), S)
    assert v.rule_id == "unclear_photo"


def test_ood_beats_hardware_fault():
    assert fuse(tel("CRITICAL"), ph("electrical_damage", 0.95, is_ood=True), S).rule_id == "unclear_photo"


def test_inconclusive_beats_every_class_row():
    t = TelemetryEvidence(status="ok", usable_clear_hours=0, deficit_severity="CRITICAL")
    for cls in CLASSES:
        assert fuse(t, ph(cls), S).rule_id == "inconclusive"


def test_model_needs_field_check_flag_is_unclear():
    assert fuse(tel(), ph("dusty", 0.9, needs_field_check=True, field_check_reason="low_confidence"), S).rule_id \
        == "unclear_photo"


# ---- edge cases
def test_confidence_exactly_06_is_accepted():
    assert fuse(tel(), ph("dusty", 0.6), S).rule_id == "soiling_confirmed"
    assert fuse(tel(), ph("dusty", 0.5999), S).rule_id == "unclear_photo"


@pytest.mark.parametrize("conf", [None, float("nan")])
def test_missing_confidence_is_unclear(conf):
    assert fuse(tel(), ph("dusty", conf), S).rule_id == "unclear_photo"


def test_no_photo_and_unknown_class_are_unclear():
    assert fuse(tel(), None, S).rule_id == "unclear_photo"
    assert fuse(tel(), ph("cat"), S).rule_id == "unclear_photo"


def test_class_name_normalised():
    assert fuse(tel(), ph("Bird-Drop"), S).photo_state == "bird_drop"


def test_info_alert_is_not_a_deficit():
    assert fuse(tel("INFO"), ph("dusty"), S).rule_id == "early_soiling"


def test_soiling_with_missing_roi_inputs_waits_with_reason():
    v = fuse(tel(expected_kwh_day=None), ph("dusty"), S)
    assert v.rule_id == "soiling_confirmed" and v.action == "WAIT" and "ROI inputs missing" in v.reason
    assert v.roi_incomplete and v.roi.incomplete
    assert not fuse(tel(), ph("dusty"), S).roi_incomplete


def test_soiling_zero_tariff_waits():
    s = FusionSettings(roi=RoiSettings(tariff_inr_per_kwh=0.0, tariff_preset=None, labour_cost_inr=500))
    v = fuse(tel(), ph("dusty"), s)
    assert v.action == "WAIT" and "never pays back" in v.reason


def test_deficit_text_falls_back_when_unquantified():
    v = fuse(tel(deviation_percent=None, attributable_deficit_fraction=None), ph("clean"), S)
    assert "unquantified" in v.reason


# ---- fallbacks (outside the spec table)
@pytest.mark.parametrize("cls,rule,action", [("clean", "healthy", "NO ACTION"), ("snow_covered", "snow_no_loss", "WAIT"),
                                             ("electrical_damage", "latent_electrical", "FIELD CHECK")])
def test_fallback_rows(cls, rule, action):
    v = fuse(tel(None), ph(cls), S)
    assert (v.rule_id, v.action) == (rule, action)


def test_every_combination_matches_a_row():
    for t in (tel(), tel(None), None, TelemetryEvidence(status="no_telemetry")):
        for p in [ph(c) for c in CLASSES] + [None, ph("dusty", 0.1)]:
            assert fuse(t, p, S).rule_id
