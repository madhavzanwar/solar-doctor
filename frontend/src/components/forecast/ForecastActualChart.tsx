"use client";

import React, { useState, useRef, useMemo } from "react";
import type { ForecastRecord } from "@/lib/api";

interface ForecastActualChartProps {
  records: ForecastRecord[];
  capacityKw?: number;
  height?: number;
  showControls?: boolean;
  className?: string;
}

export default function ForecastActualChart({
  records,
  capacityKw,
  height = 280,
  showControls = true,
  className = "",
}: ForecastActualChartProps) {
  const [showBase, setShowBase] = useState(true);
  const [showCorrected, setShowCorrected] = useState(true);
  const [showActual, setShowActual] = useState(true);
  const [showDelta, setShowDelta] = useState(false);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Sort ascending by forecast time
  const sortedRecords = useMemo(() => {
    return [...records].sort(
      (a, b) => new Date(a.forecast_time).getTime() - new Date(b.forecast_time).getTime()
    );
  }, [records]);

  // Overall statistics
  const deltaSummary = useMemo(() => {
    if (!sortedRecords || sortedRecords.length < 2) {
      return { avgDelta: 0, actualCount: 0, maeBase: null, maeAdapted: null };
    }
    let sumDelta = 0;
    let actualCount = 0;
    let sumMaeBase = 0;
    let sumMaeAdapted = 0;

    sortedRecords.forEach((r) => {
      const b = r.ml_power_kw ?? r.predicted_power_kw;
      const c = r.predicted_power_kw;
      sumDelta += c - b;

      if (r.actual_power_kw != null) {
        actualCount++;
        sumMaeBase += Math.abs(r.actual_power_kw - b);
        sumMaeAdapted += Math.abs(r.actual_power_kw - c);
      }
    });

    const avgDelta = sumDelta / sortedRecords.length;
    const maeBase = actualCount > 0 ? sumMaeBase / actualCount : null;
    const maeAdapted = actualCount > 0 ? sumMaeAdapted / actualCount : null;

    return { avgDelta, actualCount, maeBase, maeAdapted };
  }, [sortedRecords]);

  if (!sortedRecords || sortedRecords.length < 2) {
    return (
      <div className="dash-empty" style={{ padding: "2.5rem 1rem", textAlign: "center" }}>
        Need at least two forecast points to draw the comparison. Generate another forecast to continue.
      </div>
    );
  }

  const W = 860;
  const H = height;
  const PAD = { top: 20, right: 24, bottom: 40, left: 56 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  // Compute domain
  const maxRecorded = Math.max(
    ...sortedRecords.map((r) =>
      Math.max(
        r.predicted_power_kw,
        r.ml_power_kw ?? 0,
        r.actual_power_kw ?? 0
      )
    ),
    10
  );
  const maxVal = capacityKw ? Math.max(capacityKw, maxRecorded) : maxRecorded * 1.05;
  const minVal = 0;

  const xScale = (i: number) =>
    PAD.left + (i / Math.max(sortedRecords.length - 1, 1)) * innerW;
  const yScale = (v: number) =>
    PAD.top + innerH - ((Math.max(0, v) - minVal) / Math.max(maxVal - minVal, 1)) * innerH;

  // Path coordinates
  const correctedCoords = sortedRecords.map((r, i) => ({
    x: xScale(i),
    y: yScale(r.predicted_power_kw),
    val: r.predicted_power_kw,
  }));

  const baseCoords = sortedRecords.map((r, i) => {
    const val = r.ml_power_kw != null ? r.ml_power_kw : r.predicted_power_kw;
    return { x: xScale(i), y: yScale(val), val };
  });

  const actualPoints = sortedRecords
    .map((r, i) => ({
      i,
      x: xScale(i),
      y: r.actual_power_kw != null ? yScale(r.actual_power_kw) : null,
      val: r.actual_power_kw,
    }))
    .filter((pt): pt is { i: number; x: number; y: number; val: number } => pt.y != null);

  const makeLinePath = (coords: { x: number; y: number }[]) =>
    coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");

  const correctedPath = makeLinePath(correctedCoords);
  const basePath = makeLinePath(baseCoords);

  const actualPath = actualPoints
    .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ");

  // Shaded area for corrected
  const firstX = xScale(0);
  const lastX = xScale(sortedRecords.length - 1);
  const zeroY = yScale(0);
  const correctedArea = `${correctedPath} L${lastX},${zeroY} L${firstX},${zeroY} Z`;

  // Delta ribbon between base and corrected
  const deltaRibbon = `${correctedPath} ${baseCoords
    .slice()
    .reverse()
    .map((c) => `L${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ")} Z`;

  // Y-axis grid ticks
  const yTicks = 4;
  const yGrid = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minVal + ((maxVal - minVal) * i) / yTicks;
    return { y: yScale(val), label: `${Math.round(val)}` };
  });

  // X-axis time ticks
  const stepX = Math.max(1, Math.floor(sortedRecords.length / 6));
  const xGrid = sortedRecords
    .filter((_, i) => i % stepX === 0 || i === sortedRecords.length - 1)
    .map((r) => {
      const idx = sortedRecords.indexOf(r);
      const d = new Date(r.forecast_time);
      const label = `${d.getHours().toString().padStart(2, "0")}:${d
        .getMinutes()
        .toString()
        .padStart(2, "0")}`;
      return { x: xScale(idx), label };
    });

  // Mouse hover tracking
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgX = (mouseX / rect.width) * W;

    // Find closest index
    const clampedX = Math.max(PAD.left, Math.min(W - PAD.right, svgX));
    const ratio = (clampedX - PAD.left) / innerW;
    const closestIdx = Math.round(ratio * (sortedRecords.length - 1));
    setHoverIndex(closestIdx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  const activeRecord = hoverIndex != null ? sortedRecords[hoverIndex] : null;
  const activeBase = activeRecord
    ? activeRecord.ml_power_kw ?? activeRecord.predicted_power_kw
    : 0;
  const activeCorrected = activeRecord ? activeRecord.predicted_power_kw : 0;
  const activeActual = activeRecord?.actual_power_kw;
  const activeDelta = activeCorrected - activeBase;
  const activeDeltaPct = activeBase > 0 ? (activeDelta / activeBase) * 100 : 0;


  return (
    <div className={`forecast-actual-chart-wrap ${className}`} style={{ width: "100%" }}>
      {showControls && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
            marginBottom: "0.85rem",
            padding: "0 0.25rem",
          }}
        >
          {/* Layer toggles */}
          <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontWeight: 600,
                color: showCorrected ? "var(--field)" : "var(--dash-muted)",
              }}
            >
              <input
                type="checkbox"
                checked={showCorrected}
                onChange={(e) => setShowCorrected(e.target.checked)}
              />
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: 3,
                  backgroundColor: "var(--field)",
                  borderRadius: 2,
                }}
              />
              Adapted forecast
            </label>

            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontWeight: 600,
                color: showBase ? "#4a5568" : "var(--dash-muted)",
              }}
            >
              <input
                type="checkbox"
                checked={showBase}
                onChange={(e) => setShowBase(e.target.checked)}
              />
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: 0,
                  borderTop: "2px dashed #718096",
                }}
              />
              Base forecast
            </label>

            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.8rem",
                cursor: "pointer",
                fontWeight: 600,
                color: showActual ? "var(--sun)" : "var(--dash-muted)",
              }}
            >
              <input
                type="checkbox"
                checked={showActual}
                onChange={(e) => setShowActual(e.target.checked)}
              />
              <span
                style={{
                  display: "inline-block",
                  width: 14,
                  height: 2,
                  backgroundColor: "var(--sun)",
                }}
              />
              Actual output
            </label>

            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontSize: "0.78rem",
                cursor: "pointer",
                color: showDelta ? "var(--ink)" : "var(--dash-muted)",
              }}
            >
              <input
                type="checkbox"
                checked={showDelta}
                onChange={(e) => setShowDelta(e.target.checked)}
              />
              Show adjustment band
            </label>
          </div>

          <div style={{ fontSize: "0.78rem", color: "var(--dash-muted)" }}>
            Avg adjustment:{" "}
            <span
              style={{
                fontWeight: 700,
                color: deltaSummary.avgDelta < 0 ? "var(--sun)" : "var(--field)",
              }}
            >
              {deltaSummary.avgDelta >= 0 ? `+${deltaSummary.avgDelta.toFixed(1)}` : deltaSummary.avgDelta.toFixed(1)} kW
            </span>
            {deltaSummary.maeAdapted != null && deltaSummary.maeBase != null && (
              <span style={{ marginLeft: "0.75rem" }}>
                Avg error after adapt: <strong>{deltaSummary.maeAdapted.toFixed(1)} kW</strong>{" "}
                <span style={{ fontSize: "0.7rem", color: "var(--dash-muted)" }}>
                  (base was {deltaSummary.maeBase.toFixed(1)} kW)
                </span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Main SVG Plot */}
      <div style={{ position: "relative", width: "100%" }}>
        <svg
          ref={svgRef}
          className="dash-chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={{ width: "100%", height, display: "block", cursor: "crosshair" }}
        >
          <defs>
            <linearGradient id="correctedAreaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--field)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--field)" stopOpacity="0.01" />
            </linearGradient>
            <linearGradient id="deltaRibbonGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--sun)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--sun)" stopOpacity="0.05" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {yGrid.map(({ y, label }) => (
            <g key={label + y}>
              <line
                x1={PAD.left}
                y1={y}
                x2={W - PAD.right}
                y2={y}
                stroke="var(--line)"
                strokeWidth="1"
                strokeDasharray="2 3"
              />
              <text
                x={PAD.left - 8}
                y={y + 4}
                textAnchor="end"
                fontSize="10"
                fill="var(--muted)"
                fontWeight="500"
              >
                {label} kW
              </text>
            </g>
          ))}

          {xGrid.map(({ x, label }) => (
            <text
              key={label + x}
              x={x}
              y={H - 12}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {label}
            </text>
          ))}

          {/* Axes */}
          <line
            x1={PAD.left}
            y1={PAD.top}
            x2={PAD.left}
            y2={H - PAD.bottom}
            stroke="var(--line)"
            strokeWidth="1"
          />
          <line
            x1={PAD.left}
            y1={H - PAD.bottom}
            x2={W - PAD.right}
            y2={H - PAD.bottom}
            stroke="var(--line)"
            strokeWidth="1"
          />

          {/* Delta ribbon */}
          {showDelta && showBase && showCorrected && (
            <path d={deltaRibbon} fill="url(#deltaRibbonGrad)" />
          )}

          {/* Corrected Area Fill */}
          {showCorrected && (
            <path d={correctedArea} fill="url(#correctedAreaGrad)" />
          )}

          {/* Base Model (Tier-1 LightGBM) — Dashed Slate Line */}
          {showBase && (
            <path
              d={basePath}
              fill="none"
              stroke="#718096"
              strokeWidth="1.8"
              strokeDasharray="5 3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Online Corrected (Tier-2) — Solid Emerald Line */}
          {showCorrected && (
            <path
              d={correctedPath}
              fill="none"
              stroke="var(--field)"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Actual SCADA Telemetry — Solid Gold Line with Dots */}
          {showActual && actualPath && (
            <>
              <path
                d={actualPath}
                fill="none"
                stroke="var(--sun)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {actualPoints.map((pt) => (
                <circle
                  key={`act-${pt.i}`}
                  cx={pt.x}
                  cy={pt.y}
                  r={3.5}
                  fill="var(--sun)"
                  stroke="var(--panel)"
                  strokeWidth="1.5"
                />
              ))}
            </>
          )}

          {/* Crosshair on Hover */}
          {hoverIndex != null && (
            <g>
              <line
                x1={xScale(hoverIndex)}
                y1={PAD.top}
                x2={xScale(hoverIndex)}
                y2={H - PAD.bottom}
                stroke="var(--ink)"
                strokeWidth="1"
                strokeDasharray="3 3"
                opacity={0.5}
              />
              {showCorrected && (
                <circle
                  cx={correctedCoords[hoverIndex].x}
                  cy={correctedCoords[hoverIndex].y}
                  r={5}
                  fill="var(--field)"
                  stroke="#fff"
                  strokeWidth="2"
                />
              )}
              {showBase && (
                <circle
                  cx={baseCoords[hoverIndex].x}
                  cy={baseCoords[hoverIndex].y}
                  r={4}
                  fill="#718096"
                  stroke="#fff"
                  strokeWidth="1.5"
                />
              )}
              {showActual && activeActual != null && (
                <circle
                  cx={xScale(hoverIndex)}
                  cy={yScale(activeActual)}
                  r={5}
                  fill="var(--sun)"
                  stroke="#fff"
                  strokeWidth="2"
                />
              )}
            </g>
          )}
        </svg>

        {/* Hover Tooltip Box */}
        {hoverIndex != null && activeRecord && (
          <div
            style={{
              position: "absolute",
              top: 12,
              left: Math.min(
                Math.max(10, xScale(hoverIndex) - 100),
                W - 220
              ),
              background: "var(--panel)",
              border: "1px solid var(--line)",
              borderRadius: "5px",
              boxShadow: "0 4px 14px rgba(0,0,0,0.12)",
              padding: "0.55rem 0.75rem",
              fontSize: "0.76rem",
              pointerEvents: "none",
              zIndex: 10,
              minWidth: "190px",
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: "0.35rem", color: "var(--ink)", borderBottom: "1px solid var(--line)", paddingBottom: "0.2rem" }}>
              {new Date(activeRecord.forecast_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              <span style={{ fontWeight: 400, color: "var(--dash-muted)", marginLeft: "0.35rem" }}>
                {new Date(activeRecord.forecast_time).toLocaleDateString([], { month: "short", day: "numeric" })}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", color: "var(--field)", fontWeight: 600 }}>
              <span>Adapted:</span>
              <span>{activeCorrected.toFixed(1)} kW</span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", color: "#4a5568", marginTop: "0.15rem" }}>
              <span>Base:</span>
              <span>{activeBase.toFixed(1)} kW</span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", color: activeDelta < 0 ? "var(--sun)" : "var(--field)", marginTop: "0.15rem", fontWeight: 600 }}>
              <span>Adjustment:</span>
              <span>
                {activeDelta >= 0 ? `+${activeDelta.toFixed(1)}` : activeDelta.toFixed(1)} kW ({activeDeltaPct >= 0 ? `+${activeDeltaPct.toFixed(1)}` : activeDeltaPct.toFixed(1)}%)
              </span>
            </div>

            {activeActual != null ? (
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", color: "var(--sun)", fontWeight: 700, marginTop: "0.25rem", borderTop: "1px dashed var(--line)", paddingTop: "0.2rem" }}>
                <span>Actual:</span>
                <span>{activeActual.toFixed(1)} kW</span>
              </div>
            ) : (
              <div style={{ color: "var(--dash-muted)", fontSize: "0.7rem", marginTop: "0.2rem" }}>
                No measured reading yet
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
