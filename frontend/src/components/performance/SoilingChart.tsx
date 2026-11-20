import type { SoilingAnalytics } from "@/lib/api";
import { soilingSawtooth } from "@/lib/performance";

const W = 860;
const H = 220;
const PAD = { top: 16, right: 24, bottom: 32, left: 48 };

/**
 * Soiling ratio line with cleaning / rain markers. The API returns a fitted rate and event dates, not a daily
 * series, so the line is a modelled sawtooth (see soilingSawtooth) and is labelled as such.
 */
export default function SoilingChart({ soiling, endDay }: { soiling: SoilingAnalytics; endDay: string }) {
  const pts = soilingSawtooth(soiling, endDay);
  if (pts.length < 2) return null;
  const lo = Math.min(0.8, ...pts.map((p) => p.ratio)) - 0.02;
  const x = (i: number) => PAD.left + (i / (pts.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - lo) / (1.02 - lo)) * (H - PAD.top - PAD.bottom);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.ratio).toFixed(1)}`).join(" ");
  const events = new Set(soiling.cleaning_events ?? []);
  const rain = soiling.method === "pvlib_kimber";
  const ticks = [1, (1 + lo) / 2 + 0.01, lo + 0.02];
  return (
    <div>
      <div className="dash-table-wrap" tabIndex={0} role="region" aria-label="Soiling chart (scrollable)">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Modelled soiling ratio over ${pts.length} days, loss ${((soiling.soiling_loss_rate_pct_per_day ?? (soiling.soiling_loss_rate_per_day ?? 0) * 100)).toFixed(2)} percent per day, ${events.size} ${rain ? "rain resets" : "cleaning events"}.`}
          style={{ display: "block", width: "100%", minWidth: 600, height: "auto" }}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray="2 3" />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">{t.toFixed(2)}</text>
            </g>
          ))}
          <path d={d} fill="none" stroke="var(--sun)" strokeWidth="2" strokeLinejoin="round" />
          {pts.map((p, i) =>
            events.has(p.day) ? (
              rain ? (
                <line key={p.day} x1={x(i)} x2={x(i)} y1={PAD.top} y2={PAD.top + 10} stroke="#4f7f9e" strokeWidth="2" data-testid="soiling-rain" />
              ) : (
                <path key={p.day} d={`M${x(i)},${PAD.top} v22 M${x(i)},${PAD.top} l12,5 l-12,5 z`} stroke="var(--field)" fill="var(--field)" data-testid="soiling-clean" />
              )
            ) : null,
          )}
          {[0, Math.floor(pts.length / 2), pts.length - 1].map((i) => (
            <text key={i} x={x(i)} y={H - 10} textAnchor={i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle"} fontSize="10" fill="var(--muted)">{pts[i].day}</text>
          ))}
        </svg>
      </div>
      <p className="dash-page-sub" style={{ marginTop: "0.5rem" }}>
        Modelled from the fitted loss rate: linear loss, reset on each {rain ? "rain event" : "cleaning interval"}. Not a measured daily series.
      </p>
    </div>
  );
}
