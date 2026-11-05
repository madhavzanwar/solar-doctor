"""Demo plant definitions for ``make seed``.

Everything here is a *demo asset*, not a real plant record.  Coordinates are approximate public
locations of the named sites (rounded, from public maps); tilt follows the "about latitude"
rule of thumb; azimuth 180 (equator-facing); module wattage, DC/AC ratio, temperature
coefficient and tariffs are ASSUMPTIONS typical of Indian utility/commercial PV and are
labelled as such.  Nothing here is measured plant data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

SOURCE = "SIMULATED"
PROJECT_NAME = "SolarDoctor Demo Portfolio (SIMULATED)"
TZ = "Asia/Kolkata"

#: Injected-event calendar, in days from the window start (0-based).
CLOUDY_SPELL_DAYS = (15, 16, 17)  # all plants: false-positive control
CLOUDY_SPELL_K_FACTOR = 0.35      # clearness index multiplier on the cloudy spell


@dataclass(frozen=True)
class StringSpec:
    name: str
    inverter: int            # index into the plant's inverter list
    modules: int
    fault_loss: float = 0.0  # fractional DC loss once the fault starts
    fault_start_day: int = 0


@dataclass(frozen=True)
class PlantSpec:
    key: str
    name: str
    location: str
    lat: float
    lon: float
    altitude_m: float
    tilt: float
    azimuth: float
    dc_kw: float
    ac_kw: float
    module_wp: float
    inverters: int
    tariff_inr_kwh: float
    park_id: str
    soiling_start_pct: float          # soiling already present at window start
    soiling_rate_pct_day: float
    cleaning_days: tuple[int, ...] = ()  # soiling resets to 0 at the start of these days
    temp_coeff: float = -0.0037          # 1/degC of Pmp (assumption: mono-PERC)
    strings: tuple[StringSpec, ...] = field(default_factory=tuple)

    @property
    def module_count(self) -> int:
        return round(self.dc_kw * 1000.0 / self.module_wp)


_PCCOE_STRINGS = (
    StringSpec("S-01", 0, 37),
    StringSpec("S-02", 0, 37),
    StringSpec("S-03", 0, 37),
    # S-04: the single injected string fault, -12.5 % DC from day 10 onwards (inside the -10..-15 % brief).
    StringSpec("S-04", 1, 37, fault_loss=0.125, fault_start_day=10),
    StringSpec("S-05", 1, 36),
    StringSpec("S-06", 1, 36),
)

PLANTS: tuple[PlantSpec, ...] = (
    PlantSpec(
        key="bhadla", name="Bhadla Block C", location="Bhadla Solar Park, Jodhpur, Rajasthan",
        lat=27.54, lon=71.92, altitude_m=230.0, tilt=27.0, azimuth=180.0,
        dc_kw=50_000.0, ac_kw=40_000.0, module_wp=545.0, inverters=10,
        tariff_inr_kwh=2.6, park_id="PARK_BHADLA_C",
        # Desert site: steady dust accumulation, no cleaning in the window -> ~9 % by day 30.
        soiling_start_pct=0.0, soiling_rate_pct_day=0.30,
    ),
    PlantSpec(
        key="pccoe", name="PCCoE Rooftop", location="PCCoE, Akurdi, Pune, Maharashtra",
        lat=18.65, lon=73.76, altitude_m=580.0, tilt=19.0, azimuth=180.0,
        dc_kw=120.0, ac_kw=100.0, module_wp=545.0, inverters=2,
        tariff_inr_kwh=8.0, park_id="PARK_PCCOE_ROOFTOP",
        soiling_start_pct=0.0, soiling_rate_pct_day=0.20,
        strings=_PCCOE_STRINGS,
    ),
    PlantSpec(
        key="pavagada", name="Pavagada Unit 4", location="Pavagada Solar Park, Tumakuru, Karnataka",
        lat=14.26, lon=77.45, altitude_m=650.0, tilt=15.0, azimuth=180.0,
        dc_kw=25_000.0, ac_kw=20_000.0, module_wp=545.0, inverters=5,
        tariff_inr_kwh=3.0, park_id="PARK_PAVAGADA_U4",
        # Starts already dirty (5.5 %), cleaned on day 6 (a resolved historical alert), then re-soils.
        soiling_start_pct=5.5, soiling_rate_pct_day=0.30, cleaning_days=(6,),
    ),
)

#: Faults that are ready to become work orders (PanelFault rows; assigned to the technician).
#: (plant key, panel id, canonical class, status, priority/note)
FAULTS: tuple[dict, ...] = (
    dict(plant="pccoe", panel_id="S-04", class_="string", status="assigned", confidence=0.0,
         note="SIMULATED seed: string S-04 delivers ~12.5 % less than its peers on sunny hours "
              "(see plant alert string_underperformance). Check connectors, MC4 contacts and bypass diodes.",
         assign=True, due_days=7),
    dict(plant="bhadla", panel_id="R12-C7", class_="hot-spot-low", status="assigned", confidence=0.81,
         note="SIMULATED seed fault for work-order demo.", assign=True, due_days=14),
    dict(plant="pavagada", panel_id="R3-C9", class_="bypass-diode", status="open", confidence=0.74,
         note="SIMULATED seed fault for work-order demo (unassigned).", assign=False, due_days=None),
)

PVDAQ_DEFAULT_SYSTEM_ID = 9068
