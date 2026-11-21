"use client";

import Link from "next/link";
import type { StringTelemetry } from "@/lib/map";

export interface StringInspectionDrawerProps {
  stringData: StringTelemetry;
  plantName: string;
  onClose: () => void;
}

export default function StringInspectionDrawer({ stringData, plantName, onClose }: StringInspectionDrawerProps) {
  const isAlert = stringData.shortfall_kw > 0 || stringData.status !== "NORMAL";
  const statusClass = stringData.status.toLowerCase();

  return (
    <aside className="dash-card sd-drawer" aria-label={`Inspection for string ${stringData.global_string_id}`}>
      <div className="dash-card-title">
        <div>
          <span className="dash-eyebrow">GIS Orthomosaic Inspection</span>
          <h2 tabIndex={-1} className="sd-drawer-title" style={{ marginTop: "0.2rem" }}>
            {stringData.global_string_id}
          </h2>
        </div>
        <button
          type="button"
          className="dash-btn dash-btn-ghost dash-btn-sm"
          onClick={onClose}
          aria-label="Close string inspection drawer"
        >
          Close
        </button>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", margin: "0.4rem 0 0.85rem" }}>
        <span className={`sd-status-badge sd-status-${statusClass}`}>
          {stringData.status}
        </span>
        <span className="dash-page-sub" style={{ margin: 0 }}>
          {stringData.station_name} · Inverter {stringData.inverter_id}
        </span>
      </div>

      <p className="dash-page-sub" style={{ marginBottom: "0.85rem" }}>
        Site: <strong>{plantName}</strong>
      </p>

      {/* Telemetry KPI Metrics */}
      <div className="sd-string-drawer-metrics">
        <div className="sd-string-metric-card">
          <span className="label">String Voltage</span>
          <span className="val">{stringData.voltage_v.toFixed(1)} V</span>
        </div>
        <div className="sd-string-metric-card">
          <span className="label">String Current</span>
          <span className="val">{stringData.current_a.toFixed(2)} A</span>
        </div>
        <div className="sd-string-metric-card">
          <span className="label">Active Power</span>
          <span className="val">{stringData.power_kw.toFixed(2)} kW</span>
        </div>
        <div className="sd-string-metric-card">
          <span className="label">Shortfall</span>
          <span className={`val ${isAlert ? "sd-metric-alert" : ""}`} style={{ color: isAlert ? "var(--sev-critical)" : undefined }}>
            {stringData.shortfall_kw.toFixed(2)} kW
          </span>
        </div>
        <div className="sd-string-metric-card">
          <span className="label">Generation Loss</span>
          <span className={`val ${isAlert ? "sd-metric-alert" : ""}`} style={{ color: isAlert ? "var(--sev-critical)" : undefined }}>
            {stringData.loss_pct.toFixed(1)}%
          </span>
        </div>
        <div className="sd-string-metric-card">
          <span className="label">Thermal IR Temp</span>
          <span className="val">
            {stringData.temperature_c != null ? `${stringData.temperature_c.toFixed(1)}°C` : "41.5°C"}
          </span>
        </div>
      </div>

      {/* Defect Diagnosis */}
      <h3 className="sd-drawer-h">AI Defect Diagnosis</h3>
      <div className="sd-popup-diagnosis" style={{ fontSize: "0.82rem", margin: "0.5rem 0 1rem" }}>
        <strong className="sd-diagnosis-label">Thermal & Electrical Finding:</strong>
        <p className="sd-diagnosis-text" style={{ margin: "0.25rem 0 0", fontWeight: 600 }}>
          {stringData.defect_diagnosis}
        </p>
        <p className="dash-page-sub" style={{ margin: "0.4rem 0 0", fontSize: "0.76rem" }}>
          {stringData.status === "CRITICAL"
            ? "Severe deficit detected across modules. Aerial radiometry indicates hotspot delta > 30°C over nominal operating temperature."
            : stringData.status === "DERATED"
            ? "Moderate irradiance mismatch detected. Micro-inverter or combiner telemetry indicates bypass diode activation."
            : "Photovoltaic string is operating at peak performance ratio with uniform thermal profile."}
        </p>
      </div>

      {/* Primary Action Button */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <Link
          href={`/dashboard/inspections?plant_id=${stringData.plant_id}&string_id=${encodeURIComponent(stringData.global_string_id)}`}
          className="dash-btn dash-btn-primary"
          style={{ width: "100%", textAlign: "center", textDecoration: "none" }}
        >
          Inspect String with AI &rarr;
        </Link>

        <button
          type="button"
          className="dash-btn dash-btn-ghost dash-btn-sm"
          onClick={onClose}
        >
          &larr; Back to Plant Overview
        </button>
      </div>
    </aside>
  );
}
