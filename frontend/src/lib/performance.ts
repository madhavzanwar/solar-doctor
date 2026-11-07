/** Pure helpers for the Performance screen (DESIGN.md §8.2): KPIs, chart geometry, QC advisories. */
import type { HourlyPoint, PerformanceResponse, QcStatus, SoilingAnalytics } from "@/lib/api";
import { formatMoney } from "@/lib/money";

const MINUS = "−";
const DASH = "—";

// ── KPI formatting ─────────────────────────────────────────────────────────────

/** `en-IN` grouping (1,24,500). */
export function formatNumber(v: number, digits = 0): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);
}

export function formatKwh(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? DASH : formatNumber(v, Math.abs(v) < 100 ? 1 : 0);
}

export function formatPercent(v: number | null | undefined, digits = 1): string {
  return v == null || !Number.isFinite(v) ? DASH : `${formatNumber(v, digits)}%`;
}

/** Signed percentage points with a true minus sign, e.g. "−4.2 pp". */
export function formatSignedPp(v: number): string {
  return `${v < 0 ? MINUS : v > 0 ? "+" : ""}${formatNumber(Math.abs(v), 1)} pp`;
}

/** Recoverable value for the ROI hook: `en-IN` INR, or the labelled placeholder. */
export type RecoverableInr = { state: "unconfigured" } | { state: "ready"; inrPerMonth: number };

export function formatRecoverable(r: RecoverableInr): { value: string; sub: string } {
  return r.state === "ready"
    ? { value: formatMoney(r.inrPerMonth, "INR"), sub: "per month, from the ROI engine" }
    : { value: DASH, sub: "ROI not configured" };
}

// ── KPI maths (usable QC-passed samples only) ──────────────────────────────────

const usableBoth = (p: HourlyPoint) => p.usable && p.expected_kw != null && p.actual_kw != null;

/** Median spacing of the series in hours (the API sends hourly rows; default 1). */
export function stepHours(series: HourlyPoint[]): number {
  if (series.length < 2) return 1;
  const d = series
    .slice(1)
    .map((p, i) => (Date.parse(p.ts) - Date.parse(series[i].ts)) / 3_600_000)
    .filter((x) => x > 0)
    .sort((a, b) => a - b);
  return d.length ? d[Math.floor(d.length / 2)] : 1;
}

export interface PerformanceKpis {
  /** sum(actual) / sum(expected) on usable hours; null when nothing is usable. */
  pr: number | null;
  deficitKwh: number | null;
  usableHours: number;
}

export function computeKpis(series: HourlyPoint[]): PerformanceKpis {
  const pts = series.filter(usableBoth);
  const exp = pts.reduce((s, p) => s + p.expected_kw!, 0);
  const act = pts.reduce((s, p) => s + p.actual_kw!, 0);
  const h = stepHours(series);
  return {
    pr: exp > 0 ? act / exp : null,
    deficitKwh: pts.length ? Math.max(exp - act, 0) * h : null,
    usableHours: pts.length * h,
  };
}

export function soilingKpi(s: SoilingAnalytics | null): { value: string; sub: string; ratio: number | null } {
  if (!s) return { value: DASH, sub: "No soiling analysis yet", ratio: null };
  if (s.status !== "ok" || s.soiling_ratio_p50 == null) {
    return { value: DASH, sub: s.reason ?? "Soiling analysis unavailable", ratio: null };
  }
  const ci = s.soiling_ratio_ci ? ` · CI ${s.soiling_ratio_ci[0].toFixed(2)}–${s.soiling_ratio_ci[1].toFixed(2)}` : "";
  const how = s.label === "measured" ? "RdTools SRR, measured" : "pvlib Kimber, modelled";
  return { value: s.soiling_ratio_p50.toFixed(2), ratio: s.soiling_ratio_p50, sub: how + ci };
}

// ── QC advisories ──────────────────────────────────────────────────────────────

/** Share of usable samples whose irradiance came from the site sensor (null with no usable sample). */
export function irradianceSiteShare(series: HourlyPoint[]): number | null {
  const u = series.filter((p) => p.usable);
  return u.length ? u.filter((p) => p.source === "site_sensor").length / u.length : null;
}

export interface Advisory {
  id: string;
  title: string;
  body: string;
}

/**
 * `time_offset_suspected` only exists on the scan response; `irradiance_unverified` is also derived from the series
 * with the backend's fixed rule (under 50 % of usable samples on site-sensor irradiance).
 */
export function qcAdvisories(
  resp: PerformanceResponse | null,
  scan: { qc_status: QcStatus | null; clock_offset_min: number | null } | null,
): Advisory[] {
  const out: Advisory[] = [];
  const share = resp ? irradianceSiteShare(resp.series) : null;
  const status = scan?.qc_status;
  if (status === "time_offset_suspected") {
    const off = scan?.clock_offset_min;
    const by = off != null ? `${Math.abs(Math.round(off))} min` : "30 min or more";
    out.push({
      id: "time_offset_suspected",
      title: "Telemetry clock offset suspected",
      body: `Site irradiance lines up with the clear-sky curve ${by} away from the telemetry timestamps. Deficit alerts are suppressed until the logger clock is checked.`,
    });
  }
  if (status === "irradiance_unverified" || (share != null && share < 0.5)) {
    const lead = share != null ? `Only ${Math.round(share * 100)}% of usable hours use site-sensor irradiance. ` : "";
    out.push({
      id: "irradiance_unverified",
      title: "Irradiance not verified by a site sensor",
      body: `${lead}Plant- and inverter-wide deficits are capped at INFO because satellite or modelled irradiance shares one error across the whole plant. String peer comparisons are still trusted.`,
    });
  }
  if (resp && (resp.status === "no_telemetry" || !resp.series.some((p) => p.usable))) {
    out.push({
      id: "inconclusive",
      title: "No clear-sky samples to judge",
      body: "No hour in this window passed every QC gate (cloudy, missing telemetry or unverified irradiance). This is inconclusive, not healthy.",
    });
  }
  return out;
}

