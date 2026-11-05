/** Labelled state for plants whose fixed-tilt physics baseline is invalid (single-axis trackers). */
export function TrackerUnsupported({ detail }: { detail?: string | null }) {
  return (
    <div className="dash-card dash-empty" role="status" data-testid="tracker-unsupported">
      <p style={{ fontWeight: 600 }}>Not supported for single-axis trackers (fixed-tilt baseline invalid)</p>
      <p style={{ color: "var(--dash-muted)", marginTop: "0.4rem" }}>
        {detail || "Forecasts and expected-power baselines for this plant would be misleading, so they are not produced."}
      </p>
    </div>
  );
}
