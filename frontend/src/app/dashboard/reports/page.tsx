"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/states";
import { plantsApi, reportsApi, type Plant, type ReportSummary } from "@/lib/api";

export default function ReportsPage() {
  const [plants, setPlants] = useState<Plant[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Generator form
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(null);
  const [selectedFormat, setSelectedFormat] = useState<"pdf" | "excel" | "geojson" | "json">("pdf");
  const [irradiance, setIrradiance] = useState<string>("850");
  const [airTemp, setAirTemp] = useState<string>("32");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all([
      plantsApi.list().catch(() => []),
      reportsApi.list().catch(() => []),
    ])
      .then(([plantsData, reportsData]) => {
        setPlants(plantsData);
        setReports(reportsData);
        if (plantsData.length > 0) {
          setSelectedPlantId(plantsData[0].id);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load reports metadata");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleDownload = (reportId: string, format: string) => {
    const url = reportsApi.getDownloadUrl(reportId, format);
    window.open(url, "_blank");
  };

  const handleGenerateCustom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPlantId) return;

    setGenerating(true);
    const reportId = `plant-${selectedPlantId}`;
    handleDownload(reportId, selectedFormat);
    setTimeout(() => setGenerating(false), 800);
  };

  return (
    <>
      <PageHeader
        eyebrow="Documentation & Exports"
        title="Audit & Inspection Reports"
        sub="Generate IEC TS 62446-3 thermographic audit reports, multi-sheet Excel defect summaries, and GIS GeoJSON maps."
      />

      {error && (
        <div className="dash-error" style={{ marginBottom: "1.25rem" }}>
          ⚠ {error}
        </div>
      )}

      {/* Generator Section */}
      <div className="dash-card" style={{ marginBottom: "1.5rem" }}>
        <div className="dash-card-title">Instant Report Generator</div>
        <p style={{ margin: "0 0 1.25rem 0", fontSize: "0.85rem", color: "var(--dash-muted)" }}>
          Select an operating asset to generate IEC-compliant documentation with automated revenue loss modeling.
        </p>

        <form onSubmit={handleGenerateCustom}>
          <div className="dash-form-grid" style={{ marginBottom: "1.25rem" }}>
            <div className="dash-field">
              <label htmlFor="gen-plant">Solar PV Plant</label>
              <select
                id="gen-plant"
                className="dash-input"
                value={selectedPlantId ?? ""}
                onChange={(e) => setSelectedPlantId(Number(e.target.value))}
                required
              >
                {plants.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} (#{p.id}) {p.location ? `· ${p.location}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="dash-field">
              <label htmlFor="gen-format">Document Format</label>
              <select
                id="gen-format"
                className="dash-input"
                value={selectedFormat}
                onChange={(e) => setSelectedFormat(e.target.value as "pdf" | "excel" | "geojson" | "json")}
              >
                <option value="pdf">PDF Audit Report (IEC 62446-3 compliant)</option>
                <option value="excel">Excel Defect Inventory (.xlsx)</option>
                <option value="geojson">GIS GeoJSON Map (.geojson)</option>
                <option value="json">Raw Inspection JSON (.json)</option>
              </select>
            </div>

            <div className="dash-field">
              <label htmlFor="gen-irrad">Inspection Irradiance (W/m²)</label>
              <input
                id="gen-irrad"
                className="dash-input"
                type="number"
                value={irradiance}
                onChange={(e) => setIrradiance(e.target.value)}
              />
            </div>

            <div className="dash-field">
              <label htmlFor="gen-temp">Ambient Temperature (°C)</label>
              <input
                id="gen-temp"
                className="dash-input"
                type="number"
                value={airTemp}
                onChange={(e) => setAirTemp(e.target.value)}
              />
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              type="submit"
              className="dash-btn dash-btn-primary"
              disabled={generating || !selectedPlantId}
              style={{ padding: "0.6rem 1.4rem" }}
            >
              {generating ? "Generating Document…" : `Generate & Download ${selectedFormat.toUpperCase()}`}
            </button>
          </div>
        </form>
      </div>

      {/* Available Reports Table */}
      <div className="dash-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <div className="dash-card-title" style={{ margin: 0 }}>Available Inspection Audits</div>
            <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.82rem", color: "var(--dash-muted)" }}>
              One-click download of verified reports in all standardized engineering formats.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="dash-loading">
            <div className="dash-spinner" />
            <div>Loading report catalog…</div>
          </div>
        ) : reports.length === 0 ? (
          <div className="dash-card dash-empty">
            No inspection reports found. Run an inspection scan from the Inspections dashboard first.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="dash-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Audit Title / Asset</th>
                  <th>Standard</th>
                  <th>Anomalies</th>
                  <th>Generated</th>
                  <th style={{ textAlign: "right" }}>Download Formats</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{r.title}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--dash-muted)" }}>
                        Asset: {r.park_id}
                      </div>
                    </td>
                    <td>
                      <span className="sd-badge sd-badge-muted" style={{ fontSize: "0.72rem" }}>
                        IEC TS 62446-3
                      </span>
                    </td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {r.detections_count != null ? (
                        <span>{r.detections_count} finding(s)</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--dash-muted)" }}>
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : "Live"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: "0.4rem" }}>
                        <button
                          type="button"
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                          style={{ fontSize: "0.74rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => handleDownload(r.id, "pdf")}
                          title="Download PDF Inspection Report"
                        >
                          📄 PDF
                        </button>
                        <button
                          type="button"
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                          style={{ fontSize: "0.74rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => handleDownload(r.id, "excel")}
                          title="Download Excel Defect Inventory"
                        >
                          📊 Excel
                        </button>
                        <button
                          type="button"
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                          style={{ fontSize: "0.74rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => handleDownload(r.id, "geojson")}
                          title="Download GIS GeoJSON Map"
                        >
                          🗺 GeoJSON
                        </button>
                        <button
                          type="button"
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                          style={{ fontSize: "0.74rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => handleDownload(r.id, "json")}
                          title="Download Raw JSON Summary"
                        >
                          { } JSON
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
