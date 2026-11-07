import type { DeficitEvent, PeersResponse } from "@/lib/api";
import { formatPercent, formatSignedPp, type DayTotal } from "@/lib/performance";
import Sparkline from "./Sparkline";

const SEV: Record<string, string> = { CRITICAL: "var(--sev-critical)", WARNING: "var(--sev-high)", INFO: "var(--sev-low)" };

function Badge({ label, color }: { label: string; color?: string }) {
  return (
    <span className="dash-badge" style={color ? { background: `color-mix(in srgb, ${color} 12%, transparent)`, color } : undefined}>
      {label}
    </span>
  );
}

/** String peer comparison (DESIGN.md §8.2): yield vs plant median, bar per string, plant PI sparkline, deficit badge. */
export default function PeerTable({ peers, events, days }: { peers: PeersResponse; events: DeficitEvent[]; days: DayTotal[] }) {
  const median = peers.plant_median;
  const sevOf = (id: number) => events.find((e) => e.scope === "string" && e.scope_id === id)?.severity;
  const rows = [...peers.peers].sort((a, b) => a.normalised_yield - b.normalised_yield);
  return (
    <div className="dash-table-wrap" tabIndex={0} role="region" aria-label="String peer comparison (scrollable)">
      <table className="dash-table">
        <caption className="sd-visually-hidden">String yield against the plant median, lowest first</caption>
        <thead>
          <tr>
            <th scope="col">String</th>
            <th scope="col">Normalised yield</th>
            <th scope="col">vs plant median</th>
            <th scope="col">Peer z</th>
            <th scope="col">Clear hours</th>
            <th scope="col">Trend</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" style={{ textAlign: "left" }}>Plant (all hours)</th>
            <td className="nowrap">{formatPercent(median != null ? median * 100 : null)}</td>
            <td>{"—"}</td>
            <td>{"—"}</td>
            <td>{"—"}</td>
            <td><Sparkline values={days.map((d) => d.pr)} /></td>
            <td><span className="dash-badge dash-badge-muted">DAILY PR</span></td>
          </tr>
          {rows.map((p) => {
            const sev = sevOf(p.string_id);
            const outlier = p.peer_z != null && p.peer_z <= -3;
            const delta = median != null ? (p.normalised_yield - median) * 100 : null;
            return (
              <tr key={p.string_id}>
                <th scope="row" style={{ textAlign: "left" }}>{p.name}</th>
                <td className="nowrap">{formatPercent(p.normalised_yield * 100)}</td>
                <td className="nowrap">
                  {delta != null ? formatSignedPp(delta) : "—"}
                  <svg width="64" height="8" viewBox="0 0 64 8" aria-hidden="true" style={{ marginLeft: 8, verticalAlign: "middle" }}>
                    <rect x="0" y="2" width="64" height="4" fill="var(--line)" opacity="0.5" />
                    <rect x="0" y="2" width={Math.min(64, Math.max(0, p.normalised_yield) * 64)} height="4" fill={sev ? SEV[sev] : "var(--field)"} />
                    {median != null && <line x1={median * 64} x2={median * 64} y1="0" y2="8" stroke="var(--ink)" />}
                  </svg>
                </td>
                <td className="nowrap">{p.peer_z != null ? p.peer_z.toFixed(2) : "—"}</td>
                <td className="nowrap">{p.clear_hours}</td>
                <td>{"—"}</td>
                <td>{sev ? <Badge label={sev} color={SEV[sev]} /> : outlier ? <Badge label="PEER OUTLIER" color="var(--sev-low)" /> : <Badge label="OK" color="var(--sev-resolved)" />}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
