# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics; logic unchanged.
"""
app/services/soiling_service.py

Dynamic soiling-loss calculation.

This is a simplified engineering model intended for development purposes.
It is NOT a scientifically validated production soiling model.
The function signature is designed to be easy to replace with a more
advanced model later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SoilingResult:
    soiling_loss_percent: float
    estimated_loss_kw: float
    method: str = "simple_rate_model"


def calculate_soiling_loss(
    current_power_kw: float,
    days_since_cleaning: float,
    rainfall_mm: float = 0.0,
    irradiance_w_m2: float = 1000.0,
    soiling_rate_per_day: float = 0.10,
    previous_soiling_loss_percent: float = 0.0,
    rainfall_cleaning_threshold_mm: float = 5.0,
) -> SoilingResult:
    """
    Estimate soiling loss based on elapsed time and rainfall.

    Parameters
    ----------
    current_power_kw:
        Current measured or predicted power output.
    days_since_cleaning:
        Number of days since the last physical panel cleaning.
    rainfall_mm:
        Rainfall in mm since the last reading (natural cleaning proxy).
    irradiance_w_m2:
        Current irradiance — higher irradiance increases the impact of soiling.
    soiling_rate_per_day:
        Assumed daily soiling accumulation rate in percent.
        Default 0.10 % per day is a conservative estimate.
    previous_soiling_loss_percent:
        Soiling loss from the previous time step.
    rainfall_cleaning_threshold_mm:
        Rainfall above this threshold resets soiling loss (self-cleaning).

    Returns
    -------
    SoilingResult with soiling_loss_percent and estimated_loss_kw.
    """
    # Clamp inputs
    days_since_cleaning = max(0.0, days_since_cleaning)
    rainfall_mm = max(0.0, rainfall_mm)
    current_power_kw = max(0.0, current_power_kw)
    irradiance_w_m2 = max(0.0, irradiance_w_m2)

    # If significant rainfall occurred, panels are self-cleaned
    if rainfall_mm >= rainfall_cleaning_threshold_mm:
        soiling_loss_percent = 0.0
    else:
        # Accumulate soiling; scale slightly with irradiance (dust bakes more at high irr)
        irradiance_factor = min(irradiance_w_m2 / 1000.0, 1.5)
        accumulated = days_since_cleaning * soiling_rate_per_day * irradiance_factor
        soiling_loss_percent = min(accumulated, 30.0)  # cap at 30% maximum

    # Smooth towards the new value (avoid instant jumps)
    soiling_loss_percent = 0.7 * soiling_loss_percent + 0.3 * previous_soiling_loss_percent

    # Estimated power loss
    estimated_loss_kw = current_power_kw * (soiling_loss_percent / 100.0)

    return SoilingResult(
        soiling_loss_percent=round(soiling_loss_percent, 4),
        estimated_loss_kw=round(estimated_loss_kw, 4),
    )
