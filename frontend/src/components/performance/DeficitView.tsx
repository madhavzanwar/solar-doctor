"use client";

import { useEffect, useMemo, useState } from "react";
import {
  performanceApi,
  type PeersResponse,
  type PerformanceBaseline,
  type PerformanceResponse,
  type ScanResponse,
} from "@/lib/api";
import { isTrackerUnsupported } from "@/lib/api/errors";
import { TrackerUnsupported } from "@/components/ui/TrackerUnsupported";
import { SourceBadge } from "@/components/ui/SourceBadge";
import { EmptyState, LoadingState } from "@/components/ui/states";
import {
  computeKpis,
  dailyTotals,
  formatKwh,
  formatPercent,
  formatRecoverable,
  qcAdvisories,
  soilingKpi,
} from "@/lib/performance";
import { useRecoverableInr } from "@/lib/roi";
import PerformanceChart from "./PerformanceChart";
import PeerTable from "./PeerTable";
import SoilingChart from "./SoilingChart";

const BASELINES: Array<{ id: PerformanceBaseline; label: string }> = [
  { id: "clearsky", label: "Clear-sky (Ineichen)" },
  { id: "pvwatts", label: "PVWatts from NASA POWER" },
  { id: "hybrid", label: "Hybrid ML" },
];
const RANGES = [7, 14, 30];

function Advisories({ items }: { items: ReturnType<typeof qcAdvisories> }) {
  return (
    <>
      {items.map((a) => (
        <div key={a.id} className="dash-advisory" data-testid={`advisory-${a.id}`} role="note" style={{ marginBottom: "1rem" }}>
          <div className="dash-advisory-title">{a.title}</div>
          <div className="dash-advisory-body">{a.body}</div>
        </div>
      ))}
    </>
  );
}