// ── Chart geometry ─────────────────────────────────────────────────────────────

type X = (i: number) => number;
type Y = (v: number) => number;

const pt = (x: number, y: number) => `${x.toFixed(1)},${y.toFixed(1)}`;

/** Runs of consecutive indices where `ok(i)` holds. */
function runs(n: number, ok: (i: number) => boolean): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  let start = -1;
  for (let i = 0; i <= n; i++) {
    const good = i < n && ok(i);
    if (good && start < 0) start = i;
    if (!good && start >= 0) {
      out.push([start, i - 1]);
      start = -1;
    }
  }
  return out;
}

/**
 * Deficit ribbon: one closed polygon per run (>= 2 points) of usable hours where actual is below expected.
 * Forward along expected, back along actual. Surplus hours and gaps break the ribbon.
 */
export function ribbonPaths(series: HourlyPoint[], x: X, y: Y): string[] {
  return runs(series.length, (i) => usableBoth(series[i]) && series[i].expected_kw! > series[i].actual_kw!)
    .filter(([a, b]) => b > a)
    .map(([a, b]) => {
      const idx = Array.from({ length: b - a + 1 }, (_, k) => a + k);
      const top = idx.map((i, k) => `${k ? "L" : "M"}${pt(x(i), y(series[i].expected_kw!))}`);
      const bottom = [...idx].reverse().map((i) => `L${pt(x(i), y(series[i].actual_kw!))}`);
      return `${top.join(" ")} ${bottom.join(" ")} Z`;
    });
}

/** Line path that breaks (new `M`) wherever the value is null. */
export function linePath(series: HourlyPoint[], pick: (p: HourlyPoint) => number | null, x: X, y: Y): string {
  let pen = false;
  return series
    .map((p, i) => {
      const v = pick(p);
      if (v == null) {
        pen = false;
        return "";
      }
      const seg = `${pen ? "L" : "M"}${pt(x(i), y(v))}`;
      pen = true;
      return seg;
    })
    .filter(Boolean)
    .join(" ");
}

/** Clear-sky strip: x extents of contiguous clear hours, widened half a step so a single hour is visible. */
export function clearStrips(series: HourlyPoint[], x: X): Array<{ x1: number; x2: number }> {
  const half = series.length > 1 ? (x(1) - x(0)) / 2 : 0;
  return runs(series.length, (i) => series[i].clear).map(([a, b]) => ({ x1: x(a) - half, x2: x(b) + half }));
}

/** Index of the first series row on a UTC calendar day (`YYYY-MM-DD`), or -1 outside the window. */
export function indexOfDay(series: HourlyPoint[], day: string): number {
  return series.findIndex((p) => p.ts.slice(0, 10) === day);
}

export interface DayTotal {
  day: string;
  expectedKwh: number;
  actualKwh: number;
  deficitKwh: number;
  pr: number | null;
}

/** Per-UTC-day totals on usable hours: feeds the accessible data table and the plant sparkline. */
export function dailyTotals(series: HourlyPoint[]): DayTotal[] {
  const h = stepHours(series);
  const by = new Map<string, { e: number; a: number }>();
  for (const p of series.filter(usableBoth)) {
    const d = p.ts.slice(0, 10);
    const cur = by.get(d) ?? { e: 0, a: 0 };
    cur.e += p.expected_kw!;
    cur.a += p.actual_kw!;
    by.set(d, cur);
  }
  return [...by.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, { e, a }]) => ({
      day,
      expectedKwh: e * h,
      actualKwh: a * h,
      deficitKwh: Math.max(e - a, 0) * h,
      pr: e > 0 ? a / e : null,
    }));
}

/** Polyline points for a sparkline in a w x h box; nulls are skipped, a flat series sits mid-height. */
export function sparklinePoints(values: Array<number | null>, w: number, h: number, pad = 2): string {
  const v = values.map((x, i) => ({ x, i })).filter((p): p is { x: number; i: number } => p.x != null);
  if (v.length < 2) return "";
  const lo = Math.min(...v.map((p) => p.x));
  const hi = Math.max(...v.map((p) => p.x));
  const n = values.length - 1;
  return v
    .map((p) => {
      const t = hi === lo ? 0.5 : (p.x - lo) / (hi - lo);
      return pt(pad + (p.i / n) * (w - 2 * pad), h - pad - t * (h - 2 * pad));
    })
    .join(" ");
}

/**
 * Soiling ratio reconstructed from the fitted loss rate: starts clean at the window start, loses `rate` per day and
 * resets to 1 on each cleaning/rain date. It is a modelled sawtooth, not a measured series, and the UI says so.
 */
export function soilingSawtooth(s: SoilingAnalytics, endDay: string): Array<{ day: string; ratio: number }> {
  const rate = s.soiling_loss_rate_per_day;
  const days = s.days ?? s.days_with_data;
  if (s.status !== "ok" || rate == null || !days || days < 2) return [];
  const end = Date.parse(`${endDay}T00:00:00Z`);
  const events = new Set(s.cleaning_events ?? []);
  const out: Array<{ day: string; ratio: number }> = [];
  let since = -1;
  for (let k = days - 1; k >= 0; k--) {
    const day = new Date(end - k * 86_400_000).toISOString().slice(0, 10);
    since = events.has(day) ? 0 : since + 1;
    out.push({ day, ratio: Math.min(1, Math.max(0, 1 - rate * since)) });
  }
  return out;
}
