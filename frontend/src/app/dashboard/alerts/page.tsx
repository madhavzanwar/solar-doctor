"use client";

import { useCallback, useEffect, useState } from "react";
import {
  alertsApi,
  diagnosisApi,
  plantsApi,
  type Alert,
  type Plant,
  type DiagnosisResponse,
  type RootCauseTaxonomyItem,
} from "@/lib/api";
import DiagnosisModal from "@/components/diagnosis/DiagnosisModal";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [plants, setPlants] = useState<Plant[]>([]);
  const [taxonomy, setTaxonomy] = useState<RootCauseTaxonomyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("open");
  const [viewTab, setViewTab] = useState<"alerts" | "sandbox">("alerts");

  const [activeDiagnosis, setActiveDiagnosis] = useState<DiagnosisResponse | null>(null);
  const [diagnosingId, setDiagnosingId] = useState<number | null>(null);

  const [customPlantId, setCustomPlantId] = useState<number | null>(null);
  const [selectedErrorCode, setSelectedErrorCode] = useState<string>("F056");
  const [customExpectedKw, setCustomExpectedKw] = useState<string>("42000");
  const [customActualKw, setCustomActualKw] = useState<string>("28000");
  const [customIrradiance, setCustomIrradiance] = useState<string>("850");
  const [customTemp, setCustomTemp] = useState<string>("38");
  const [runningSandbox, setRunningSandbox] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [alertData, plantData, taxData] = await Promise.all([
        alertsApi.list(undefined, 200),
        plantsApi.list(),
        diagnosisApi.getTaxonomy().catch(() => []),
      ]);
      setAlerts(alertData);
      setPlants(plantData);
      setTaxonomy(taxData);
      if (plantData.length > 0) setCustomPlantId(plantData[0].id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load alerts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleResolve = async (id: number) => {
    try {
      await alertsApi.resolve(id);
      setAlerts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, is_resolved: true } : a))
      );
    } catch {
      // ignore
    }
  };

  const handleDiagnoseAlert = async (alertId: number) => {
    setDiagnosingId(alertId);
    setError(null);
    try {
      const diag = await diagnosisApi.diagnoseAlert(alertId);
      setActiveDiagnosis(diag);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Diagnosis failed.");
    } finally {
      setDiagnosingId(null);
    }
  };

  const handleRunSandbox = async () => {
    if (!customPlantId) return;
    setRunningSandbox(true);
    setError(null);
    try {
      const diag = await diagnosisApi.diagnose({
        plant_id: customPlantId,
        inverter_error_code: selectedErrorCode,
        expected_power_kw: parseFloat(customExpectedKw) || 1000,
        actual_power_kw: parseFloat(customActualKw) || 600,
        irradiance_w_m2: parseFloat(customIrradiance) || 800,
        temperature_c: parseFloat(customTemp) || 30,
      });
      setActiveDiagnosis(diag);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Diagnostic run failed.");
    } finally {
      setRunningSandbox(false);
    }
  };

  const filtered = alerts.filter((a) => {
    if (filter === "open") return !a.is_resolved;
    if (filter === "resolved") return a.is_resolved;
    return true;
  });

  const counts = {
    all: alerts.length,
    open: alerts.filter((a) => !a.is_resolved).length,
    resolved: alerts.filter((a) => a.is_resolved).length,
  };

  return (
    <>
      <div className="dash-page-header">
        <p className="dash-eyebrow">Operations</p>
        <h1 className="dash-section-title">Alerts</h1>
        <p className="dash-page-sub">
          Anomaly log and inverter fault diagnosis for field dispatch.
        </p>
      </div>

      {error && <div className="dash-error">{error}</div>}

      <div className="dash-tabs">
        <button
          type="button"
          className={`dash-tab${viewTab === "alerts" ? " active" : ""}`}
          onClick={() => setViewTab("alerts")}
        >
          Alert log ({counts.open} open)
        </button>
        <button
          type="button"
          className={`dash-tab${viewTab === "sandbox" ? " active" : ""}`}
          onClick={() => setViewTab("sandbox")}
        >
          Fault sandbox
        </button>
      </div>

      {viewTab === "alerts" && (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "1.25rem",
              flexWrap: "wrap",
              gap: "0.75rem",
            }}
          >
            <div className="dash-filters">
              {(["open", "all", "resolved"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`dash-btn dash-btn-sm ${filter === f ? "dash-btn-primary" : "dash-btn-ghost"}`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                  <span style={{ opacity: 0.75 }}>{counts[f]}</span>
                </button>
              ))}
            </div>
            <p className="dash-page-sub" style={{ margin: 0, fontSize: "0.82rem" }}>
              Use Diagnose to inspect root cause and technician steps.
            </p>
          </div>

          {loading ? (
            <div className="dash-loading">
              <div className="dash-spinner" />
              <div>Loading alerts…</div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="dash-card dash-empty">
              {filter === "open" ? "No open alerts." : "No alerts in this category."}
            </div>
          ) : (
            <div className="dash-card">
              <div className="dash-alert-list">
                {filtered.map((a) => {
                  const severity = a.severity as "CRITICAL" | "WARNING" | "INFO";
                  const isDiagnosing = diagnosingId === a.id;

                  return (
                    <div key={a.id} className={`dash-alert-row ${severity}`}>
                      <span className={`dash-alert-badge ${severity}`}>{severity}</span>
                      <div style={{ minWidth: 0 }}>
                        <div className="dash-alert-msg" style={{ fontWeight: 600 }}>
                          {a.message}
                        </div>
                        <div
                          style={{
                            fontSize: "0.74rem",
                            color: "var(--dash-muted)",
                            marginTop: "0.3rem",
                            lineHeight: 1.4,
                            overflowWrap: "anywhere",
                          }}
                        >
                          Plant #{a.plant_id}
                          {" · "}
                          {a.alert_type}
                          {a.deviation_percent != null &&
                            ` · ${a.deviation_percent.toFixed(1)}% shortfall`}
                          {a.expected_power_kw != null &&
                            a.actual_power_kw != null &&
                            ` · ${a.actual_power_kw.toFixed(0)} / ${a.expected_power_kw.toFixed(0)} kW`}
                        </div>
                      </div>
                      <span className="dash-alert-time">
                        {new Date(a.timestamp).toLocaleString()}
                      </span>
                      <div className="dash-alert-actions">
                        <button
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                          onClick={() => handleDiagnoseAlert(a.id)}
                          disabled={isDiagnosing}
                        >
                          {isDiagnosing ? "Diagnosing…" : "Diagnose"}
                        </button>
                        {!a.is_resolved ? (
                          <button
                            className="dash-alert-resolve-btn"
                            onClick={() => handleResolve(a.id)}
                          >
                            Resolve
                          </button>
                        ) : (
                          <span
                            style={{
                              fontSize: "0.72rem",
                              color: "var(--field)",
                              fontWeight: 600,
                            }}
                          >
                            Resolved
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {viewTab === "sandbox" && (
        <div className="dash-card">
          <div style={{ marginBottom: "1.25rem", maxWidth: "36rem" }}>
            <h2
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontSize: "1.1rem",
                fontWeight: 700,
                margin: 0,
                letterSpacing: "-0.02em",
              }}
            >
              Inverter fault sandbox
            </h2>
            <p className="dash-page-sub" style={{ marginTop: "0.35rem" }}>
              Enter a fault code and telemetry shortfall to run root-cause analysis.
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))",
              gap: "1rem",
              marginBottom: "1.25rem",
            }}
          >
            <div className="dash-field">
              <label htmlFor="sandbox-plant">Plant</label>
              <select
                id="sandbox-plant"
                className="dash-input"
                value={customPlantId ?? ""}
                onChange={(e) => setCustomPlantId(parseInt(e.target.value, 10))}
              >
                {plants.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.capacity_kw} kW)
                  </option>
                ))}
              </select>
            </div>

            <div className="dash-field">
              <label htmlFor="sandbox-code">Error code</label>
              <input
                id="sandbox-code"
                type="text"
                className="dash-input"
                value={selectedErrorCode}
                onChange={(e) => setSelectedErrorCode(e.target.value)}
                placeholder="e.g. F056"
              />
            </div>

            <div className="dash-field">
              <label htmlFor="sandbox-expected">Expected power (kW)</label>
              <input
                id="sandbox-expected"
                type="number"
                className="dash-input"
                value={customExpectedKw}
                onChange={(e) => setCustomExpectedKw(e.target.value)}
              />
            </div>

            <div className="dash-field">
              <label htmlFor="sandbox-actual">Actual power (kW)</label>
              <input
                id="sandbox-actual"
                type="number"
                className="dash-input"
                value={customActualKw}
                onChange={(e) => setCustomActualKw(e.target.value)}
              />
            </div>

            <div className="dash-field">
              <label htmlFor="sandbox-irr">Irradiance (W/m²)</label>
              <input
                id="sandbox-irr"
                type="number"
                className="dash-input"
                value={customIrradiance}
                onChange={(e) => setCustomIrradiance(e.target.value)}
              />
            </div>

            <div className="dash-field">
              <label htmlFor="sandbox-temp">Temperature (°C)</label>
              <input
                id="sandbox-temp"
                type="number"
                className="dash-input"
                value={customTemp}
                onChange={(e) => setCustomTemp(e.target.value)}
              />
            </div>
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <div className="dash-config-label" style={{ marginBottom: "0.45rem" }}>
              Presets
            </div>
            <div className="dash-chip-row">
              {[
                { code: "F056", label: "F056 Overtemp" },
                { code: "F034", label: "F034 Ground fault" },
                { code: "F012", label: "F012 Open circuit" },
                { code: "F063", label: "F063 Arc fault" },
                { code: "F021", label: "F021 Grid OV" },
                { code: "F077", label: "F077 MPPT stall" },
                { code: "SOILING", label: "Soiling" },
                { code: "CLIPPING", label: "Clipping" },
              ].map((preset) => (
                <button
                  key={preset.code}
                  type="button"
                  className={`dash-chip${selectedErrorCode === preset.code ? " active" : ""}`}
                  onClick={() => setSelectedErrorCode(preset.code)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <button
            className="dash-btn dash-btn-primary"
            onClick={handleRunSandbox}
            disabled={runningSandbox || !customPlantId}
          >
            {runningSandbox ? "Running…" : "Run diagnosis"}
          </button>

          {taxonomy.length > 0 && (
            <div
              style={{
                marginTop: "2rem",
                borderTop: "1px solid var(--dash-border)",
                paddingTop: "1.25rem",
              }}
            >
              <h3
                style={{
                  fontFamily: "var(--font-display), sans-serif",
                  fontSize: "1rem",
                  fontWeight: 700,
                  marginBottom: "0.85rem",
                  letterSpacing: "-0.02em",
                }}
              >
                Fault taxonomy ({taxonomy.length})
              </h3>
              <div className="dash-preset-grid">
                {taxonomy.map((t) => (
                  <div key={t.category} className="dash-preset-card">
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "0.5rem",
                      }}
                    >
                      <strong style={{ fontSize: "0.88rem", overflowWrap: "anywhere" }}>
                        {t.title}
                      </strong>
                      <span className="dash-badge dash-badge-muted">{t.typical_urgency}</span>
                    </div>
                    <p>{t.description}</p>
                    <div className="dash-chip-row">
                      {t.common_error_codes.map((c) => (
                        <button
                          key={c}
                          type="button"
                          className="dash-chip"
                          onClick={() => setSelectedErrorCode(c)}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeDiagnosis && (
        <DiagnosisModal
          diagnosis={activeDiagnosis}
          onClose={() => setActiveDiagnosis(null)}
          onResolveAlert={handleResolve}
        />
      )}
    </>
  );
}
