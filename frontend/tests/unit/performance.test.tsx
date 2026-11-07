import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HourlyPoint } from "@/lib/api";
import {
  clearStrips,
  computeKpis,
  dailyTotals,
  formatRecoverable,
  qcAdvisories,
  ribbonPaths,
  soilingKpi,
  soilingSawtooth,
  sparklinePoints,
} from "@/lib/performance";
import { panelsWithGps, plantPins, severityKey, worstSeverity } from "@/lib/map";
import { peers, performance, parkGrid, plants } from "../fixtures/index.mjs";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const pt = (h: number, e: number | null, a: number | null, o: Partial<HourlyPoint> = {}): HourlyPoint => ({
  ts: new Date(Date.UTC(2026, 10, 1, h)).toISOString(),
  expected_kw: e,
  actual_kw: a,
  pi: null,
  clear: true,
  usable: true,
  source: "site_sensor",
  ...o,
});
const X = (i: number) => i * 10;
const Y = (v: number) => 100 - v;

const flush = async () => act(async () => void (await new Promise((r) => setTimeout(r, 0))));
afterEach(() => {
  vi.resetModules();
  vi.doUnmock("@/lib/api");
  document.body.innerHTML = "";
});

describe("deficit ribbon geometry", () => {
  it("draws one closed polygon over a contiguous deficit, expected forward then actual back", () => {
    const [d, ...rest] = ribbonPaths([pt(0, 10, 8), pt(1, 20, 15), pt(2, 30, 21)], X, Y);
    expect(rest).toHaveLength(0);
    expect(d).toBe("M0.0,90.0 L10.0,80.0 L20.0,70.0 L20.0,79.0 L10.0,85.0 L0.0,92.0 Z");
  });
  it("splits at surplus hours and QC gaps, and skips single-point runs", () => {
    const s = [pt(0, 10, 5), pt(1, 10, 5), pt(2, 10, 12), pt(3, 10, 5), pt(4, 10, 5, { usable: false }), pt(5, 10, 5), pt(6, 10, 5)];
    expect(ribbonPaths(s, X, Y)).toHaveLength(2);
    expect(ribbonPaths([pt(0, 10, 5)], X, Y)).toEqual([]);
  });
  it("builds clear-sky strips widened by half a step", () => {
    const s = [pt(0, 1, 1, { clear: false }), pt(1, 1, 1), pt(2, 1, 1), pt(3, 1, 1, { clear: false })];
    expect(clearStrips(s, X)).toEqual([{ x1: 5, x2: 25 }]);
  });
});

describe("KPI maths and formatting", () => {
  it("computes PR and deficit kWh on usable hours only", () => {
    const k = computeKpis([pt(0, 10, 9), pt(1, 10, 8), pt(2, 10, 0, { usable: false })]);
    expect(k.pr).toBeCloseTo(0.85);
    expect(k.deficitKwh).toBeCloseTo(3);
  });
  it("returns nulls with no usable hour", () => {
    expect(computeKpis([pt(0, 10, 9, { usable: false })])).toMatchObject({ pr: null, deficitKwh: null });
  });
  it("formats the recoverable KPI in en-IN rupees, or the labelled placeholder", () => {
    expect(formatRecoverable({ state: "ready", inrPerMonth: 124500 }).value.replace(/\s/g, "")).toBe("₹1,24,500");
    expect(formatRecoverable({ state: "unconfigured" })).toEqual({ value: "—", sub: "ROI not configured" });
  });
  it("reports soiling status honestly", () => {
    expect(soilingKpi(null).value).toBe("—");
    expect(soilingKpi({ status: "insufficient_data", method: "none", label: "none", reason: "needs 60 days" }).sub).toBe("needs 60 days");
    expect(soilingKpi(performance.soiling as never).value).toBe("0.96");
  });
  it("sums daily totals and builds sparkline points", () => {
    expect(dailyTotals([pt(0, 10, 9), pt(1, 10, 9)])[0]).toMatchObject({ day: "2026-11-01", expectedKwh: 20, deficitKwh: 2 });
    expect(sparklinePoints([1], 80, 20)).toBe("");
    expect(sparklinePoints([1, 2], 80, 20).split(" ")).toHaveLength(2);
  });
  it("makes a sawtooth that resets on event days", () => {
    const s = soilingSawtooth({ status: "ok", method: "pvlib_kimber", label: "modelled", days: 5, soiling_loss_rate_per_day: 0.1, cleaning_events: ["2026-11-03"] }, "2026-11-05");
    expect(s.map((p) => p.ratio)).toEqual([1, 0.9, 1, 0.9, 0.8]);
  });
});

