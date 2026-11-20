# ROI method

Code: `backend/solardoctor/roi/`. Every monetary input is a **user assumption** (editable in plant settings, labelled
as such in every output under `assumptions`). Nothing here is measured; the physics deficit and soiling rate come from
the physics workstream and carry their own labels (measured / modelled / SIMULATED).

## Formulas

| Quantity | Formula |
|---|---|
| recoverable kWh/day | `expected_kwh_day x f`, where `f` = attributable deficit fraction (clamped to 0..1) |
| Rs/day | `recoverable_kwh_day x tariff` |
| cleaning cost `C` | `modules x Rs/module + water_L x Rs/L + labour`, with `water_L = modules x L/module` |
| payback days | `C / (Rs/day)`; Rs/day <= 0 gives `payback_days = null`, label "never pays back" |
| clean production value `V` | `expected_kwh_day x tariff` (Rs/day of a fully clean plant) |
| optimal interval `T*` | `sqrt(2C / (r V))`, `r` = soiling rate in fraction/day |
| water saved / year | `water_L_per_clean x (365 / calendar_interval - 365 / T*)` (signed) |

Tariff presets (starting points only): utility PPA Rs 2.6, C&I Rs 6.5, residential Rs 8 per kWh.

## Decision

Evaluated in this order; the first match decides.

1. **WAIT, rain**: any forecast hour with `0 <= hours_ahead <= 72` and precipitation probability `>= 60 %`
   (both inclusive; hour 73 and 59.9 % do not count). Rain may clean the panels for free.
2. **WAIT, never pays back**: Rs/day is 0 or negative (tariff 0, no deficit).
3. **CLEAN NOW** if payback `<= max_payback_days`, else **WAIT**.
4. Missing or NaN expected energy / deficit gives **WAIT** with "ROI inputs missing: configure expected energy/costs", `incomplete = true`, and no numbers. A total cleaning cost of 0 gives WAIT "Cleaning cost not configured" (also `incomplete`).

`max_payback_days` (default 30) is **our assumption**: the spec asks for a CLEAN NOW / WAIT choice from payback but gives
no limit. It is editable and listed in `assumptions`.

## T* derivation (heuristic)

Let a clean panel produce value `V` Rs/day. Soiling loses a fraction `r` of that per day, linearly, and a cleaning
resets it. If we clean every `t` days, the loss on day `s` is `r V s`, so the average loss per day over a cycle is

    (1/t) * integral_0^t r V s ds = r V t / 2.

Cleaning costs `C` once per cycle, i.e. `C / t` per day. Average cost per day:

    g(t) = r V t / 2 + C / t.

`g'(t) = rV/2 - C/t^2 = 0` gives `t* = sqrt(2C / (rV))`, and `g'' = 2C/t^3 > 0`, so this is the minimum.
`T*` is undefined (returned as `null`) when `r <= 0`, `V <= 0`, `C < 0` or any input is missing.

## Assumptions and limits

- **Heuristic, not an optimum for the real plant.** Soiling is modelled as linear and the cleaning as perfect and
  instantaneous; real soiling is non-linear, rain resets it partially, and dust types differ.
- `r` is only as good as its source: RdTools SRR (`measured`, needs >= 60 days) or the pvlib Kimber default
  (`modelled`, an assumed rate rather than a fit). A single constant tariff and a constant cost per clean are assumed.
- `T*` uses `C` for the whole scope you pass in (plant or string) and `V` of that scope; keep them consistent.
- Water saved compares the calendar schedule (default every 15 days) with cleaning every `T*` days. It is **negative**
  when `T*` is shorter than the calendar interval (the data say clean more often). It ignores rain skips.
- The rain rule uses forecast probability, not rainfall amount; light showers may not clean panels.
- **Scope convention:** all ROI inputs describe the scope being cleaned. Plant scope: plant expected kWh/day, plant
  `1 - PI`, plant module count. String scope: that string's expected kWh/day, `1 - pi_median` of the string, and that
  string's module count. Never multiply the deficit by the string's module share (the share is already inside the
  string's own expected kWh/day). The engine does not recompute the fraction.
- **Incomplete inputs:** missing expected energy/deficit, or a total cleaning cost of 0 (no modules, or all unit costs
  0), gives WAIT with `incomplete = true` and an explicit reason. A zero cost is "not configured", not a free clean.
- The soiling rate carries a source label (`soiling_rate_source`, e.g. "pvlib_kimber assumed default"): T* is a
  heuristic and only as good as that rate.
- Rupee figures are rounded to 2 decimals, kWh to 3, in the output; internal arithmetic is float.
