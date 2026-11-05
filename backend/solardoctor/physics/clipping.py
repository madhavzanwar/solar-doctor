# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics; logic unchanged.
"""
app/services/clipping_service.py

Inverter AC export capping (clipping) calculation.

Clipping occurs when the DC power from the panels exceeds
the inverter's rated AC output capacity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClippingResult:
    raw_ac_power_kw: float
    clipped_ac_power_kw: float
    clipping_loss_kw: float
    is_clipping: bool


def calculate_clipping(
    dc_power_kw: float,
    inverter_capacity_kw: float,
    efficiency: float = 0.96,
) -> ClippingResult:
    """
    Calculate inverter clipping loss.

    Parameters
    ----------
    dc_power_kw:
        DC power produced by the PV array (kW).
    inverter_capacity_kw:
        Maximum AC output capacity of the inverter (kW).
    efficiency:
        DC-to-AC conversion efficiency (0–1).

    Returns
    -------
    ClippingResult with raw, clipped power and clipping loss.
    """
    # Guard against invalid inputs
    dc_power_kw = max(0.0, dc_power_kw)
    inverter_capacity_kw = max(0.0, inverter_capacity_kw)
    efficiency = max(0.0, min(1.0, efficiency))

    raw_ac_kw = dc_power_kw * efficiency

    if raw_ac_kw > inverter_capacity_kw:
        clipped_ac_kw = inverter_capacity_kw
        clipping_loss_kw = raw_ac_kw - inverter_capacity_kw
        is_clipping = True
    else:
        clipped_ac_kw = raw_ac_kw
        clipping_loss_kw = 0.0
        is_clipping = False

    return ClippingResult(
        raw_ac_power_kw=round(raw_ac_kw, 4),
        clipped_ac_power_kw=round(clipped_ac_kw, 4),
        clipping_loss_kw=round(clipping_loss_kw, 4),
        is_clipping=is_clipping,
    )