describe("QC advisories", () => {
  const resp = (series: HourlyPoint[]) => ({ ...(performance as never as object), series, status: "ok" }) as never;
  it("shows time_offset_suspected from the scan", () => {
    const a = qcAdvisories(resp([pt(0, 1, 1)]), { qc_status: "time_offset_suspected", clock_offset_min: -45 });
    expect(a.map((x) => x.id)).toEqual(["time_offset_suspected"]);
    expect(a[0].body).toContain("45 min");
  });
  it("derives irradiance_unverified from the series when under half is site-sensor", () => {
    const a = qcAdvisories(resp([pt(0, 1, 1, { source: "nasa_power" }), pt(1, 1, 1, { source: "site_sensor" }), pt(2, 1, 1, { source: "openmeteo" })]), null);
    expect(a.map((x) => x.id)).toEqual(["irradiance_unverified"]);
  });
  it("says inconclusive, not healthy, when nothing is usable", () => {
    expect(qcAdvisories(resp([pt(0, 1, 1, { usable: false })]), null)[0].id).toBe("inconclusive");
  });
  it("is quiet for a clean, sensor-verified window", () => {
    expect(qcAdvisories(performance as never, { qc_status: "ok", clock_offset_min: 0 })).toEqual([]);
  });
});

describe("map helpers", () => {
  it("ranks alert and detection severities on one scale", () => {
    expect(severityKey("WARNING")).toBe("high");
    expect(severityKey("INFO")).toBe("low");
    expect(severityKey("nope")).toBeNull();
    expect(worstSeverity([{ severity: "LOW" }, { severity: "CRITICAL" }, { severity: "HIGH" }])).toBe("CRITICAL");
  });
  it("pins plants by worst open alert and keeps only GPS panels", () => {
    const alerts = [{ plant_id: 2, severity: "CRITICAL", is_resolved: false }, { plant_id: 2, severity: "INFO", is_resolved: true }, { plant_id: 1, severity: "WARNING", is_resolved: false }];
    const pins = plantPins(plants as never, alerts as never);
    expect(pins.find((p) => p.plant.id === 2)?.severity).toBe("CRITICAL");
    expect(pins.find((p) => p.plant.id === 3)?.severity).toBeNull();
    expect(panelsWithGps(parkGrid.panels as never)).toHaveLength(2);
  });
});

