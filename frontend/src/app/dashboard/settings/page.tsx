"use client";

import { useCallback, useEffect, useState } from "react";
import {
  plantsApi,
  roiApi,
  usersApi,
  type Plant,
  type PlantConfig,
  type UserRecord,
  type PlantRoiSettings,
} from "@/lib/api";
import { PageHeader } from "@/components/ui/states";

export default function SettingsPage() {
  const [tab, setTab] = useState<"plant" | "users">("plant");

  // Plant configuration state
  const [plants, setPlants] = useState<Plant[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(null);
  const [loadingPlant, setLoadingPlant] = useState(false);
  const [savingPlant, setSavingPlant] = useState(false);
  const [plantSaveSuccess, setPlantSaveSuccess] = useState<string | null>(null);
  const [plantSaveError, setPlantSaveError] = useState<string | null>(null);

  // Form fields for plant
  const [capacityKw, setCapacityKw] = useState<string>("100");
  const [inverterCapacityKw, setInverterCapacityKw] = useState<string>("90");
  const [tilt, setTilt] = useState<string>("20.0");
  const [azimuth, setAzimuth] = useState<string>("180.0");
  const [efficiency, setEfficiency] = useState<string>("0.18");
  const [tariffInr, setTariffInr] = useState<string>("4.50");
  const [cleaningCost, setCleaningCost] = useState<string>("25");
  const [waterPerModule, setWaterPerModule] = useState<string>("2.5");
  const [labourHours, setLabourHours] = useState<string>("1.5");
  const [piWarning, setPiWarning] = useState<string>("10.0");
  const [piCritical, setPiCritical] = useState<string>("20.0");
  const [soilingThreshold, setSoilingThreshold] = useState<string>("5.0");
  const [clippingThreshold, setClippingThreshold] = useState<string>("95.0");
  const [forecastHorizon, setForecastHorizon] = useState<string>("60");

  // User management state
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [userError, setUserError] = useState<string | null>(null);
  const [userSuccess, setUserSuccess] = useState<string | null>(null);
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("operator");
  const [creatingUser, setCreatingUser] = useState(false);

  // Load plants on mount
  useEffect(() => {
    plantsApi.list()
      .then((data) => {
        setPlants(data);
        if (data.length > 0 && selectedPlantId === null) {
          setSelectedPlantId(data[0].id);
        }
      })
      .catch((err: unknown) => {
        setPlantSaveError(err instanceof Error ? err.message : "Failed to load plants");
      });
  }, [selectedPlantId]);

  // Load configuration whenever selectedPlantId changes
  useEffect(() => {
    if (!selectedPlantId) return;
    setLoadingPlant(true);
    setPlantSaveSuccess(null);
    setPlantSaveError(null);

    Promise.all([
      plantsApi.get(selectedPlantId).catch(() => null),
      plantsApi.getConfig(selectedPlantId).catch(() => null),
      roiApi.get(selectedPlantId).catch(() => null),
    ])
      .then(([plant, config, roi]) => {
        if (plant) {
          setCapacityKw(String(plant.capacity_kw || 100));
          setInverterCapacityKw(String(plant.inverter_capacity_kw || 90));
          if (plant.tariff_inr_kwh != null) {
            setTariffInr(String(plant.tariff_inr_kwh));
          }
        }
        if (config) {
          setTilt(String(config.tilt ?? 20.0));
          setAzimuth(String(config.azimuth ?? 180.0));
          setEfficiency(String(config.efficiency ?? 0.18));
          setSoilingThreshold(String(config.soiling_threshold ?? 5.0));
          setClippingThreshold(String(config.clipping_threshold ?? 95.0));
          setForecastHorizon(String(config.forecast_horizon_minutes ?? 60));
        }
        if (roi && roi.settings) {
          const s = roi.settings;
          if (s.tariff_inr_kwh != null) setTariffInr(String(s.tariff_inr_kwh));
          if (s.cleaning_cost_per_module_inr != null) setCleaningCost(String(s.cleaning_cost_per_module_inr));
          if (s.water_l_per_module != null) setWaterPerModule(String(s.water_l_per_module));
          if (s.labour_cost_inr != null) setLabourHours(String(s.labour_cost_inr));
        }
      })
      .finally(() => setLoadingPlant(false));
  }, [selectedPlantId]);

  // Load users when tab is switched to users
  const loadUsers = useCallback(() => {
    setLoadingUsers(true);
    setUserError(null);
    usersApi.list()
      .then((data) => setUsers(data))
      .catch((err: unknown) => {
        setUserError(err instanceof Error ? err.message : "Failed to load users (requires Admin role)");
      })
      .finally(() => setLoadingUsers(false));
  }, []);

  useEffect(() => {
    if (tab === "users") {
      loadUsers();
    }
  }, [tab, loadUsers]);

  // Save Plant Configuration
  const handleSavePlant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPlantId) return;

    setSavingPlant(true);
    setPlantSaveSuccess(null);
    setPlantSaveError(null);

    try {
      // 1. Update core plant
      await plantsApi.update(selectedPlantId, {
        capacity_kw: parseFloat(capacityKw) || 100,
        inverter_capacity_kw: parseFloat(inverterCapacityKw) || 90,
        tariff_inr_kwh: parseFloat(tariffInr) || 4.5,
      });

      // 2. Update plant physics config
      await plantsApi.updateConfig(selectedPlantId, {
        tilt: parseFloat(tilt) || 20.0,
        azimuth: parseFloat(azimuth) || 180.0,
        efficiency: parseFloat(efficiency) || 0.18,
        soiling_threshold: parseFloat(soilingThreshold) || 5.0,
        clipping_threshold: parseFloat(clippingThreshold) || 95.0,
        forecast_horizon_minutes: parseInt(forecastHorizon, 10) || 60,
      });

      // 3. Update anomaly thresholds
      await plantsApi.setAnomalyThreshold({
        plant_id: selectedPlantId,
        warning_threshold_percent: parseFloat(piWarning) || 10.0,
        critical_threshold_percent: parseFloat(piCritical) || 20.0,
      });

      // 4. Update ROI parameters
      await roiApi.updateSettings(selectedPlantId, {
        tariff_inr_kwh: parseFloat(tariffInr) || 4.5,
        cleaning_cost_per_module_inr: parseFloat(cleaningCost) || 25,
        water_l_per_module: parseFloat(waterPerModule) || 2.5,
        labour_cost_inr: parseFloat(labourHours) || 500,
      });

      setPlantSaveSuccess("Plant settings and thresholds successfully saved and persisted!");
    } catch (err: unknown) {
      setPlantSaveError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSavingPlant(false);
    }
  };

  // User Actions
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail || !newPassword) return;
    setCreatingUser(true);
    setUserError(null);
    setUserSuccess(null);

    try {
      await usersApi.create({
        email: newEmail.trim().toLowerCase(),
        password: newPassword,
        role: newRole,
      });
      setUserSuccess(`User ${newEmail} created successfully.`);
      setShowAddUserModal(false);
      setNewEmail("");
      setNewPassword("");
      setNewRole("operator");
      loadUsers();
    } catch (err: unknown) {
      setUserError(err instanceof Error ? err.message : "Failed to create user.");
    } finally {
      setCreatingUser(false);
    }
  };

  const handleRoleChange = async (userId: number, role: string) => {
    setUserError(null);
    setUserSuccess(null);
    try {
      await usersApi.update(userId, { role });
      setUserSuccess(`Updated user role to ${role}.`);
      loadUsers();
    } catch (err: unknown) {
      setUserError(err instanceof Error ? err.message : "Failed to update role.");
    }
  };

  const handleToggleDisabled = async (userId: number, currentDisabled: boolean) => {
    setUserError(null);
    setUserSuccess(null);
    try {
      await usersApi.update(userId, { disabled: !currentDisabled });
      setUserSuccess(`User ${!currentDisabled ? "disabled" : "activated"}.`);
      loadUsers();
    } catch (err: unknown) {
      setUserError(err instanceof Error ? err.message : "Failed to update user status.");
    }
  };

  const handleDeleteUser = async (userId: number) => {
    if (!window.confirm("Are you sure you want to delete this user account?")) return;
    setUserError(null);
    setUserSuccess(null);
    try {
      await usersApi.delete(userId);
      setUserSuccess("User deleted successfully.");
      loadUsers();
    } catch (err: unknown) {
      setUserError(err instanceof Error ? err.message : "Failed to delete user.");
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Configuration & Access"
        title="Settings & Administration"
        sub="Plant physical parameters, economic tariff presets, alert thresholds, and Role-Based Access Control."
      />

      <div className="dash-tabs" style={{ marginBottom: "1.25rem" }}>
        <button
          type="button"
          className={`dash-tab${tab === "plant" ? " active" : ""}`}
          onClick={() => setTab("plant")}
        >
          Plant Configuration & Thresholds
        </button>
        <button
          type="button"
          className={`dash-tab${tab === "users" ? " active" : ""}`}
          onClick={() => setTab("users")}
        >
          User Management & RBAC
        </button>
      </div>

      {tab === "plant" && (
        <>
          <div className="dash-card" style={{ marginBottom: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <label htmlFor="settings-plant-select" style={{ fontSize: "0.85rem", fontWeight: 700, display: "block", marginBottom: "0.3rem" }}>
                  Active Plant
                </label>
                <select
                  id="settings-plant-select"
                  className="dash-input"
                  style={{ minWidth: "280px" }}
                  value={selectedPlantId ?? ""}
                  onChange={(e) => setSelectedPlantId(Number(e.target.value))}
                >
                  {plants.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} (#{p.id}) {p.location ? `— ${p.location}` : ""}
                    </option>
                  ))}
                </select>
              </div>

              {loadingPlant && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--dash-muted)", fontSize: "0.85rem" }}>
                  <div className="dash-spinner" style={{ width: "16px", height: "16px" }} />
                  Loading plant config…
                </div>
              )}
            </div>
          </div>

          {plantSaveSuccess && (
            <div className="dash-card" style={{ background: "#ecfdf5", border: "2px solid #a7f3d0", color: "#065f46", marginBottom: "1.25rem", padding: "0.75rem 1rem", fontSize: "0.85rem" }}>
              ✓ {plantSaveSuccess}
            </div>
          )}

          {plantSaveError && (
            <div className="dash-error" style={{ marginBottom: "1.25rem" }}>
              ⚠ {plantSaveError}
            </div>
          )}

          <form onSubmit={handleSavePlant}>
            {/* Physical Parameters */}
            <div className="dash-card" style={{ marginBottom: "1.15rem" }}>
              <div className="dash-card-title">Physical & Solar Array Geometry</div>
              <p style={{ margin: "0 0 1rem 0", fontSize: "0.82rem", color: "var(--dash-muted)" }}>
                Inverter and PV array specifications used for clear-sky physics models and irradiance calculations.
              </p>
              <div className="dash-form-grid">
                <div className="dash-field">
                  <label htmlFor="set-cap">DC Capacity (kWp)</label>
                  <input
                    id="set-cap"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="1"
                    value={capacityKw}
                    onChange={(e) => setCapacityKw(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-inv-cap">Inverter AC Capacity (kW)</label>
                  <input
                    id="set-inv-cap"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="1"
                    value={inverterCapacityKw}
                    onChange={(e) => setInverterCapacityKw(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-tilt">Tilt Angle (°)</label>
                  <input
                    id="set-tilt"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="0"
                    max="90"
                    value={tilt}
                    onChange={(e) => setTilt(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-azimuth">Azimuth (° from North)</label>
                  <input
                    id="set-azimuth"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="0"
                    max="360"
                    value={azimuth}
                    onChange={(e) => setAzimuth(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-eff">Module Nominal Efficiency (0–1)</label>
                  <input
                    id="set-eff"
                    className="dash-input"
                    type="number"
                    step="0.01"
                    min="0.01"
                    max="1"
                    value={efficiency}
                    onChange={(e) => setEfficiency(e.target.value)}
                    required
                  />
                </div>
              </div>
            </div>

            {/* Economics & Tariffs */}
            <div className="dash-card" style={{ marginBottom: "1.15rem" }}>
              <div className="dash-card-title">Economics, Tariffs & Maintenance Costs</div>
              <p style={{ margin: "0 0 1rem 0", fontSize: "0.82rem", color: "var(--dash-muted)" }}>
                PPA tariff and dispatch parameters driving ROI engine calculations and cleaning dispatch payback.
              </p>
              <div className="dash-form-grid">
                <div className="dash-field">
                  <label htmlFor="set-tariff">Electricity Tariff (₹/kWh)</label>
                  <input
                    id="set-tariff"
                    className="dash-input"
                    type="number"
                    step="0.05"
                    min="0"
                    value={tariffInr}
                    onChange={(e) => setTariffInr(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-cleaning-cost">Cleaning Cost (₹ / module)</label>
                  <input
                    id="set-cleaning-cost"
                    className="dash-input"
                    type="number"
                    step="0.5"
                    min="0"
                    value={cleaningCost}
                    onChange={(e) => setCleaningCost(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-water">Water Consumption (L / module)</label>
                  <input
                    id="set-water"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="0"
                    value={waterPerModule}
                    onChange={(e) => setWaterPerModule(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-labour">Labour Time (hrs / MW)</label>
                  <input
                    id="set-labour"
                    className="dash-input"
                    type="number"
                    step="0.1"
                    min="0"
                    value={labourHours}
                    onChange={(e) => setLabourHours(e.target.value)}
                    required
                  />
                </div>
              </div>
            </div>

            {/* Thresholds & Alerting */}
            <div className="dash-card" style={{ marginBottom: "1.25rem" }}>
              <div className="dash-card-title">Performance Index (PI) & Deficit Thresholds</div>
              <p style={{ margin: "0 0 1rem 0", fontSize: "0.82rem", color: "var(--dash-muted)" }}>
                Shortfall boundaries triggering WARNING and CRITICAL telemetry anomalies.
              </p>
              <div className="dash-form-grid">
                <div className="dash-field">
                  <label htmlFor="set-pi-warn">PI Warning Threshold (% shortfall)</label>
                  <input
                    id="set-pi-warn"
                    className="dash-input"
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={piWarning}
                    onChange={(e) => setPiWarning(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-pi-crit">PI Critical Threshold (% shortfall)</label>
                  <input
                    id="set-pi-crit"
                    className="dash-input"
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={piCritical}
                    onChange={(e) => setPiCritical(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-soiling">Soiling Trigger Threshold (%)</label>
                  <input
                    id="set-soiling"
                    className="dash-input"
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={soilingThreshold}
                    onChange={(e) => setSoilingThreshold(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-clipping">Inverter Clipping Threshold (%)</label>
                  <input
                    id="set-clipping"
                    className="dash-input"
                    type="number"
                    step="0.5"
                    min="0"
                    max="100"
                    value={clippingThreshold}
                    onChange={(e) => setClippingThreshold(e.target.value)}
                    required
                  />
                </div>
                <div className="dash-field">
                  <label htmlFor="set-horizon">Forecast Horizon (minutes)</label>
                  <input
                    id="set-horizon"
                    className="dash-input"
                    type="number"
                    step="5"
                    min="5"
                    max="1440"
                    value={forecastHorizon}
                    onChange={(e) => setForecastHorizon(e.target.value)}
                    required
                  />
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button
                type="submit"
                className="dash-btn dash-btn-primary"
                disabled={savingPlant || !selectedPlantId}
                style={{ padding: "0.6rem 1.4rem", fontSize: "0.9rem" }}
              >
                {savingPlant ? "Saving Changes…" : "Save Plant Configuration"}
              </button>
            </div>
          </form>
        </>
      )}

      {tab === "users" && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
            <div>
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>Active User Accounts</h2>
              <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.82rem", color: "var(--dash-muted)" }}>
                Manage team accounts and Role-Based Access Control (RBAC).
              </p>
            </div>
            <button
              type="button"
              className="dash-btn dash-btn-primary dash-btn-sm"
              onClick={() => setShowAddUserModal(true)}
            >
              + Add User Account
            </button>
          </div>

          {userSuccess && (
            <div className="dash-card" style={{ background: "#ecfdf5", border: "2px solid #a7f3d0", color: "#065f46", marginBottom: "1.25rem", padding: "0.75rem 1rem", fontSize: "0.85rem" }}>
              ✓ {userSuccess}
            </div>
          )}

          {userError && (
            <div className="dash-error" style={{ marginBottom: "1.25rem" }}>
              ⚠ {userError}
            </div>
          )}

          {loadingUsers ? (
            <div className="dash-loading">
              <div className="dash-spinner" />
              <div>Loading user accounts…</div>
            </div>
          ) : users.length === 0 ? (
            <div className="dash-card dash-empty">
              No users returned. Verify that you are signed in with an administrative account.
            </div>
          ) : (
            <div className="dash-card" style={{ overflowX: "auto", marginBottom: "1.5rem" }}>
              <table className="dash-table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Scope</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const roleClass = `sd-role-${u.role}`;
                    return (
                      <tr key={u.id}>
                        <td style={{ fontWeight: 600 }}>
                          {u.email}
                        </td>
                        <td>
                          <span className={`sd-role-badge ${roleClass}`}>
                            {u.role}
                          </span>
                        </td>
                        <td>
                          {u.disabled ? (
                            <span className="sd-badge sd-badge-critical" style={{ fontSize: "0.72rem" }}>
                              Disabled
                            </span>
                          ) : (
                            <span className="sd-badge sd-badge-success" style={{ fontSize: "0.72rem" }}>
                              Active
                            </span>
                          )}
                        </td>
                        <td style={{ fontSize: "0.8rem", color: "var(--dash-muted)" }}>
                          {u.project_ids && u.project_ids.length > 0 ? (
                            <span>{u.project_ids.length} park(s)</span>
                          ) : (
                            <span>All Parks (Global)</span>
                          )}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                            <select
                              value={u.role}
                              onChange={(e) => handleRoleChange(u.id, e.target.value)}
                              className="dash-input"
                              style={{ padding: "0.2rem 0.4rem", fontSize: "0.78rem", height: "auto" }}
                              title="Change Role"
                            >
                              <option value="admin">admin</option>
                              <option value="operator">operator</option>
                              <option value="technician">technician</option>
                              <option value="viewer">viewer</option>
                            </select>

                            <button
                              type="button"
                              className="dash-btn dash-btn-ghost dash-btn-sm"
                              style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }}
                              onClick={() => handleToggleDisabled(u.id, u.disabled)}
                            >
                              {u.disabled ? "Enable" : "Disable"}
                            </button>

                            <button
                              type="button"
                              className="dash-btn dash-btn-ghost dash-btn-sm"
                              style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem", color: "var(--red, #b91c1c)" }}
                              onClick={() => handleDeleteUser(u.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* RBAC Roles Matrix Card */}
          <div className="dash-card">
            <div className="dash-card-title">Role-Based Access Control (RBAC) Specification</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem", marginTop: "1rem" }}>
              <div style={{ padding: "0.75rem", border: "1px solid #c5cdc5", borderRadius: "4px" }}>
                <span className="sd-role-badge sd-role-admin" style={{ marginBottom: "0.5rem" }}>admin</span>
                <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--dash-text)" }}>
                  Full authority. Manages users, plant registration, billing tariffs, alert delivery channels, and platform settings.
                </p>
              </div>
              <div style={{ padding: "0.75rem", border: "1px solid #c5cdc5", borderRadius: "4px" }}>
                <span className="sd-role-badge sd-role-operator" style={{ marginBottom: "0.5rem" }}>operator</span>
                <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--dash-text)" }}>
                  Operations command. Runs deficit scans, dispatches work orders, configures thresholds, and oversees drone missions.
                </p>
              </div>
              <div style={{ padding: "0.75rem", border: "1px solid #c5cdc5", borderRadius: "4px" }}>
                <span className="sd-role-badge sd-role-technician" style={{ marginBottom: "0.5rem" }}>technician</span>
                <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--dash-text)" }}>
                  Field engineering. Executes assigned work orders, completes checklist procedures, uploads repair photos, and triggers fix verification.
                </p>
              </div>
              <div style={{ padding: "0.75rem", border: "1px solid #c5cdc5", borderRadius: "4px" }}>
                <span className="sd-role-badge sd-role-viewer" style={{ marginBottom: "0.5rem" }}>viewer</span>
                <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--dash-text)" }}>
                  Read-only monitoring. Inspects overview charts, peer comparisons, weather forecasts, and historical work order logs.
                </p>
              </div>
            </div>
          </div>

          {/* Add User Modal */}
          {showAddUserModal && (
            <div className="sd-drawer-backdrop" onClick={() => setShowAddUserModal(false)}>
              <div
                className="dash-card"
                style={{
                  position: "fixed",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  width: "440px",
                  maxWidth: "92vw",
                  zIndex: 1001,
                  boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Add User Account</h3>
                  <button
                    type="button"
                    className="dash-btn dash-btn-ghost dash-btn-sm"
                    onClick={() => setShowAddUserModal(false)}
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleCreateUser}>
                  <div className="dash-field" style={{ marginBottom: "1rem" }}>
                    <label htmlFor="new-user-email">Email Address</label>
                    <input
                      id="new-user-email"
                      className="dash-input"
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      placeholder="technician@solardoctor.internal"
                      required
                    />
                  </div>

                  <div className="dash-field" style={{ marginBottom: "1rem" }}>
                    <label htmlFor="new-user-password">Initial Password (min 8 chars)</label>
                    <input
                      id="new-user-password"
                      className="dash-input"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="••••••••"
                      minLength={8}
                      required
                    />
                  </div>

                  <div className="dash-field" style={{ marginBottom: "1.5rem" }}>
                    <label htmlFor="new-user-role">Role</label>
                    <select
                      id="new-user-role"
                      className="dash-input"
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value)}
                    >
                      <option value="operator">Operator (Field Dispatch & Thresholds)</option>
                      <option value="technician">Technician (Repairs & Fix Verification)</option>
                      <option value="viewer">Viewer (Read-Only Dashboards)</option>
                      <option value="admin">Admin (Full System Privileges)</option>
                    </select>
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="dash-btn dash-btn-ghost dash-btn-sm"
                      onClick={() => setShowAddUserModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="dash-btn dash-btn-primary dash-btn-sm"
                      disabled={creatingUser}
                    >
                      {creatingUser ? "Creating Account…" : "Create User"}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
