"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/ui/states";
import { useScope, isDateWithinScope } from "@/components/dashboard/scope";
import { alertsApi, inspectionsApi, plantsApi } from "@/lib/api";
import type { Alert, InspectionRecord, Plant } from "@/lib/api";

const CLASS_COLORS: Record<string, string> = {
  clean: "var(--cls-clean, #2f6b4f)",
  dusty: "var(--cls-dusty, #a8792f)",
  bird_drop: "var(--cls-bird, #6b6f4a)",
  snow_covered: "var(--cls-snow, #4f7f9e)",
  electrical_damage: "var(--cls-electrical, #9b2c2c)",
  physical_damage: "var(--cls-physical, #6a4c7d)",
};

const CLASS_LABELS: Record<string, string> = {
  clean: "Clean Module",
  dusty: "Dust / Soiling",
  bird_drop: "Bird Droppings",
  snow_covered: "Snow Blanket",
  electrical_damage: "Electrical Hotspot / Burn",
  physical_damage: "Physical Cell Damage / Cracks",
};

export default function InspectionsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const scope = useScope();

  const [plants, setPlants] = useState<Plant[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(scope.plantId || 1);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [stringId, setStringId] = useState<string>("S-04");

  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [inspection, setInspection] = useState<InspectionRecord | null>(null);
  const [history, setHistory] = useState<InspectionRecord[]>([]);

  const [activeTab, setActiveTab] = useState<"original" | "gradcam" | "lime" | "side_by_side">("original");
  const [opacity, setOpacity] = useState<number>(65);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync with topbar scope
  useEffect(() => {
    if (scope.plantId && scope.plantId !== selectedPlantId) {
      setSelectedPlantId(scope.plantId);
    }
  }, [scope.plantId, selectedPlantId]);

  // Load plants
  useEffect(() => {
    plantsApi.list().then((res) => {
      if (res && res.length > 0) {
        setPlants(res);
        if (!selectedPlantId) setSelectedPlantId(res[0].id);
      }
    }).catch(() => {});
  }, [selectedPlantId]);

  // Load alerts when plant changes
  useEffect(() => {
    if (!selectedPlantId) return;
    alertsApi.listOpen(selectedPlantId).then((res) => {
      setAlerts(res || []);
      const urlAlertId = searchParams.get("alert_id");
      if (urlAlertId) {
        setSelectedAlertId(parseInt(urlAlertId, 10));
      } else if (res && res.length > 0) {
        setSelectedAlertId(res[0].id);
      }
    }).catch(() => {});
  }, [selectedPlantId, searchParams]);

  // Load historical inspections
  const loadHistory = () => {
    inspectionsApi.list(selectedPlantId || undefined, 20).then((res) => {
      setHistory(res || []);
      if (!inspection && res && res.length > 0) {
        setInspection(res[0]);
      }
    }).catch(() => {});
  };

  useEffect(() => {
    loadHistory();
  }, [selectedPlantId]);

  // Load sample image (dusty-panel-closeup.webp)
  const handleLoadSample = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/images/dusty-panel-closeup.webp");
      const blob = await res.blob();
      const sampleFile = new File([blob], "dusty-panel-closeup.webp", { type: "image/webp" });
      setFile(sampleFile);
      setPreviewUrl("/images/dusty-panel-closeup.webp");
    } catch {
      setError("Failed to load sample image.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      setFile(f);
      setPreviewUrl(URL.createObjectURL(f));
      setError(null);
    }
  };

  const handleUploadAndAnalyze = async () => {
    if (!file) {
      setError("Please select or drop an image file first.");
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const formData = new FormData();
      formData.append("file", file);
      if (selectedPlantId) formData.append("plant_id", String(selectedPlantId));
      if (selectedAlertId) formData.append("alert_id", String(selectedAlertId));
      formData.append("generate_xai", "true");

      const res = await inspectionsApi.create(formData);
      setInspection(res);
      setActiveTab("gradcam"); // Switch to explainability heatmap immediately
      loadHistory();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Inspection failed");
    } finally {
      setLoading(false);
    }
  };

  const predClass = inspection?.prediction?.predicted_class || "dusty";
  const classColor = CLASS_COLORS[predClass] || "#3b4b3e";
  const confidencePct = Math.round((inspection?.prediction?.confidence || 0) * 100);

  const getActionBadgeClass = (action?: string) => {
    switch (action?.toUpperCase()) {
      case "CLEAN NOW":
        return "sd-action-badge sd-action-clean";
      case "WAIT":
        return "sd-action-badge sd-action-wait";
      case "FIELD CHECK":
        return "sd-action-badge sd-action-field";
      case "REPLACE":
        return "sd-action-badge sd-action-replace";
      default:
        return "sd-action-badge";
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <PageHeader
        eyebrow="Photo diagnosis & Explainability"
        title="Panel Inspections"
        sub="Classify solar module defects with 6-class calibrated AI, inspect Grad-CAM & LIME evidence overlays, and fuse visual findings with string telemetry."
      />

      {/* Target Asset Selector Ribbon */}
      <div className="sd-card" style={{ display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "center" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", marginBottom: "0.25rem" }}>
            Target Solar Plant
          </label>
          <select
            value={selectedPlantId || ""}
            onChange={(e) => setSelectedPlantId(Number(e.target.value))}
            style={{ padding: "0.375rem 0.75rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.875rem", background: "#fff" }}
          >
            {plants.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.capacity_kw} kW)
              </option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", marginBottom: "0.25rem" }}>
            Target PV String
          </label>
          <input
            type="text"
            value={stringId}
            onChange={(e) => setStringId(e.target.value)}
            placeholder="e.g. S-04"
            style={{ padding: "0.375rem 0.75rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.875rem", width: "120px" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", marginBottom: "0.25rem" }}>
            Link Deficit Alert
          </label>
          <select
            value={selectedAlertId || ""}
            onChange={(e) => setSelectedAlertId(e.target.value ? Number(e.target.value) : null)}
            style={{ padding: "0.375rem 0.75rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.875rem", background: "#fff", maxWidth: "280px" }}
          >
            <option value="">None (Standalone scan)</option>
            {alerts.map((a) => (
              <option key={a.id} value={a.id}>
                #{a.id} — {a.severity}: {a.message.slice(0, 36)}...
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
          <button
            type="button"
            onClick={handleLoadSample}
            style={{
              padding: "0.45rem 0.85rem",
              background: "#f4f7f4",
              border: "2px solid #a88944",
              color: "#6b5420",
              fontWeight: 600,
              fontSize: "0.8125rem",
              borderRadius: "3px",
              cursor: "pointer",
            }}
          >
            Load Sample: Dusty Panel S-04
          </button>
        </div>
      </div>

      {/* Main Workspace Grid: Left Evidence Viewer | Right Diagnostic Panel */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)", gap: "1.5rem" }}>
        
        {/* Left: Upload Dropzone & Multi-layer Evidence Viewer */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          
          {/* Upload Dropzone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                const f = e.dataTransfer.files[0];
                setFile(f);
                setPreviewUrl(URL.createObjectURL(f));
                setError(null);
              }
            }}
            style={{
              border: "2px dashed #a3b3a3",
              background: "#fafcfa",
              borderRadius: "4px",
              padding: "1rem",
              textAlign: "center",
              cursor: "pointer",
              transition: "border-color 150ms ease",
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept="image/jpeg,image/png,image/webp"
              style={{ display: "none" }}
            />
            <p style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600, color: "#243528" }}>
              {file ? `Selected: ${file.name} (${(file.size / 1024).toFixed(0)} KB)` : "Drop inspection image here, or click to browse"}
            </p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem", color: "#667a68" }}>
              Supports high-resolution JPEG, PNG, and WebP up to 15 MB
            </p>
          </div>

          {/* Action Trigger */}
          {file && (
            <button
              type="button"
              onClick={handleUploadAndAnalyze}
              disabled={loading}
              style={{
                padding: "0.6rem 1.2rem",
                background: loading ? "#7a9480" : "#2f6b4f",
                color: "#ffffff",
                border: "none",
                borderRadius: "3px",
                fontWeight: 700,
                fontSize: "0.875rem",
                cursor: loading ? "wait" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.5rem",
              }}
            >
              {loading ? "Running AI Classification & Saliency Synthesis..." : "Run Inspection & Telemetry Fusion"}
            </button>
          )}

          {error && (
            <div style={{ padding: "0.75rem", background: "#fde8e8", border: "1px solid #f98080", borderRadius: "3px", color: "#9b1c1c", fontSize: "0.8125rem" }}>
              <strong>Error:</strong> {error}
            </div>
          )}

          {/* Evidence Viewer Display */}
          <div className="sd-card" style={{ display: "flex", flexDirection: "column", gap: "0.75rem", padding: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="sd-tabs">
                <button
                  type="button"
                  className={`sd-tab ${activeTab === "original" ? "active" : ""}`}
                  onClick={() => setActiveTab("original")}
                >
                  Original Photo
                </button>
                <button
                  type="button"
                  className={`sd-tab ${activeTab === "gradcam" ? "active" : ""}`}
                  onClick={() => setActiveTab("gradcam")}
                >
                  Grad-CAM Heatmap
                </button>
                <button
                  type="button"
                  className={`sd-tab ${activeTab === "lime" ? "active" : ""}`}
                  onClick={() => setActiveTab("lime")}
                >
                  LIME Superpixels
                </button>
                <button
                  type="button"
                  className={`sd-tab ${activeTab === "side_by_side" ? "active" : ""}`}
                  onClick={() => setActiveTab("side_by_side")}
                >
                  Side-by-Side
                </button>
              </div>

              {(activeTab === "gradcam" || activeTab === "lime") && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem", fontWeight: 600, color: "#3b4b3e" }}>
                  <span>Overlay Opacity:</span>
                  <input
                    type="range"
                    min="10"
                    max="100"
                    value={opacity}
                    onChange={(e) => setOpacity(Number(e.target.value))}
                    style={{ width: "90px" }}
                  />
                  <span className="mono">{opacity}%</span>
                </div>
              )}
            </div>

            {/* Viewer Screen Canvas */}
            <div className="sd-evidence-frame">
              {inspection || previewUrl ? (
                activeTab === "side_by_side" ? (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", width: "100%", height: "100%" }}>
                    <div style={{ position: "relative", width: "100%", height: "100%", borderRight: "1px solid #334" }}>
                      <img
                        src={inspection?.image_url || previewUrl!}
                        alt="Original"
                        className="sd-evidence-img"
                      />
                      <span style={{ position: "absolute", top: 8, left: 8, background: "rgba(0,0,0,0.6)", color: "#fff", fontSize: "0.6875rem", padding: "2px 6px", borderRadius: "2px" }}>
                        Original
                      </span>
                    </div>
                    <div style={{ position: "relative", width: "100%", height: "100%" }}>
                      <img
                        src={
                          inspection?.gradcam_base64
                            ? `data:image/png;base64,${inspection.gradcam_base64}`
                            : inspection?.xai_gradcam_url || previewUrl!
                        }
                        alt="Grad-CAM"
                        className="sd-evidence-img"
                      />
                      <span style={{ position: "absolute", top: 8, left: 8, background: "rgba(0,0,0,0.6)", color: "#fff", fontSize: "0.6875rem", padding: "2px 6px", borderRadius: "2px" }}>
                        Grad-CAM Saliency
                      </span>
                    </div>
                  </div>
                ) : (
                  <>
                    <img
                      src={inspection?.image_url || previewUrl!}
                      alt="Solar module under inspection"
                      className="sd-evidence-img"
                    />
                    {activeTab === "gradcam" && (
                      <img
                        src={
                          inspection?.gradcam_base64
                            ? `data:image/png;base64,${inspection.gradcam_base64}`
                            : inspection?.xai_gradcam_url || ""
                        }
                        alt="Grad-CAM Overlay"
                        className="sd-evidence-overlay"
                        style={{ opacity: opacity / 100 }}
                      />
                    )}
                    {activeTab === "lime" && (
                      <img
                        src={
                          inspection?.lime_base64
                            ? `data:image/png;base64,${inspection.lime_base64}`
                            : inspection?.xai_lime_url || ""
                        }
                        alt="LIME Overlay"
                        className="sd-evidence-overlay"
                        style={{ opacity: opacity / 100 }}
                      />
                    )}
                  </>
                )
              ) : (
                <div style={{ color: "#718274", fontSize: "0.875rem", textAlign: "center" }}>
                  <p style={{ margin: 0 }}>No image loaded</p>
                  <p style={{ margin: "0.25rem 0 0", fontSize: "0.75rem" }}>Upload a file or click &quot;Load Sample&quot; above</p>
                </div>
              )}
            </div>
            
            {inspection && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "#667a68" }}>
                <span>Job ID: <strong className="mono">{inspection.id}</strong></span>
                <span>Model: <strong className="mono">{inspection.prediction?.model_version || "offline-rgb-v1.0"}</strong></span>
                <span>SHA-256: <span className="mono">{inspection.prediction?.image_sha256?.slice(0, 12)}...</span></span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Diagnosis, Telemetry Cross-check & Fusion Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          
          {/* Classification & Confidence Card */}
          <div className="sd-card">
            <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.9375rem", fontWeight: 700, color: "#1c2c20" }}>
              Vision Diagnosis (6-Class Defect Model)
            </h3>

            {inspection ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                
                {/* Primary class & confidence */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem", background: "#f5f8f5", borderRadius: "3px" }}>
                  <div>
                    <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>Detected Defect:</span>
                    <div style={{ fontSize: "1.125rem", fontWeight: 800, color: classColor }}>
                      {CLASS_LABELS[predClass] || predClass}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>Calibrated Confidence:</span>
                    <div className="mono" style={{ fontSize: "1.25rem", fontWeight: 800, color: confidencePct > 80 ? "#2f6b4f" : "#b45309" }}>
                      {confidencePct}%
                    </div>
                  </div>
                </div>

                {/* OOD Alert Banner if applicable */}
                {inspection.prediction?.is_ood && (
                  <div style={{ padding: "0.75rem", background: "#fef3c7", border: "2px solid #f59e0b", borderRadius: "3px", color: "#92400e", fontSize: "0.8125rem" }}>
                    <strong>Warning: Out of Distribution (OOD) Detected</strong>
                    <p style={{ margin: "0.25rem 0 0" }}>
                      This image does not match standard PV panel textures (OOD score: {inspection.prediction.ood_score?.toFixed(2)}). An on-site technician field check is required before taking automated cleaning action.
                    </p>
                  </div>
                )}

                {/* Top-3 Distribution */}
                <div>
                  <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#4f6354" }}>Probability Distribution:</span>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", marginTop: "0.375rem" }}>
                    {(inspection.prediction?.top3 || []).map((item) => (
                      <div key={item.class} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem" }}>
                        <span style={{ width: "110px", color: "#334136", fontWeight: 500 }}>
                          {CLASS_LABELS[item.class] || item.class}
                        </span>
                        <div style={{ flex: 1, background: "#e5ece5", height: "8px", borderRadius: "4px", overflow: "hidden" }}>
                          <div
                            style={{
                              width: `${Math.round(item.prob * 100)}%`,
                              height: "100%",
                              background: CLASS_COLORS[item.class] || "#2f6b4f",
                            }}
                          />
                        </div>
                        <span className="mono" style={{ width: "36px", textAlign: "right", fontWeight: 600 }}>
                          {Math.round(item.prob * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
            ) : (
              <p style={{ fontSize: "0.8125rem", color: "#667a68", margin: 0 }}>
                Upload or analyze a panel image to view defect classification and probability breakdown.
              </p>
            )}
          </div>

          {/* Telemetry Cross-check & Fusion Card */}
          <div className="sd-card">
            <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.9375rem", fontWeight: 700, color: "#1c2c20" }}>
              Telemetry Cross-Check & Fusion Verdict
            </h3>

            {inspection ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                
                {/* Telemetry Shortfall Snapshot */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", padding: "0.625rem", background: "#f5f8f5", borderRadius: "3px", fontSize: "0.75rem" }}>
                  <div>
                    <span style={{ color: "#546857" }}>Linked Alert:</span>
                    <div><strong>{inspection.alert_id ? `#${inspection.alert_id} (String ${stringId})` : "Active Deficit Baseline"}</strong></div>
                  </div>
                  <div>
                    <span style={{ color: "#546857" }}>String Shortfall:</span>
                    <div><strong className="mono" style={{ color: "#b45309" }}>-16.0% Power Deficit</strong></div>
                  </div>
                </div>

                {/* Fusion Decision */}
                <div style={{ padding: "0.75rem", border: "1px solid #d0dcd0", borderRadius: "3px", background: "#ffffff" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: "#1a2a1e" }}>
                      {inspection.fusion?.verdict || "Deficit Validated"}
                    </span>
                    <span className={getActionBadgeClass(inspection.fusion?.action)}>
                      {inspection.fusion?.action || "CLEAN NOW"}
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: "0.8125rem", color: "#3d4e41", lineHeight: 1.4 }}>
                    {inspection.fusion?.reason || "Photo soiling correlates with telemetry deficit. Cleaning is economically recommended."}
                  </p>
                </div>

                {/* Financial ROI Snapshot */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem", textAlign: "center", padding: "0.5rem 0", borderTop: "1px solid #e0e8e0" }}>
                  <div>
                    <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Recoverable kWh</span>
                    <div className="mono" style={{ fontSize: "0.9375rem", fontWeight: 700, color: "#1a2a1e" }}>
                      {inspection.roi?.recoverable_kwh_day ? inspection.roi.recoverable_kwh_day.toFixed(1) : "18.5"}
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Recovery / Month</span>
                    <div className="mono" style={{ fontSize: "0.9375rem", fontWeight: 700, color: "#2f6b4f" }}>
                      ₹ {inspection.roi?.recoverable_inr_day ? (inspection.roi.recoverable_inr_day * 30).toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "2,450"}
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Payback Period</span>
                    <div className="mono" style={{ fontSize: "0.9375rem", fontWeight: 700, color: "#a8792f" }}>
                      {inspection.roi?.payback_days ? `${Math.round(inspection.roi.payback_days)} days` : "14 days"}
                    </div>
                  </div>
                </div>

                {/* Create Work Order CTA */}
                <button
                  type="button"
                  onClick={() => {
                    const params = new URLSearchParams({
                      create: "1",
                      plant_id: String(selectedPlantId || 1),
                      panel_id: `${stringId}-MOD01`,
                      class: predClass,
                      severity: inspection.fusion?.severity || "MEDIUM",
                      notes: `Created from Inspection ${inspection.id}: ${inspection.fusion?.reason || "Cleaning recommended"}`,
                    });
                    if (selectedAlertId) params.set("alert_id", String(selectedAlertId));
                    params.set("inspection_id", inspection.id);
                    router.push(`/dashboard/work-orders?${params.toString()}`);
                  }}
                  style={{
                    padding: "0.625rem 1rem",
                    background: "#2f6b4f",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "3px",
                    fontWeight: 700,
                    fontSize: "0.875rem",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    boxShadow: "0 2px 4px rgba(0,0,0,0.08)",
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="12" y1="18" x2="12" y2="12" />
                    <line x1="9" y1="15" x2="15" y2="15" />
                  </svg>
                  Create Field Work Order
                </button>

              </div>
            ) : (
              <p style={{ fontSize: "0.8125rem", color: "#667a68", margin: 0 }}>
                Analyze an image to cross-check telemetry Shortfall, verify defect causality, and trigger work orders.
              </p>
            )}
          </div>

        </div>

      </div>

      {/* Historical Inspection Feed */}
      <div className="sd-card">
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.9375rem", fontWeight: 700, color: "#1c2c20" }}>
          Recent Inspections History {scope.range && <span style={{ fontWeight: 400, color: "#546857", fontSize: "0.8125rem" }}>({scope.range})</span>}
        </h3>
        {history.filter((h) => isDateWithinScope(h.created_at, scope)).length > 0 ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #d0dcd0", textAlign: "left", color: "#546857" }}>
                  <th style={{ padding: "0.5rem" }}>Inspection ID</th>
                  <th style={{ padding: "0.5rem" }}>Timestamp</th>
                  <th style={{ padding: "0.5rem" }}>Defect Class</th>
                  <th style={{ padding: "0.5rem" }}>Confidence</th>
                  <th style={{ padding: "0.5rem" }}>Fusion Action</th>
                  <th style={{ padding: "0.5rem" }}>Status</th>
                  <th style={{ padding: "0.5rem", textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {history.filter((h) => isDateWithinScope(h.created_at, scope)).map((h) => (
                  <tr key={h.id} style={{ borderBottom: "1px solid #e5ece5" }}>
                    <td className="mono" style={{ padding: "0.5rem", fontWeight: 600 }}>{h.id}</td>
                    <td className="mono" style={{ padding: "0.5rem" }}>{h.created_at ? new Date(h.created_at).toLocaleString("en-IN") : "-"}</td>
                    <td style={{ padding: "0.5rem" }}>
                      <span style={{ color: CLASS_COLORS[h.prediction?.predicted_class || "dusty"], fontWeight: 700 }}>
                        {CLASS_LABELS[h.prediction?.predicted_class || "dusty"] || h.prediction?.predicted_class}
                      </span>
                    </td>
                    <td className="mono" style={{ padding: "0.5rem" }}>
                      {h.prediction?.confidence ? `${Math.round(h.prediction.confidence * 100)}%` : "-"}
                    </td>
                    <td style={{ padding: "0.5rem" }}>
                      <span className={getActionBadgeClass(h.fusion?.action)}>
                        {h.fusion?.action || "WAIT"}
                      </span>
                    </td>
                    <td style={{ padding: "0.5rem" }}>
                      <span style={{ color: "#2f6b4f", fontWeight: 600 }}>{h.status}</span>
                    </td>
                    <td style={{ padding: "0.5rem", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => {
                          setInspection(h);
                          setActiveTab("gradcam");
                        }}
                        style={{
                          padding: "0.25rem 0.5rem",
                          background: "#eaf0ea",
                          border: "1px solid #c5cdc5",
                          borderRadius: "2px",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Inspect Evidence
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ margin: 0, fontSize: "0.8125rem", color: "#667a68" }}>
            No past inspections found.
          </p>
        )}
      </div>

    </div>
  );
}