describe("components", () => {
  it("renders the chart layers, rain ticks, cleaning flags and an accessible table toggle", async () => {
    const { default: PerformanceChart } = await import("@/components/performance/PerformanceChart");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<PerformanceChart series={performance.series as never} rainDays={["2026-10-30", "2030-01-01"]} cleaningDays={["2026-10-31"]} />));
    expect(host.querySelector('svg[role="img"]')?.getAttribute("aria-labelledby")).toBe("perf-chart-summary");
    expect(host.querySelectorAll('[data-testid="deficit-ribbon"]').length).toBeGreaterThan(0);
    expect(host.querySelectorAll('[data-testid="clear-strip"]').length).toBeGreaterThan(0);
    expect(host.querySelectorAll('[data-testid="rain-tick"]')).toHaveLength(1);
    expect(host.querySelectorAll('[data-testid="cleaning-flag"]')).toHaveLength(1);
    const btn = host.querySelector("button[aria-expanded]") as HTMLButtonElement;
    act(() => btn.click());
    expect(host.querySelector("table caption")?.textContent).toContain("Daily energy");
    act(() => root.unmount());
  });

  async function mountDeficit(api: Record<string, unknown>) {
    vi.doMock("@/lib/api", () => ({ performanceApi: api }));
    const { default: DeficitView } = await import("@/components/performance/DeficitView");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<DeficitView plantId={2} />));
    await flush();
    return { host, root };
  }

  it("shows the four KPIs, the ROI placeholder and the peer table from the fixture", async () => {
    const { host, root } = await mountDeficit({ get: vi.fn(async () => performance), peers: vi.fn(async () => peers), scan: vi.fn() });
    expect(host.textContent).toContain("Performance ratio");
    expect(host.querySelector('[data-testid="kpi-recoverable"]')?.textContent).toContain("ROI not configured");
    expect(host.textContent).toContain("S-04");
    expect(host.textContent).toContain("CRITICAL");
    act(() => root.unmount());
  });

  it("shows the empty state for no telemetry", async () => {
    const { host, root } = await mountDeficit({ get: vi.fn(async () => ({ ...performance, status: "no_telemetry", series: [], events: [] })), peers: vi.fn(), scan: vi.fn() });
    expect(host.textContent).toContain("No telemetry in this window");
    act(() => root.unmount());
  });

  it("shows an error alert, not an empty state, when the request fails", async () => {
    const { host, root } = await mountDeficit({ get: vi.fn(async () => Promise.reject(new Error("API unreachable"))), peers: vi.fn(), scan: vi.fn() });
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("API unreachable");
    expect(host.textContent).not.toContain("No telemetry");
    act(() => root.unmount());
  });

  it("shows the scan-only time offset advisory after Run scan", async () => {
    const scan = vi.fn(async () => ({ status: "ok", qc_status: "time_offset_suspected", clock_offset_min: 60, events: [], alert_ids: [], qc: {}, provenance: {}, baseline: "pvwatts", data_source: "SIMULATED" }));
    const { host, root } = await mountDeficit({ get: vi.fn(async () => performance), peers: vi.fn(async () => peers), scan });
    const run = [...host.querySelectorAll("button")].find((b) => b.textContent === "Run scan") as HTMLButtonElement;
    act(() => run.click());
    await flush();
    expect(host.querySelector('[data-testid="advisory-time_offset_suspected"]')).not.toBeNull();
    act(() => root.unmount());
  });

  async function mountMap(list: unknown, listOpen: unknown = vi.fn(async () => [])) {
    vi.doMock("@/lib/api", () => ({ plantsApi: { list }, alertsApi: { listOpen }, parksApi: {}, OPEN_ALERT_LIMIT: 500 }));
    vi.doMock("next/dynamic", () => ({ default: () => () => <div data-testid="leaflet-stub" /> }));
    vi.doMock("next/link", () => ({ default: ({ children, ...r }: { children: React.ReactNode }) => <a {...r}>{children}</a> }));
    const { default: MapView } = await import("@/components/map/MapView");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<MapView />));
    await flush();
    return { host, root };
  }

  it("map: empty state when there are no plants", async () => {
    const { host, root } = await mountMap(vi.fn(async () => []));
    expect(host.textContent).toContain("No mapped plants yet");
    act(() => root.unmount());
  });
  it("map: error state with a retry, never the empty state", async () => {
    const { host, root } = await mountMap(vi.fn(async () => Promise.reject(new Error("API unreachable"))));
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("API unreachable");
    expect(host.textContent).not.toContain("No mapped plants");
    act(() => root.unmount());
  });
  it("map: a failed alert fetch shows 'Alert status unavailable' instead of implying all clear", async () => {
    const { host, root } = await mountMap(vi.fn(async () => plants), vi.fn(async () => Promise.reject(new Error("boom"))));
    expect(host.textContent).toContain("Alert status unavailable");
    act(() => root.unmount());
  });
  it("map: warns when a plant hits the open-alert cap", async () => {
    const many = Array.from({ length: 500 }, (_, i) => ({ id: i, plant_id: 1, severity: "INFO", is_resolved: false, message: "m" }));
    const { host, root } = await mountMap(vi.fn(async () => plants), vi.fn(async () => many));
    expect(host.textContent).toContain("most recent open alerts");
    act(() => root.unmount());
  });
  it("map grid: labelled group, one tab stop, arrow keys move focus", async () => {
    const { default: ParkMapGrid } = await import("@/components/map/ParkMapGrid");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const onSelect = vi.fn();
    act(() => root.render(<ParkMapGrid grid={parkGrid as never} selectedPanelId={null} onSelect={onSelect} />));
    expect(host.querySelector('[role="grid"],[role="gridcell"]')).toBeNull();
    expect(host.querySelector('[role="group"]')?.getAttribute("aria-label")).toContain("Panel grid");
    const stops = host.querySelectorAll("button[tabindex='0']");
    expect(stops).toHaveLength(1);
    const first = stops[0] as HTMLButtonElement; // R1-C2 (row 0, col 1)
    act(() => first.focus());
    act(() => void first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(document.activeElement?.getAttribute("data-cell")).toBe("0-2");
    expect(host.querySelectorAll("button[tabindex='0']")).toHaveLength(1);
    const pressed = host.querySelector('[data-testid="panel-R2-C4"]') as HTMLButtonElement;
    expect(pressed.getAttribute("aria-pressed")).toBe("false");
    act(() => pressed.click());
    expect(onSelect).toHaveBeenCalled();
    act(() => root.unmount());
  });
  it("map: renders the map, legend and plant list for mapped plants", async () => {
    const { host, root } = await mountMap(vi.fn(async () => plants));
    expect(host.querySelector('[data-testid="leaflet-stub"]')).not.toBeNull();
    expect(host.querySelector('[aria-label="Severity legend"]')?.textContent).toContain("CRITICAL");
    expect(host.textContent).toContain("PCCoE Rooftop");
    act(() => root.unmount());
  });
});
