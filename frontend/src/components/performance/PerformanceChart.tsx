"use client";

import { useMemo, useState } from "react";
import type { HourlyPoint } from "@/lib/api";
import {
  clearStrips,
  dailyTotals,
  formatKwh,
  formatPercent,
  indexOfDay,
  linePath,
  ribbonPaths,
} from "@/lib/performance";

export interface PerformanceChartProps {
  series: HourlyPoint[];
  /** UTC dates (YYYY-MM-DD) drawn as blue rain ticks. */
  rainDays?: string[];
  /** UTC dates (YYYY-MM-DD) drawn as field-green cleaning flags. */
  cleaningDays?: string[];
  height?: number;
}

const W = 860;
const PAD = { top: 20, right: 24, bottom: 40, left: 56 };
const RAIN = "#4f7f9e";

/**
 * Expected vs actual power with the deficit ribbon (--sev-critical 14%), a thin sun strip for clear-sky hours,
 * rain ticks and cleaning flags (DESIGN.md §8.2). Hand-written SVG, same frame as ForecastActualChart.
 */
export default function PerformanceChart({ series, rainDays = [], cleaningDays = [], height = 300 }: PerformanceChartProps) {
  const [show, setShow] = useState({ expected: true, actual: true, ribbon: true, clear: true });
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const n = series.length;
  const maxKw = Math.max(1, ...series.map((p) => Math.max(p.expected_kw ?? 0, p.actual_kw ?? 0)));
  const x = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * innerW;
  const y = (v: number) => PAD.top + innerH - (Math.max(0, v) / (maxKw * 1.05)) * innerH;

  const g = useMemo(
    () => ({
      expected: linePath(series, (p) => p.expected_kw, x, y),
      actual: linePath(series, (p) => p.actual_kw, x, y),
      ribbons: ribbonPaths(series, x, y),
      strips: clearStrips(series, x),
      days: dailyTotals(series),
    }),
    // x and y are pure functions of n and maxKw
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [series, n, maxKw, height],
  );

  const mark = (days: string[]) => days.map((d) => indexOfDay(series, d)).filter((i) => i >= 0);
  const rainIdx = mark(rainDays);
  const cleanIdx = mark(cleaningDays);

  const yTicks = Array.from({ length: 5 }, (_, i) => (maxKw * 1.05 * i) / 4);
  const xStep = Math.max(1, Math.floor(n / 6));
  const xTicks = series.map((p, i) => ({ p, i })).filter(({ i }) => i % xStep === 0);
  const hp = hover != null ? series[hover] : null;

  const totals = g.days.reduce((a, d) => ({ e: a.e + d.expectedKwh, a: a.a + d.actualKwh }), { e: 0, a: 0 });
  const summary = `Expected versus actual power over ${g.days.length} days with usable data. ${formatKwh(totals.a)} kWh produced against ${formatKwh(totals.e)} kWh expected.`;

  const move = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect();
    const sx = ((clientX - r.left) / r.width) * W;
    setHover(Math.round(((Math.min(W - PAD.right, Math.max(PAD.left, sx)) - PAD.left) / innerW) * (n - 1)));
  };

  const Toggle = ({ k, label, swatch }: { k: keyof typeof show; label: string; swatch: React.ReactNode }) => (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", fontWeight: 600, cursor: "pointer" }}>
      <input type="checkbox" checked={show[k]} onChange={(e) => setShow({ ...show, [k]: e.target.checked })} />
      {swatch}
      {label}
    </label>
  );

  return (
    <div data-testid="performance-chart">
      <p className="sd-visually-hidden" id="perf-chart-summary">{summary}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 1rem", marginBottom: "0.85rem", alignItems: "center" }}>
        <Toggle k="expected" label="Expected" swatch={<span style={{ width: 14, height: 3, background: "var(--field)", display: "inline-block" }} />} />
        <Toggle k="actual" label="Actual" swatch={<span style={{ width: 14, height: 2, background: "var(--sun)", display: "inline-block" }} />} />
        <Toggle k="ribbon" label="Deficit" swatch={<span style={{ width: 14, height: 8, background: "var(--sev-critical)", opacity: 0.35, display: "inline-block" }} />} />
        <Toggle k="clear" label="Clear-sky hours" swatch={<span style={{ width: 14, height: 3, background: "var(--sun)", display: "inline-block" }} />} />
        <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
          <span aria-hidden="true" style={{ color: RAIN }}>|</span> rain &nbsp;
          <span aria-hidden="true" style={{ color: "var(--field)" }}>&#9873;</span> cleaning
        </span>
      </div>

      <div className="dash-table-wrap" tabIndex={0} role="region" aria-label="Performance chart (scrollable)">
        <svg
          viewBox={`0 0 ${W} ${height}`}
          role="img"
          aria-labelledby="perf-chart-summary"
          style={{ display: "block", width: "100%", minWidth: 600, height: "auto" }}
          onMouseMove={(e) => move(e.clientX, e.currentTarget)}
          onMouseLeave={() => setHover(null)}
        >
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeDasharray="2 3" />
              <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">{Math.round(v)} kW</text>
            </g>
          ))}
          {xTicks.map(({ p, i }) => (
            <text key={p.ts} x={x(i)} y={height - 12} textAnchor="middle" fontSize="10" fill="var(--muted)">
              {new Date(p.ts).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" })}
            </text>
          ))}
          <line x1={PAD.left} x2={PAD.left} y1={PAD.top} y2={height - PAD.bottom} stroke="var(--line)" />
          <line x1={PAD.left} x2={W - PAD.right} y1={height - PAD.bottom} y2={height - PAD.bottom} stroke="var(--line)" />

          {show.ribbon && g.ribbons.map((d, i) => <path key={i} d={d} fill="var(--sev-critical)" fillOpacity="0.14" data-testid="deficit-ribbon" />)}
          {show.expected && <path d={g.expected} fill="none" stroke="var(--field)" strokeWidth="2" strokeLinejoin="round" />}
          {show.actual && <path d={g.actual} fill="none" stroke="var(--sun)" strokeWidth="2" strokeLinejoin="round" />}

          {show.clear && g.strips.map((s) => (
            <rect key={s.x1} x={s.x1} y={height - PAD.bottom - 4} width={Math.max(s.x2 - s.x1, 1)} height={4} fill="var(--sun)" data-testid="clear-strip" />
          ))}
          {rainIdx.map((i) => (
            <line key={`r${i}`} x1={x(i)} x2={x(i)} y1={PAD.top} y2={PAD.top + 10} stroke={RAIN} strokeWidth="2" data-testid="rain-tick" />
          ))}
          {cleanIdx.map((i) => (
            <g key={`c${i}`} data-testid="cleaning-flag">
              <line x1={x(i)} x2={x(i)} y1={PAD.top} y2={PAD.top + 22} stroke="var(--field)" strokeWidth="1.5" />
              <path d={`M${x(i)},${PAD.top} l12,5 l-12,5 z`} fill="var(--field)" />
            </g>
          ))}
          {hover != null && hp && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={height - PAD.bottom} stroke="var(--ink)" strokeDasharray="3 3" opacity="0.5" />
          )}
          <rect
            x={PAD.left} y={PAD.top} width={innerW} height={innerH} fill="transparent" tabIndex={0}
            aria-label="Chart cursor: use left and right arrow keys to read each hour"
            onFocus={() => setHover((h) => h ?? 0)}
            onBlur={() => setHover(null)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? -1) + 1));
              else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? 1) - 1));
              else return;
              e.preventDefault();
            }}
          />
        </svg>
      </div>

      <p aria-live="polite" style={{ minHeight: "1.3rem", margin: "0.5rem 0 0", fontSize: "0.82rem", color: "var(--muted)" }}>
        {hp
          ? `${new Date(hp.ts).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC · expected ${formatKwh(hp.expected_kw)} kW · actual ${formatKwh(hp.actual_kw)} kW${hp.usable ? "" : " · not used (failed QC)"}`
          : "Hover or focus the chart to read an hour."}
      </p>

      <button type="button" className="dash-btn dash-btn-ghost dash-btn-sm" aria-expanded={table} onClick={() => setTable(!table)}>
        {table ? "Hide data table" : "Show data table"}
      </button>
      {table && (
        <div className="dash-table-wrap" tabIndex={0} role="region" aria-label="Daily totals (scrollable)" style={{ marginTop: "0.75rem" }}>
          <table className="dash-table">
            <caption className="sd-visually-hidden">Daily energy totals on usable clear-sky hours</caption>
            <thead>
              <tr><th>Day (UTC)</th><th>Expected kWh</th><th>Actual kWh</th><th>Deficit kWh</th><th>PR</th></tr>
            </thead>
            <tbody>
              {g.days.map((d) => (
                <tr key={d.day}>
                  <td className="nowrap">{d.day}</td>
                  <td className="nowrap">{formatKwh(d.expectedKwh)}</td>
                  <td className="nowrap">{formatKwh(d.actualKwh)}</td>
                  <td className="nowrap">{formatKwh(d.deficitKwh)}</td>
                  <td className="nowrap">{d.pr != null ? formatPercent(d.pr * 100) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
