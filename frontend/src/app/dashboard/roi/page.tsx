"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/states";
import { useScope } from "@/components/dashboard/scope";
import { plantsApi, roiApi } from "@/lib/api";
import type { Plant, RoiResponse } from "@/lib/api";

const TARIFF_PRESETS = [
  { id: "c_and_i", label: "Commercial & Industrial (C&I)", rate: 6.5 },
  { id: "utility", label: "Utility Scale", rate: 3.2 },
  { id: "residential", label: "Residential Rooftop", rate: 8.0 },
];

export default function RoiPage() {
  const scope = useScope();
  const [plants, setPlants] = useState<Plant[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(scope.plantId || 1);
  const [roiData, setRoiData] = useState<RoiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);

  // Editable settings
  const [tariff, setTariff] = useState<number>(6.5);
  const [preset, setPreset] = useState<string>("c_and_i");
  const [costPerModule, setCostPerModule] = useState<number>(50.0);
  const [waterLPerModule, setWaterLPerModule] = useState<number>(2.5);
  const [waterCost, setWaterCost] = useState<number>(0.05);
  const [labourCost, setLabourCost] = useState<number>(1500.0);

  // Sync with scope
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

  // Load ROI data
  const loadRoi = () => {
    if (!selectedPlantId) return;
    setLoading(true);
    roiApi
      .get(selectedPlantId)
      .then((res) => {
        setRoiData(res);
        if (res.settings) {
          setTariff(res.settings.tariff_inr_kwh);
          setPreset(res.settings.tariff_preset || "c_and_i");
          setCostPerModule(res.settings.cleaning_cost_per_module_inr);
          setWaterLPerModule(res.settings.water_l_per_module);
          setWaterCost(res.settings.water_cost_inr_per_l);
          setLabourCost(res.settings.labour_cost_inr);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadRoi();
  }, [selectedPlantId]);

  const handlePresetSelect = (presetId: string, rate: number) => {
    setPreset(presetId);
    setTariff(rate);
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPlantId) return;
    setSaving(true);
    setSaveSuccess(false);
    try {
      await roiApi.updateSettings(selectedPlantId, {
        tariff_inr_kwh: tariff,
        tariff_preset: preset,
        cleaning_cost_per_module_inr: costPerModule,
        water_l_per_module: waterLPerModule,
        water_cost_inr_per_l: waterCost,
        labour_cost_inr: labourCost,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      loadRoi();
    } catch {
      alert("Failed to save ROI settings");
    } finally {
      setSaving(false);
    }
  };

  const getDecisionBadge = (decision: string) => {
    switch (decision) {
      case "CLEAN NOW":
        return <span className="sd-action-badge sd-action-clean">CLEAN NOW</span>;
      case "WAIT":
        return <span className="sd-action-badge sd-action-wait">WAIT</span>;
      case "FIELD CHECK":
        return <span className="sd-action-badge sd-action-field">FIELD CHECK</span>;
      case "REPLACE":
        return <span className="sd-action-badge sd-action-replace">REPLACE</span>;
      default:
        return <span className="sd-action-badge">{decision}</span>;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <PageHeader
        eyebrow="Financial Recovery & Cleaning Decisions"
        title="Return on Investment (ROI)"
        sub="Calculate daily & monthly recoverable rupees, compare payback thresholds against rain outlooks, and determine string-level action recommendations."
      />

      {/* Plant selector */}
      <div className="sd-card" style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", marginBottom: "0.25rem" }}>
            Select Solar Plant:
          </label>
          <select
            value={selectedPlantId || ""}
            onChange={(e) => setSelectedPlantId(Number(e.target.value))}
            style={{ padding: "0.375rem 0.75rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.875rem", background: "#fff" }}
          >
            {plants.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.capacity_kw} kW)</option>
            ))}
          </select>
        </div>
      </div>

      {/* Rain-Aware Alert Banner */}
      {roiData?.rain_wait && (
        <div style={{ padding: "0.875rem 1.25rem", background: "rgba(201, 133, 42, 0.12)", border: "2px solid #c9852a", borderRadius: "4px", color: "#8a5a14", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 16.58A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25" />
            <path d="M8 19v2M8 13v2M16 19v2M16 13v2M12 21v2M12 15v2" />
          </svg>
          <div>
            <strong>Rain Forecast Detected (Next 72 Hours):</strong>
            <p style={{ margin: "0.125rem 0 0", fontSize: "0.8125rem" }}>
              Natural precipitation will clean the panel surface at zero cost. Manual washing dispatch is deferred to save water and labour expenses.
            </p>
          </div>
        </div>
      )}

      {/* KPI Cards Strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
        <div className="sd-card">
          <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>MONTHLY RECOVERY</span>
          <div className="mono" style={{ fontSize: "1.75rem", fontWeight: 800, color: "#2f6b4f", margin: "0.25rem 0" }}>
            ₹ {roiData ? roiData.inr_per_month.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "0"}
          </div>
          <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>
            ₹ {roiData ? roiData.inr_per_day.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "0"} / day recoverable
          </span>
        </div>

        <div className="sd-card">
          <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>ENERGY AT RISK</span>
          <div className="mono" style={{ fontSize: "1.75rem", fontWeight: 800, color: "#1c2c20", margin: "0.25rem 0" }}>
            {roiData ? roiData.recoverable_kwh_day.toFixed(1) : "0"} <span style={{ fontSize: "1rem", fontWeight: 500 }}>kWh/day</span>
          </div>
          <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Shortfall from soiled surface</span>
        </div>

        <div className="sd-card">
          <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>CLEANING PAYBACK</span>
          <div className="mono" style={{ fontSize: "1.75rem", fontWeight: 800, color: "#a8792f", margin: "0.25rem 0" }}>
            {roiData?.payback_days ? `${Math.round(roiData.payback_days)} days` : "N/A"}
          </div>
          <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>
            Clean cost: ₹ {roiData?.cleaning_cost_inr ? roiData.cleaning_cost_inr.toLocaleString("en-IN") : "0"}
          </span>
        </div>

        <div className="sd-card">
          <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>OPTIMAL INTERVAL</span>
          <div className="mono" style={{ fontSize: "1.75rem", fontWeight: 800, color: "#3b82f6", margin: "0.25rem 0" }}>
            {roiData ? `${Math.round(roiData.optimal_interval_days)} days` : "15 days"}
          </div>
          <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Economically calibrated cycle</span>
        </div>

        <div className="sd-card">
          <span style={{ fontSize: "0.75rem", color: "#546857", fontWeight: 600 }}>ANNUAL WATER SAVED</span>
          <div className="mono" style={{ fontSize: "1.75rem", fontWeight: 800, color: "#0891b2", margin: "0.25rem 0" }}>
            {roiData ? roiData.water_saved_l_per_year.toLocaleString("en-IN") : "4,500"} <span style={{ fontSize: "1rem", fontWeight: 500 }}>L</span>
          </div>
          <span style={{ fontSize: "0.6875rem", color: "#667a68" }}>Saved via condition-based cleaning</span>
        </div>
      </div>

      {/* Plant Decision & Strategy Callout */}
      {roiData && (
        <div className="sd-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f5f8f5" }}>
          <div>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#546857", textTransform: "uppercase" }}>Plant Strategy Recommendation:</span>
            <div style={{ marginTop: "0.25rem", fontSize: "0.9375rem", color: "#243528" }}>
              {roiData.reason}
            </div>
          </div>
          <div>
            {getDecisionBadge(roiData.decision)}
          </div>
        </div>
      )}

      {/* String-Level Decisions Breakdown Table */}
      <div className="sd-card">
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.9375rem", fontWeight: 700, color: "#1c2c20" }}>
          String-Level Decisions & Energy Breakdown
        </h3>
        {roiData && roiData.strings && roiData.strings.length > 0 ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #c5cdc5", textAlign: "left", color: "#4f6354" }}>
                <th style={{ padding: "0.5rem" }}>String</th>
                <th style={{ padding: "0.5rem" }}>Modules</th>
                <th style={{ padding: "0.5rem" }}>Action Decision</th>
                <th style={{ padding: "0.5rem" }}>Recoverable kWh/day</th>
                <th style={{ padding: "0.5rem" }}>Revenue / Day</th>
                <th style={{ padding: "0.5rem" }}>Payback (Days)</th>
                <th style={{ padding: "0.5rem" }}>Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {roiData.strings.map((str) => (
                <tr key={str.string_id} style={{ borderBottom: "1px solid #e5ece5" }}>
                  <td className="mono" style={{ padding: "0.5rem", fontWeight: 700 }}>{str.string_name}</td>
                  <td className="mono" style={{ padding: "0.5rem" }}>{str.module_count}</td>
                  <td style={{ padding: "0.5rem" }}>{getDecisionBadge(str.decision)}</td>
                  <td className="mono" style={{ padding: "0.5rem" }}>{str.recoverable_kwh_day.toFixed(1)} kWh</td>
                  <td className="mono" style={{ padding: "0.5rem", color: "#2f6b4f", fontWeight: 600 }}>₹ {str.inr_per_day.toFixed(0)}</td>
                  <td className="mono" style={{ padding: "0.5rem" }}>{Math.round(str.payback_days)} days</td>
                  <td style={{ padding: "0.5rem", color: "#546857" }}>{str.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ margin: 0, fontSize: "0.8125rem", color: "#667a68" }}>
            Plant overall decision: <strong>{roiData?.decision || "ANALYZING"}</strong>. String-level sub-meters are aggregated into the plant baseline.
          </p>
        )}
      </div>

      {/* Editable Cost Assumptions & Tariff Configuration */}
      <div className="sd-card">
        <h3 style={{ margin: "0 0 1rem", fontSize: "0.9375rem", fontWeight: 700, color: "#1c2c20" }}>
          ROI Parameters & Cost Assumptions Configuration
        </h3>

        {/* Tariff Presets Strip */}
        <div style={{ marginBottom: "1.25rem" }}>
          <span style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", marginBottom: "0.5rem" }}>
            Electricity Tariff Preset:
          </span>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {TARIFF_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePresetSelect(p.id, p.rate)}
                style={{
                  padding: "0.5rem 0.875rem",
                  border: preset === p.id ? "2px solid #2f6b4f" : "1px solid #c5cdc5",
                  background: preset === p.id ? "rgba(47,107,79,0.08)" : "#fff",
                  borderRadius: "3px",
                  fontSize: "0.8125rem",
                  fontWeight: preset === p.id ? 700 : 500,
                  cursor: "pointer",
                }}
              >
                {p.label} (₹ {p.rate.toFixed(2)}/kWh)
              </button>
            ))}
          </div>
        </div>

        {/* Form Inputs */}
        <form onSubmit={handleSaveSettings}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                Active Tariff (₹ / kWh)
              </label>
              <input
                type="number"
                step="0.05"
                value={tariff}
                onChange={(e) => {
                  setTariff(Number(e.target.value));
                  setPreset("custom");
                }}
                style={{ width: "100%", padding: "0.45rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                Cleaning Cost per Module (₹)
              </label>
              <input
                type="number"
                step="1"
                value={costPerModule}
                onChange={(e) => setCostPerModule(Number(e.target.value))}
                style={{ width: "100%", padding: "0.45rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                Water Volume per Module (Litres)
              </label>
              <input
                type="number"
                step="0.1"
                value={waterLPerModule}
                onChange={(e) => setWaterLPerModule(Number(e.target.value))}
                style={{ width: "100%", padding: "0.45rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                Water Cost (₹ / Litre)
              </label>
              <input
                type="number"
                step="0.01"
                value={waterCost}
                onChange={(e) => setWaterCost(Number(e.target.value))}
                style={{ width: "100%", padding: "0.45rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                Mobilisation / Labour Fixed Cost (₹)
              </label>
              <input
                type="number"
                step="100"
                value={labourCost}
                onChange={(e) => setLabourCost(Number(e.target.value))}
                style={{ width: "100%", padding: "0.45rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: "0.55rem 1.25rem",
                background: "#2f6b4f",
                color: "#fff",
                border: "none",
                borderRadius: "3px",
                fontWeight: 700,
                fontSize: "0.875rem",
                cursor: saving ? "wait" : "pointer",
              }}
            >
              {saving ? "Saving Assumptions..." : "Save & Recalculate ROI"}
            </button>
            {saveSuccess && (
              <span style={{ fontSize: "0.8125rem", color: "#2f6b4f", fontWeight: 600 }}>
                ✓ ROI settings saved successfully!
              </span>
            )}
          </div>
        </form>
      </div>

    </div>
  );
}
