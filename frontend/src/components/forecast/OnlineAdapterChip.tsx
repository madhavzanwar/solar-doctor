"use client";

import React, { useEffect, useState, useCallback, useRef, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { forecastApi, type OnlineAdapterStatus } from "@/lib/api";

interface OnlineAdapterChipProps {
  plantId: number | string | null;
  /** Full status card vs compact toolbar pill */
  expanded?: boolean;
  onStatusChange?: (status: OnlineAdapterStatus | null) => void;
  className?: string;
}

type AdapterMode = "optimal" | "damping" | "boosted";

function resolveMode(gamma: number, statusLabel: string): AdapterMode {
  if (gamma < 0.95 || statusLabel === "ADAPTING_SOILING_HAZE") return "damping";
  if (gamma > 1.05 || statusLabel === "ADAPTING_ABOVE_NWP") return "boosted";
  return "optimal";
}

const MODE_CONFIG = {
  optimal: {
    color: "var(--field)",
    bg: "rgba(26, 58, 42, 0.08)",
    border: "rgba(26, 58, 42, 0.25)",
    badgeText: "On track",
    shortLabel: "On track",
    description:
      "Live plant output matches the base forecast. No extra correction is needed right now.",
  },
  damping: {
    color: "var(--sun)",
    bg: "rgba(201, 133, 42, 0.12)",
    border: "rgba(201, 133, 42, 0.35)",
    badgeText: "Damping applied",
    shortLabel: "Damping",
    description:
      "Output is running below the weather-based forecast — often haze, aerosols, or panel soiling. Near-term predictions are scaled down.",
  },
  boosted: {
    color: "#2b6cb0",
    bg: "rgba(43, 108, 176, 0.10)",
    border: "rgba(43, 108, 176, 0.3)",
    badgeText: "Boost applied",
    shortLabel: "Boosted",
    description:
      "Output is beating the weather forecast — clearer skies or stronger inverter performance. Near-term predictions are scaled up.",
  },
} as const;

function formatPct(gamma: number): string {
  const pct = ((gamma - 1.0) * 100).toFixed(1);
  return gamma >= 1.0 ? `+${pct}%` : `${pct}%`;
}

/** Map gamma in [0.7, 1.3] to a 0–100% position on the gauge. */
function gammaToGaugePct(gamma: number): number {
  return Math.min(100, Math.max(0, ((gamma - 0.7) / 0.6) * 100));
}

export default function OnlineAdapterChip({
  plantId,
  expanded = false,
  onStatusChange,
  className = "",
}: OnlineAdapterChipProps) {
  const [status, setStatus] = useState<OnlineAdapterStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchStatus = useCallback(
    async (isSilent = false) => {
      if (!plantId) return;
      if (!isSilent) setLoading(true);
      try {
        const data = await forecastApi.getOnlineStatus(plantId);
        setStatus(data);
        setError(null);
        setLastRefreshedAt(new Date());
        onStatusChange?.(data);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Adapter status unavailable";
        setError(msg);
      } finally {
        if (!isSilent) setLoading(false);
      }
    },
    [plantId, onStatusChange]
  );

  useEffect(() => {
    if (!plantId) return;
    fetchStatus();
    const interval = setInterval(() => fetchStatus(true), 30000);
    return () => clearInterval(interval);
  }, [plantId, fetchStatus]);

  const updatePopoverPosition = useCallback(() => {
    const chip = chipRef.current;
    if (!chip) return;

    const rect = chip.getBoundingClientRect();
    const gap = 8;
    const width = Math.min(360, window.innerWidth - 32);
    const estimatedHeight = popoverRef.current?.offsetHeight ?? 280;

    let left = rect.right - width;
    left = Math.max(16, Math.min(left, window.innerWidth - width - 16));

    const spaceBelow = window.innerHeight - rect.bottom - gap;
    const openAbove = spaceBelow < estimatedHeight && rect.top > spaceBelow;
    const top = openAbove
      ? Math.max(16, rect.top - estimatedHeight - gap)
      : rect.bottom + gap;

    setPopoverPos({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (!isDetailsOpen) {
      setPopoverPos(null);
      return;
    }
    updatePopoverPosition();
    // Re-measure after paint so flip-above uses the real popover height.
    const raf = requestAnimationFrame(() => updatePopoverPosition());
    const onReposition = () => updatePopoverPosition();
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [isDetailsOpen, updatePopoverPosition, status, error]);

  if (!plantId) return null;

  const gamma = status?.scaling_factor ?? 1.0;
  const biasKw = status?.bias_kw ?? 0.0;
  const samples = status?.samples_observed_today ?? 0;
  const rmse = status?.recent_rmse_kw ?? 0.0;
  const statusLabel = status?.status ?? "BASELINE_OPTIMAL";
  const mode = resolveMode(gamma, statusLabel);
  const modeConfig = MODE_CONFIG[mode];
  const pctLabel = formatPct(gamma);
  const gaugePct = gammaToGaugePct(gamma);

  if (expanded) {
    return (
      <div
        className={`dash-card online-adapter-panel ${className}`}
        style={{ borderLeft: `4px solid ${modeConfig.color}` }}
      >
        <div className="online-adapter-panel-head">
          <div className="online-adapter-panel-titles">
            <div className="online-adapter-title-row">
              <span
                className="online-adapter-dot"
                style={{ backgroundColor: modeConfig.color, boxShadow: `0 0 0 3px ${modeConfig.bg}` }}
                aria-hidden
              />
              <h2 className="online-adapter-title">Live forecast adjustment</h2>
              <span
                className="dash-badge"
                style={{
                  backgroundColor: modeConfig.bg,
                  color: modeConfig.color,
                  borderColor: modeConfig.border,
                }}
              >
                {modeConfig.badgeText}
              </span>
            </div>
            <p className="online-adapter-lead">
              As SCADA readings arrive, a lightweight adapter nudges the frozen ML forecast so
              near-term power tracks haze, soiling, and equipment drift — without waiting for a
              full model retrain.
            </p>
            <p className="online-adapter-status-desc">{modeConfig.description}</p>
          </div>

          <div className="online-adapter-refresh">
            <span>
              {lastRefreshedAt
                ? `Updated ${lastRefreshedAt.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}`
                : loading
                  ? "Loading…"
                  : "Waiting for status…"}
            </span>
            <button
              type="button"
              onClick={() => fetchStatus(false)}
              disabled={loading}
              className="dash-btn"
              style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}
              title="Refresh adapter status"
            >
              {loading ? "…" : "Refresh"}
            </button>
          </div>
        </div>

        {error && (
          <div className="online-adapter-notice" role="status">
            Status unavailable — showing defaults until the adapter responds. ({error})
          </div>
        )}

        <div className="online-adapter-metrics">
          <div>
            <div className="online-adapter-metric-label">Clearness multiplier</div>
            <div className="online-adapter-metric-value" style={{ color: modeConfig.color }}>
              {gamma.toFixed(3)}×
              <span className="online-adapter-metric-pct">({pctLabel})</span>
            </div>
            <div className="online-adapter-metric-hint">
              Scales the base forecast. 1.00 = no change.
            </div>
          </div>

          <div>
            <div className="online-adapter-metric-label">Bias offset</div>
            <div className="online-adapter-metric-value">
              {biasKw >= 0 ? `+${biasKw.toFixed(1)}` : biasKw.toFixed(1)}
              <span className="online-adapter-metric-unit">kW</span>
            </div>
            <div className="online-adapter-metric-hint">Constant kW shift applied after scaling.</div>
          </div>

          <div>
            <div className="online-adapter-metric-label">Recent error</div>
            <div className="online-adapter-metric-value">
              {rmse.toFixed(1)}
              <span className="online-adapter-metric-unit">kW</span>
            </div>
            <div className="online-adapter-metric-hint">
              Rolling gap between adapted forecast and measured power.
            </div>
          </div>

          <div>
            <div className="online-adapter-metric-label">Samples today</div>
            <div className="online-adapter-metric-value">{samples}</div>
            <div className="online-adapter-metric-hint">SCADA cycles used to learn today.</div>
          </div>
        </div>

        <div className="online-adapter-gauge">
          <div className="online-adapter-gauge-labels">
            <span>More damping</span>
            <span className="online-adapter-gauge-mid">Baseline (1.00×)</span>
            <span>More boost</span>
          </div>
          <div className="online-adapter-gauge-track" aria-hidden>
            <div className="online-adapter-gauge-center" />
            <div
              className="online-adapter-gauge-marker"
              style={{
                left: `${gaugePct}%`,
                backgroundColor: modeConfig.color,
              }}
            />
          </div>
          <div className="online-adapter-gauge-scale">
            <span>0.70×</span>
            <span>1.00×</span>
            <span>1.30×</span>
          </div>
        </div>

        <p className="online-adapter-footnote">
          Base ML model stays frozen. Only this small correction updates as telemetry streams in
          {status?.last_updated
            ? ` · Last reading ${new Date(status.last_updated).toLocaleTimeString()}`
            : ""}
          .
        </p>
      </div>
    );
  }

  const popover =
    isDetailsOpen &&
    typeof document !== "undefined" &&
    createPortal(
      <>
        <div
          className="online-adapter-popover-backdrop"
          onClick={() => setIsDetailsOpen(false)}
          aria-hidden
        />
        <div
          ref={popoverRef}
          className="online-adapter-popover"
          role="dialog"
          aria-label="Live forecast adjustment"
          style={
            popoverPos
              ? { top: popoverPos.top, left: popoverPos.left, right: "auto" }
              : { visibility: "hidden", top: 0, left: 0, right: "auto" }
          }
        >
          <div className="online-adapter-popover-head">
            <span>Live forecast adjustment</span>
            <button
              type="button"
              onClick={() => setIsDetailsOpen(false)}
              className="online-adapter-popover-close"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          {error && (
            <div className="online-adapter-notice" style={{ marginBottom: "0.65rem" }}>
              {error}
            </div>
          )}

          <p className="online-adapter-popover-desc">
            Corrects near-term forecasts from live plant readings when weather models miss haze,
            soiling, or efficiency drift.
          </p>
          <p className="online-adapter-status-desc" style={{ marginBottom: "0.75rem" }}>
            {modeConfig.description}
          </p>

          <div className="online-adapter-popover-grid">
            <div>
              <div className="online-adapter-metric-label">Multiplier</div>
              <div style={{ fontWeight: 700, color: modeConfig.color, fontSize: "1rem" }}>
                {gamma.toFixed(3)}× ({pctLabel})
              </div>
            </div>
            <div>
              <div className="online-adapter-metric-label">Bias</div>
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>
                {biasKw >= 0 ? `+${biasKw.toFixed(1)}` : biasKw.toFixed(1)} kW
              </div>
            </div>
            <div>
              <div className="online-adapter-metric-label">Recent error</div>
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>{rmse.toFixed(1)} kW</div>
            </div>
            <div>
              <div className="online-adapter-metric-label">Samples today</div>
              <div style={{ fontWeight: 700, fontSize: "1rem" }}>{samples}</div>
            </div>
          </div>

          <p
            className="online-adapter-footnote"
            style={{ marginTop: "0.75rem", borderTop: "1px solid var(--line)", paddingTop: "0.5rem" }}
          >
            Open the Online learning tab for the full comparison chart and calibration log.
          </p>
        </div>
      </>,
      document.body
    );

  return (
    <div className={`online-adapter-chip-container ${className}`}>
      <button
        ref={chipRef}
        type="button"
        onClick={() => setIsDetailsOpen((prev) => !prev)}
        className="online-adapter-chip"
        style={{
          borderColor: modeConfig.border,
          background: modeConfig.bg,
          color: modeConfig.color,
        }}
        title="View live forecast adjustment details"
        aria-expanded={isDetailsOpen}
      >
        <span
          className="online-adapter-dot"
          style={{
            width: 8,
            height: 8,
            backgroundColor: modeConfig.color,
            boxShadow: `0 0 0 2px ${modeConfig.border}`,
          }}
          aria-hidden
        />
        <span>Live adjust</span>
        <span className="online-adapter-chip-value">{pctLabel}</span>
        <span
          className="online-adapter-chip-mode"
          style={{ borderLeftColor: modeConfig.border }}
        >
          {modeConfig.shortLabel}
        </span>
        <span className="online-adapter-chip-caret" aria-hidden>
          ▾
        </span>
      </button>

      {popover}
    </div>
  );
}
