"""Cleaning ROI engine (pure, DB-free). See docs/solardoctor/ROI_METHOD.md."""
from .engine import (CLEAN_NOW, WAIT, cleaning_cost, evaluate, optimal_interval_days, payback_days, rain_outlook,
                     water_per_clean)
from .models import ASSUMPTION_LABEL, TARIFF_PRESETS, ForecastHour, RoiResult, RoiSettings

__all__ = ["CLEAN_NOW", "WAIT", "ASSUMPTION_LABEL", "TARIFF_PRESETS", "ForecastHour", "RoiResult", "RoiSettings",
           "cleaning_cost", "evaluate", "optimal_interval_days", "payback_days", "rain_outlook", "water_per_clean"]
