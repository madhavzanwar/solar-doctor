"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import { plantsApi, weatherApi, type Plant, type WeatherData } from "@/lib/api";

export default function PlantsPage() {
  const [plants, setPlants] = useState<Plant[]>([]);
  const [weathers, setWeathers] = useState<Record<number, WeatherData>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await plantsApi.list();
      setPlants(data);

      // Fetch current weather for each plant in parallel
      const wxResults = await Promise.allSettled(
        data.map((p) => weatherApi.current(p.id))
      );
      const wxMap: Record<number, WeatherData> = {};
      wxResults.forEach((res, i) => {
        if (res.status === "fulfilled" && res.value) {
          wxMap[data[i].id] = res.value;
        }
      });
      setWeathers(wxMap);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load plants.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div className="dash-page-header-row">
        <div className="dash-page-header" style={{ marginBottom: 0 }}>
          <p className="dash-eyebrow">Sites</p>
          <h1 className="dash-section-title">Plants</h1>
          <p className="dash-page-sub">
            Registered solar generation sites and capacity.
          </p>
        </div>
        <Link href="/dashboard/plants/new" className="dash-btn dash-btn-primary">
          Add plant
        </Link>
      </div>

      {error && <div className="dash-error">{error}</div>}

      {loading ? (
        <div className="dash-loading">
          <div className="dash-spinner" />
          <div>Loading plants…</div>
        </div>
      ) : plants.length === 0 ? (
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
        <div className="dash-card" style={{ padding: 0 }}>
          <div className="dash-table-wrap">
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Location</th>
                  <th>Live Weather</th>
                  <th>Capacity</th>
                  <th>Inverter</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {plants.map((plant) => {
                  const wx = weathers[plant.id];
                  return (
                    <tr key={plant.id}>
                      <td style={{ fontWeight: 600 }}>{plant.name}</td>
                      <td style={{ color: "var(--dash-muted)" }}>
                        {plant.location ??
                          `${plant.latitude.toFixed(3)}, ${plant.longitude.toFixed(3)}`}
                      </td>
                      <td className="nowrap">
                        {wx ? (
                          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            <span style={{ fontWeight: 600, color: "var(--dash-sun, #e8a838)" }}>
                              {wx.current.temperature_c.toFixed(1)}°C
                            </span>
                            <span style={{ fontSize: "0.8rem", color: "var(--dash-muted)" }}>
                              {wx.current.condition}
                            </span>
                            {wx.source === "mock" && (
                              <span className="dash-badge dash-badge-muted" style={{ fontSize: "0.6rem", padding: "0.05rem 0.3rem" }}>
                                mock
                              </span>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: "var(--dash-muted)", fontSize: "0.8rem" }}>—</span>
                        )}
                      </td>
                      <td className="nowrap">{plant.capacity_kw} kW</td>
                      <td className="nowrap">{plant.inverter_capacity_kw} kW</td>
                      <td className="nowrap">
                        {plant.is_active ? (
                          <span className="dash-badge dash-badge-green">Active</span>
                        ) : (
                          <span className="dash-badge dash-badge-muted">Inactive</span>
                        )}
                      </td>
                      <td className="nowrap" style={{ color: "var(--dash-muted)" }}>
                        {new Date(plant.created_at).toLocaleDateString()}
                      </td>
                      <td className="nowrap">
                        <Link
                          href={`/dashboard/plants/${plant.id}`}
                          className="dash-btn dash-btn-ghost dash-btn-sm"
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