export default function DeficitView({ plantId, refreshKey = 0, timeZone = "UTC" }: { plantId: number; refreshKey?: number; timeZone?: string }) {
  const [baseline, setBaseline] = useState<PerformanceBaseline>("pvwatts");
  const [days, setDays] = useState(7);
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [peers, setPeers] = useState<PeersResponse | null>(null);
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [peersFailed, setPeersFailed] = useState(false);
  const [unsupported, setUnsupported] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const recoverable = useRecoverableInr(plantId);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    setUnsupported(null);
    setPeers(null);
    setPeersFailed(false);
    const start = new Date(Date.now() - days * 86_400_000).toISOString();
    (async () => {
      try {
        const res = await performanceApi.get(plantId, { start, baseline });
        if (!live) return;
        setData(res);
        const sid =
          res.events.find((e) => e.scope === "string" && e.scope_id != null)?.scope_id ??
          res.open_alerts.find((a) => a.string_id != null)?.string_id;
        if (sid != null) {
          // Peers are a secondary card: a failure there must not blank the main chart.
          performanceApi.peers(sid, { start }).then((p) => live && setPeers(p), () => live && setPeersFailed(true));
        }
      } catch (err: unknown) {
        if (!live) return;
        setData(null);
        if (isTrackerUnsupported(err)) setUnsupported((err as Error).message);
        else setError(err instanceof Error ? err.message : "Failed to load performance data.");
      } finally {
        if (live) setLoading(false);
      }
    })();
    return () => {
      live = false;
    };
  }, [plantId, baseline, days, refreshKey, nonce]);

  const runScan = async () => {
    setScanning(true);
    setError(null);
    try {
      setScan(await performanceApi.scan(plantId, { start: new Date(Date.now() - days * 86_400_000).toISOString(), baseline }));
      setNonce((n) => n + 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scan failed.");
    } finally {
      setScanning(false);
    }
  };

  const kpis = useMemo(() => computeKpis(data?.series ?? []), [data]);
  const totals = useMemo(() => dailyTotals(data?.series ?? [], timeZone), [data, timeZone]);
  const soil = soilingKpi(data?.soiling ?? null);
  const roi = formatRecoverable(recoverable);
  const rain = data?.soiling?.method === "pvlib_kimber" ? data.soiling.cleaning_events ?? [] : [];
  const clean = data?.soiling?.method === "rdtools_srr" ? data.soiling.cleaning_events ?? [] : [];

  const toolbar = (
    <div className="dash-toolbar" style={{ marginBottom: "1.15rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <label htmlFor="perf-baseline">Baseline</label>
        <select id="perf-baseline" className="dash-input" style={{ width: "auto", padding: "0.45rem 0.65rem" }} value={baseline} onChange={(e) => { setBaseline(e.target.value as PerformanceBaseline); setScan(null); }}>
          {BASELINES.map((b) => (
            <option key={b.id} value={b.id}>{b.label}</option>
          ))}
        </select>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <label htmlFor="perf-range">Range</label>
        <select id="perf-range" className="dash-input" style={{ width: "auto", padding: "0.45rem 0.65rem" }} value={days} onChange={(e) => { setDays(parseInt(e.target.value, 10)); setScan(null); }}>
          {RANGES.map((d) => (
            <option key={d} value={d}>Last {d} days</option>
          ))}
        </select>
      </div>
      <div className="dash-toolbar-spacer">
        <button type="button" className="dash-btn dash-btn-ghost" onClick={runScan} disabled={scanning || loading || !!unsupported} title="Run the deficit detector now and update alerts (operator role)">
          {scanning ? "Scanning…" : "Run scan"}
        </button>
      </div>
    </div>
  );

  if (unsupported !== null) return <TrackerUnsupported detail={unsupported} />;

  return (
    <>
      {toolbar}
      {error && <div className="dash-error" role="alert">{error}</div>}
      {loading ? (
        <LoadingState label="Comparing telemetry with the expected-power baseline…" rows={3} />
      ) : !data ? null : data.status === "no_telemetry" || data.series.length === 0 ? (
        <>
          <Advisories items={qcAdvisories(data, scan)} />
          <EmptyState icon="chart" title="No telemetry in this window">
            Nothing was reported by this plant in the last {days} days. Check the data connection or widen the range.
          </EmptyState>
        </>
      ) : (
        <>
          <Advisories items={qcAdvisories(data, scan)} />
          <div className="dash-kpi-grid" style={{ marginBottom: "1.25rem" }}>
            <div className="dash-kpi">
              <div className="dash-kpi-label">Performance ratio</div>
              <div className="dash-kpi-value">{formatPercent(kpis.pr != null ? kpis.pr * 100 : null)}</div>
              <div className="dash-kpi-sub">actual / expected · {kpis.usableHours} clear hours</div>
            </div>
            <div className="dash-kpi">
              <div className="dash-kpi-label">Energy deficit</div>
              <div className="dash-kpi-value dash-kpi-sun">{formatKwh(kpis.deficitKwh)}<span className="dash-kpi-unit">kWh</span></div>
              <div className="dash-kpi-sub">on clear, QC-passed hours</div>
            </div>
            <div className="dash-kpi">
              <div className="dash-kpi-label">Soiling ratio</div>
              <div className="dash-kpi-value">{soil.value}</div>
              <div className="dash-kpi-sub">{soil.sub}</div>
            </div>
            <div className="dash-kpi" data-testid="kpi-recoverable">
              <div className="dash-kpi-label">Recoverable / month</div>
              <div className="dash-kpi-value">{roi.value}</div>
              <div className="dash-kpi-sub">{roi.sub}</div>
            </div>
          </div>

          <div className="dash-card" style={{ marginBottom: "1.5rem" }}>
            <div className="dash-card-title">
              <span>Expected vs actual</span>
              <span>
                <span className="dash-badge dash-badge-muted">{BASELINES.find((b) => b.id === data.baseline)?.label ?? data.baseline}</span>
                <SourceBadge source={data.data_source} />
              </span>
            </div>
            <PerformanceChart series={data.series} rainDays={rain} cleaningDays={clean} timeZone={timeZone} />
          </div>

          <div className="dash-card" style={{ marginBottom: "1.5rem" }}>
            <div className="dash-card-title"><span>String peers</span></div>
            {peers && peers.peers.length > 0 ? (
              <PeerTable peers={peers} events={data.events} days={totals} />
            ) : peersFailed ? (
              <div className="dash-error" role="alert">Peers unavailable: the string comparison could not be loaded.</div>
            ) : (
              <EmptyState icon="panel" title="No string comparison yet">
                Peers are compared once a string is flagged or has an open alert and at least four strings report clear-sky hours.
              </EmptyState>
            )}
          </div>

          <div className="dash-card">
            <div className="dash-card-title">
              <span>Soiling</span>
              {data.soiling?.label && data.soiling.label !== "none" && <span className="dash-badge dash-badge-muted">{data.soiling.label}</span>}
            </div>
            {data.soiling && data.soiling.status === "ok" ? (
              <SoilingChart soiling={data.soiling} endDay={data.soiling.day ?? data.series[data.series.length - 1].ts.slice(0, 10)} />
            ) : (
              <EmptyState icon="droplet" title="No soiling estimate yet">
                {data.soiling?.reason ?? "Soiling needs rain or a longer history of clear-sky days."}
              </EmptyState>
            )}
          </div>
        </>
      )}
    </>
  );
}
