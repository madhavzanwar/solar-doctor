"use client";

import React, { useState, useRef } from "react";
import type { ProbabilisticForecastPoint } from "@/lib/api";

interface ProbabilisticBandChartProps {
  points: ProbabilisticForecastPoint[];
  capacityKw: number;
}

const COLORS = {
  p90: "#c9852a",
  p50: "#1a3a2a",
  p10: "#4a6fa5",
  critical: "#9b2c2c",
  high: "#c9852a",
  muted: "#5c665c",
  line: "#c5cdc5",
};

export default function ProbabilisticBandChart({
  points,
  capacityKw,
}: ProbabilisticBandChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [showP90, setShowP90] = useState(true);
  const [showP50, setShowP50] = useState(true);
  const [showP10, setShowP10] = useState(true);
  const [showRibbon, setShowRibbon] = useState(true);
  const svgRef = useRef<SVGSVGElement | null>(null);

  if (!points || points.length === 0) {
    return (
      <div className="dash-empty" style={{ padding: "3rem 1rem" }}>
        No probabilistic forecast data for this selection.
      </div>
    );
  }

  const W = 920;
  const H = 300;
  const PAD = { top: 20, right: 28, bottom: 44, left: 60 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const maxVal = Math.max(
    capacityKw,
    ...points.map((p) => Math.max(p.p90_kw, p.p50_kw, 1))
  );
  const minVal = 0;

  const xScale = (i: number) =>
    PAD.left + (i / Math.max(points.length - 1, 1)) * innerW;
  const yScale = (v: number) =>
    PAD.top +
    innerH -
    ((Math.max(0, v) - minVal) / Math.max(maxVal - minVal, 1)) * innerH;

  const p90Coords = points.map((p, i) => ({ x: xScale(i), y: yScale(p.p90_kw) }));
  const p50Coords = points.map((p, i) => ({ x: xScale(i), y: yScale(p.p50_kw) }));
  const p10Coords = points.map((p, i) => ({ x: xScale(i), y: yScale(p.p10_kw) }));

  const pathFromCoords = (coords: { x: number; y: number }[]) =>
    coords
      .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
      .join(" ");

  const p90Path = pathFromCoords(p90Coords);
  const p50Path = pathFromCoords(p50Coords);
  const p10Path = pathFromCoords(p10Coords);

  const ribbonPath = `${p90Path} ${p10Coords
    .slice()
    .reverse()
    .map((c) => `L${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ")} Z`;

  const yTicks = 4;
  const yGrid = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minVal + ((maxVal - minVal) * i) / yTicks;
    return { y: yScale(val), label: `${Math.round(val)} kW` };
  });

  const stepX = Math.max(1, Math.floor(points.length / 6));
  const xGrid = points
    .filter((_, i) => i % stepX === 0 || i === points.length - 1)
    .map((p) => {
      const idx = points.indexOf(p);
      const d = new Date(p.forecast_time);
      const label = `${d.getHours().toString().padStart(2, "0")}:${d
        .getMinutes()
        .toString()
        .padStart(2, "0")}`;
      return { x: xScale(idx), label };
    });

  const activePoint = hoverIndex != null ? points[hoverIndex] : null;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const normX = (mouseX / rect.width) * W;

    let nearestIdx = 0;
    let minDiff = Infinity;
    for (let i = 0; i < points.length; i++) {
      const diff = Math.abs(xScale(i) - normX);
      if (diff < minDiff) {
        minDiff = diff;
        nearestIdx = i;
      }
    }
    setHoverIndex(nearestIdx);
  };

  const getRiskBadgeColor = (level: string) => {
    switch (level) {
      case "critical":
        return COLORS.critical;
      case "high":
        return COLORS.high;
      case "medium":
        return COLORS.p50;
      default:
        return COLORS.muted;
    }
  };

  const toggleStyle = (active: boolean, color: string): React.CSSProperties => ({
    background: "none",
    border: "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    color: active ? color : COLORS.muted,
    opacity: active ? 1 : 0.45,
    fontWeight: 500,
    fontSize: "0.8rem",
    fontFamily: "inherit",
    padding: 0,
  });

  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "0.75rem",
          marginBottom: "0.85rem",
          padding: "0.65rem 0",
          borderBottom: `1px solid ${COLORS.line}`,
          fontSize: "0.8rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1.1rem", flexWrap: "wrap" }}>
          <button type="button" onClick={() => setShowP90(!showP90)} style={toggleStyle(showP90, COLORS.p90)}>
            <span style={{ width: 14, height: 2, background: COLORS.p90 }} />
            P90
          </button>
          <button type="button" onClick={() => setShowP50(!showP50)} style={toggleStyle(showP50, COLORS.p50)}>
            <span style={{ width: 14, height: 3, background: COLORS.p50 }} />
            P50
          </button>
          <button type="button" onClick={() => setShowP10(!showP10)} style={toggleStyle(showP10, COLORS.p10)}>
            <span style={{ width: 14, height: 2, background: COLORS.p10 }} />
            P10
          </button>
          <button
            type="button"
            onClick={() => setShowRibbon(!showRibbon)}
            style={toggleStyle(showRibbon, "var(--ink)")}
          >
            <span
              style={{
                width: 14,
                height: 10,
                background: "rgba(26,58,42,0.12)",
                border: `1px solid ${COLORS.line}`,
              }}
            />
            Band
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem", color: COLORS.muted }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <span style={{ width: 7, height: 7, background: COLORS.critical, borderRadius: 1 }} />
            Critical
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
            <span style={{ width: 7, height: 7, background: COLORS.high, borderRadius: 1 }} />
            High
          </span>
        </div>
      </div>

      <div className="dash-chart-wrap" style={{ position: "relative" }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="dash-chart-svg"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
          style={{ width: "100%", height: "auto", display: "block", cursor: "crosshair", minWidth: 480 }}
        >
          <defs>
            <linearGradient id="probRibbonGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLORS.p90} stopOpacity="0.18" />
              <stop offset="50%" stopColor={COLORS.p50} stopOpacity="0.1" />
              <stop offset="100%" stopColor={COLORS.p10} stopOpacity="0.06" />
            </linearGradient>
          </defs>

          {yGrid.map(({ y, label }) => (
            <g key={label}>
              <line
                x1={PAD.left}
                y1={y}
                x2={W - PAD.right}
                y2={y}
                stroke={COLORS.line}
                strokeDasharray="2 3"
              />
              <text
                x={PAD.left - 8}
                y={y + 4}
                textAnchor="end"
                fontSize="10"
                fill={COLORS.muted}
              >
                {label}
              </text>
            </g>
          ))}

          {xGrid.map(({ x, label }) => (
            <text
              key={label + x}
              x={x}
              y={H - 14}
              textAnchor="middle"
              fontSize="10"
              fill={COLORS.muted}
            >
              {label}
            </text>
          ))}

          {showRibbon && (
            <path d={ribbonPath} fill="url(#probRibbonGrad)" stroke="none" />
          )}

          {showP90 && (
            <path
              d={p90Path}
              fill="none"
              stroke={COLORS.p90}
              strokeWidth="1.75"
              strokeDasharray="4 3"
              strokeLinecap="round"
            />
          )}

          {showP10 && (
            <path
              d={p10Path}
              fill="none"
              stroke={COLORS.p10}
              strokeWidth="1.75"
              strokeDasharray="3 3"
              strokeLinecap="round"
            />
          )}

          {showP50 && (
            <path
              d={p50Path}
              fill="none"
              stroke={COLORS.p50}
              strokeWidth="2.25"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {points.map((p, idx) => {
            if (p.ramp_risk_level !== "high" && p.ramp_risk_level !== "critical") {
              return null;
            }
            const cx = xScale(idx);
            const cy = yScale(p.p50_kw);
            const isCritical = p.ramp_risk_level === "critical";
            const color = isCritical ? COLORS.critical : COLORS.high;

            return (
              <g key={`ramp-marker-${idx}`}>
                <rect
                  x={cx - (isCritical ? 4 : 3)}
                  y={cy - (isCritical ? 4 : 3)}
                  width={isCritical ? 8 : 6}
                  height={isCritical ? 8 : 6}
                  fill={color}
                />
              </g>
            );
          })}

          {hoverIndex != null && activePoint && (
            <g>
              <line
                x1={xScale(hoverIndex)}
                y1={PAD.top}
                x2={xScale(hoverIndex)}
                y2={PAD.top + innerH}
                stroke={COLORS.muted}
                strokeDasharray="3 3"
                strokeWidth="1"
              />
              <circle
                cx={xScale(hoverIndex)}
                cy={yScale(activePoint.p50_kw)}
                r="5"
                fill={COLORS.p50}
                stroke="#fff"
                strokeWidth="2"
              />
              <circle
                cx={xScale(hoverIndex)}
                cy={yScale(activePoint.p90_kw)}
                r="3.5"
                fill={COLORS.p90}
                stroke="#fff"
                strokeWidth="1.5"
              />
              <circle
                cx={xScale(hoverIndex)}
                cy={yScale(activePoint.p10_kw)}
                r="3.5"
                fill={COLORS.p10}
                stroke="#fff"
                strokeWidth="1.5"
              />
            </g>
          )}
        </svg>

        {hoverIndex != null && activePoint && (
          <div
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              background: "var(--panel)",
              border: `1px solid ${getRiskBadgeColor(activePoint.ramp_risk_level)}`,
              borderRadius: 2,
              padding: "0.85rem 1rem",
              fontSize: "0.8rem",
              minWidth: 220,
              maxWidth: "min(280px, calc(100% - 24px))",
              pointerEvents: "none",
              zIndex: 10,
              boxShadow: "0 8px 24px rgba(20,24,20,0.12)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.5rem",
                marginBottom: "0.5rem",
                borderBottom: `1px solid ${COLORS.line}`,
                paddingBottom: "0.4rem",
              }}
            >
              <span style={{ fontWeight: 600 }}>
                {new Date(activePoint.forecast_time).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span
                className="dash-badge"
                style={{
                  background: `color-mix(in srgb, ${getRiskBadgeColor(activePoint.ramp_risk_level)} 12%, transparent)`,
                  color: getRiskBadgeColor(activePoint.ramp_risk_level),
                }}
              >
                {activePoint.ramp_risk_level}
              </span>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "0.35rem",
                marginBottom: "0.55rem",
              }}
            >
              <div>
                <span style={{ color: COLORS.muted, fontSize: "0.72rem" }}>P50 </span>
                <strong style={{ color: COLORS.p50 }}>{activePoint.p50_kw.toFixed(1)}</strong>
              </div>
              <div>
                <span style={{ color: COLORS.muted, fontSize: "0.72rem" }}>P90 </span>
                <strong style={{ color: COLORS.p90 }}>{activePoint.p90_kw.toFixed(1)}</strong>
              </div>
              <div>
                <span style={{ color: COLORS.muted, fontSize: "0.72rem" }}>P10 </span>
                <strong style={{ color: COLORS.p10 }}>{activePoint.p10_kw.toFixed(1)}</strong>
              </div>
              <div>
                <span style={{ color: COLORS.muted, fontSize: "0.72rem" }}>Band </span>
                <strong>{activePoint.uncertainty_band_kw.toFixed(1)}</strong>
              </div>
            </div>

            <div
              style={{
                borderTop: `1px solid ${COLORS.line}`,
                paddingTop: "0.4rem",
                fontSize: "0.76rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.2rem" }}>
                <span style={{ color: COLORS.muted }}>Ramp</span>
                <span style={{ fontWeight: 600 }}>
                  {activePoint.ramp_rate_kw_per_min > 0 ? "+" : ""}
                  {activePoint.ramp_rate_kw_per_min.toFixed(2)} kW/min
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                <span style={{ color: COLORS.muted }}>BESS</span>
                <span style={{ color: COLORS.p90, fontWeight: 600 }}>
                  {activePoint.bess_reserve_recommendation_kw.toFixed(1)} kW
                </span>
              </div>
              <div
                style={{
                  color: COLORS.muted,
                  marginTop: "0.3rem",
                  fontSize: "0.74rem",
                  lineHeight: 1.4,
                  overflowWrap: "anywhere",
                }}
              >
                {activePoint.reserve_action}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
