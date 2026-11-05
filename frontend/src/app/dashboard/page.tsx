"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import {
  alertsApi,
  forecastApi,
  plantsApi,
  weatherApi,
  type Alert,
  type ForecastRecord,
  type Plant,
  type WeatherData,
} from "@/lib/api";
import ForecastActualChart from "@/components/forecast/ForecastActualChart";
import OnlineAdapterChip from "@/components/forecast/OnlineAdapterChip";


function WeatherWidget({ weather }: { weather: WeatherData | null }) {
  if (!weather) {
    return (
      <div className="dash-card">
        <div className="dash-card-title">Current weather</div>
        <div className="dash-empty" style={{ padding: "1.5rem 0" }}>
          Loading weather…
        </div>
      </div>
    );
  }

  const c = weather.current;
  const isMock = weather.source === "mock";

  return (
    <div className="dash-card">
      <div className="dash-card-title">
        Current weather
        {isMock && <span className="dash-badge dash-badge-muted">mock</span>}
      </div>

      <div style={{ marginBottom: "0.85rem" }}>
        <div className="dash-weather-temp">{c.temperature_c.toFixed(1)}°C</div>
        <div className="dash-weather-meta">
          {c.condition} · {weather.location_name}
        </div>
      </div>

      <div className="dash-stat-row">
        <span className="dash-stat-label">Irradiance</span>
        <span className="dash-stat-value" style={{ color: "var(--sun)" }}>
          {c.irradiance_w_m2.toFixed(0)} W/m²
        </span>
      </div>
      <div className="dash-stat-row">
        <span className="dash-stat-label">Humidity</span>
        <span className="dash-stat-value">{c.humidity_pct.toFixed(0)}%</span>
      </div>
      <div className="dash-stat-row">
        <span className="dash-stat-label">Cloud cover</span>
        <span className="dash-stat-value">{c.cloud_cover_pct.toFixed(0)}%</span>
      </div>
      <div className="dash-stat-row">
        <span className="dash-stat-label">Wind</span>
        <span className="dash-stat-value">{c.wind_speed_kph.toFixed(1)} km/h</span>
      </div>
      <div className="dash-stat-row">
        <span className="dash-stat-label">UV index</span>
        <span
          className="dash-stat-value"
          style={{ color: c.uv_index >= 6 ? "var(--sun)" : undefined }}
        >
          {c.uv_index.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function AlertRow({
  alert,
  onResolve,
}: {
  alert: Alert;
  onResolve: (id: number) => void;
}) {
  const severity = alert.severity as "CRITICAL" | "WARNING" | "INFO";
  const time = new Date(alert.timestamp).toLocaleString();

  return (
    <div className={`dash-alert-row ${severity}`}>
      <span className={`dash-alert-badge ${severity}`}>{severity}</span>
      <span className="dash-alert-msg">{alert.message}</span>
      <span className="dash-alert-time">{time}</span>
      {!alert.is_resolved && (
        <div className="dash-alert-actions">
          <button
            className="dash-alert-resolve-btn"
            onClick={() => onResolve(alert.id)}
          >
            Resolve
          </button>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [plants, setPlants] = useState<Plant[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(null);
  const [forecasts, setForecasts] = useState<ForecastRecord[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingPlantData, setLoadingPlantData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, a] = await Promise.all([plantsApi.list(), alertsApi.list(undefined, 20)]);
      setPlants(p);
      setAlerts(a);

      if (p.length > 0) {
        const initialId = p[0].id;
        setSelectedPlantId(initialId);
        const [fc, wx] = await Promise.all([
          forecastApi.list(initialId, 48),
          weatherApi.current(initialId).catch(() => null),
        ]);
        setForecasts(fc);
        setWeather(wx);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load dashboard data.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSelectPlant = async (plantId: number) => {
    setSelectedPlantId(plantId);
    setLoadingPlantData(true);
    try {
      const [fc, wx] = await Promise.all([
        forecastApi.list(plantId, 48),
        weatherApi.current(plantId).catch(() => null),
      ]);
      setForecasts(fc);
      setWeather(wx);
    } catch {
      // ignore
    } finally {
      setLoadingPlantData(false);
    }
  };

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

  const activePlants = plants.filter((p) => p.is_active).length;
  const totalCapacity = plants.reduce((s, p) => s + p.capacity_kw, 0);
  const openAlerts = alerts.filter((a) => !a.is_resolved);
  const criticalAlerts = openAlerts.filter((a) => a.severity === "CRITICAL").length;

  return (
    <>
      <div className="dash-page-header">
        <p className="dash-eyebrow">Fleet status</p>
        <h1 className="dash-section-title">Overview</h1>
        <p className="dash-page-sub">
          Live status across registered solar plants.
        </p>
      </div>

      {error && <div className="dash-error">{error}</div>}

      {loading ? (
        <div className="dash-loading">
          <div className="dash-spinner" />
          <div>Loading dashboard…</div>
        </div>
      ) : (
        <>
          <div className="dash-kpi-grid">
            <div className="dash-kpi">
              <div className="dash-kpi-label">Active plants</div>
              <div className="dash-kpi-value dash-kpi-accent">
                {activePlants}
                <span className="dash-kpi-unit">/ {plants.length}</span>
              </div>
              <div className="dash-kpi-sub">registered sites</div>
            </div>

            <div className="dash-kpi">
              <div className="dash-kpi-label">Total capacity</div>
              <div className="dash-kpi-value dash-kpi-sun">
                {totalCapacity.toFixed(1)}
                <span className="dash-kpi-unit">kW</span>
              </div>
              <div className="dash-kpi-sub">across all plants</div>
            </div>

            <div className="dash-kpi">
              <div className="dash-kpi-label">Open alerts</div>
              <div className={`dash-kpi-value ${criticalAlerts > 0 ? "dash-kpi-danger" : "dash-kpi-warning"}`}>
                {openAlerts.length}
              </div>
              <div className="dash-kpi-sub">{criticalAlerts} critical</div>
            </div>

            <div className="dash-kpi">
              <div className="dash-kpi-label">Forecast records</div>
              <div className="dash-kpi-value">{forecasts.length}</div>
              <div className="dash-kpi-sub">
                {plants.find((p) => p.id === selectedPlantId)?.name ?? (plants.length > 0 ? plants[0].name : "—")}
              </div>
            </div>
          </div>

          <div className="dash-split">
            <div className="dash-card">
              <div
                className="dash-card-title"
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                  <span>Yield forecast</span>
                  {plants.length > 0 && (
                    <select
                      value={selectedPlantId ?? plants[0].id}
                      onChange={(e) => handleSelectPlant(Number(e.target.value))}
                      aria-label="Select active solar plant"
                      className="dash-input"
                      style={{
                        padding: "0.25rem 0.5rem",
                        fontSize: "0.78rem",
                        fontWeight: 600,
                        height: "auto",
                        maxWidth: 260,
                        cursor: "pointer",
                      }}
                    >
                      {plants.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  )}
                  {loadingPlantData && (
                    <span style={{ fontSize: "0.72rem", color: "var(--dash-muted)" }}>Loading…</span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                  <OnlineAdapterChip plantId={selectedPlantId ?? (plants[0]?.id || null)} />
                  <Link href="/dashboard/forecasts" className="dash-btn dash-btn-ghost dash-btn-sm">
                    Forecast detail →
                  </Link>
                </div>
              </div>
              <ForecastActualChart
                records={forecasts}
                capacityKw={plants.find((p) => p.id === (selectedPlantId ?? plants[0]?.id))?.capacity_kw}
                height={220}
                showControls
              />
            </div>

            <WeatherWidget weather={weather} />
          </div>

          <div className="dash-card" style={{ marginBottom: "1.5rem" }}>
            <div className="dash-card-title">Recent alerts</div>
            {openAlerts.length === 0 ? (
              <div className="dash-empty" style={{ padding: "1.5rem 0" }}>
                No open alerts.
              </div>
            ) : (
              <div className="dash-alert-list">
                {openAlerts.slice(0, 6).map((a) => (
                  <AlertRow key={a.id} alert={a} onResolve={handleResolve} />
                ))}
              </div>
            )}
            {openAlerts.length > 6 && (
              <div style={{ marginTop: "0.85rem" }}>
                <Link href="/dashboard/alerts" className="dash-btn dash-btn-ghost dash-btn-sm">
                  View all {openAlerts.length} alerts
                </Link>
              </div>
            )}
          </div>

          <div className="dash-page-header-row" style={{ marginBottom: "1rem" }}>
            <h2 className="dash-section-title" style={{ margin: 0, fontSize: "1.25rem" }}>
              Your plants
            </h2>
            <Link href="/dashboard/plants/new" className="dash-btn dash-btn-primary">
              Add plant
            </Link>
          </div>

          {plants.length === 0 ? (
            <div className="dash-card dash-empty">
              <p>No plants registered yet.</p>
              <Link
                href="/dashboard/plants/new"
                className="dash-btn dash-btn-primary"
                style={{ marginTop: "1rem" }}
              >
                Register your first plant
              </Link>
            </div>
          ) : (
            <div className="dash-plant-grid">
              {plants.map((plant) => (
                <Link
                  key={plant.id}
                  href={`/dashboard/plants/${plant.id}`}
                  className="dash-plant-card"
                >
                  <div className="dash-plant-name">
                    <span
                      className={`dash-status-dot ${plant.is_active ? "dash-status-active" : "dash-status-inactive"}`}
                    />
                    {plant.name}
                  </div>
                  <div className="dash-plant-loc">
                    {plant.location ??
                      `${plant.latitude.toFixed(3)}, ${plant.longitude.toFixed(3)}`}
                  </div>
                  <div className="dash-plant-stats">
                    <div>
                      <div className="dash-plant-stat-label">Capacity</div>
                      <div className="dash-plant-stat-value">{plant.capacity_kw} kW</div>
                    </div>
                    <div>
                      <div className="dash-plant-stat-label">Inverter</div>
                      <div className="dash-plant-stat-value">
                        {plant.inverter_capacity_kw} kW
                      </div>
                    </div>
                    {plant.module_count && (
                      <div>
                        <div className="dash-plant-stat-label">Modules</div>
                        <div className="dash-plant-stat-value">{plant.module_count}</div>
                      </div>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
