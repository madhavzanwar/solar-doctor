import { PageHeader } from "@/components/ui/states";

export const metadata = { title: "Settings — SolarDoctor" };

const NOTE =
  "Not connected yet. These fields show what will be configurable per plant; nothing is read from or saved to the backend.";

function Field({
  id,
  label,
  unit,
  hint,
  type = "number",
}: {
  id: string;
  label: string;
  unit?: string;
  hint?: string;
  type?: string;
}) {
  return (
    <div className="dash-field">
      <label htmlFor={id}>{unit ? `${label} (${unit})` : label}</label>
      <input id={id} className="dash-input" type={type} disabled aria-describedby={`${id}-hint`} placeholder="—" />
      <span id={`${id}-hint`} className="sd-visually-hidden">
        {hint ?? "Not connected yet"}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        sub="Tariffs, cleaning cost, alert thresholds and users."
      />

      <div className="sd-disabled-note" role="note">
        <strong>Settings are not connected yet</strong>
        {NOTE}
      </div>

      <div className="dash-card" style={{ marginBottom: "1.15rem" }}>
        <div className="dash-card-title">
          Tariff
          <span className="dash-badge dash-badge-muted">Not connected</span>
        </div>
        <div className="dash-form-grid">
          <Field id="set-tariff" label="Energy tariff" unit="₹/kWh" />
          <Field id="set-currency" label="Currency" type="text" />
        </div>
      </div>

      <div className="dash-card" style={{ marginBottom: "1.15rem" }}>
        <div className="dash-card-title">
          Cleaning cost
          <span className="dash-badge dash-badge-muted">Not connected</span>
        </div>
        <div className="dash-form-grid">
          <Field id="set-clean-cost" label="Cleaning cost" unit="₹ per MW" />
          <Field id="set-water" label="Water per clean" unit="L per module" />
          <Field id="set-labour" label="Labour" unit="hours per clean" />
        </div>
      </div>

      <div className="dash-card" style={{ marginBottom: "1.15rem" }}>
        <div className="dash-card-title">
          Alert thresholds
          <span className="dash-badge dash-badge-muted">Not connected</span>
        </div>
        <div className="dash-form-grid">
          <Field id="set-deficit" label="Deficit alert threshold" unit="%" />
          <Field id="set-duration" label="Minimum sustained duration" unit="hours" />
          <Field id="set-soiling" label="Soiling ratio alert" />
          <Field id="set-confidence" label="Field-check confidence floor" unit="0–1" />
        </div>
      </div>

      <div className="dash-card">
        <div className="dash-card-title">
          Users
          <span className="dash-badge dash-badge-muted">Not connected</span>
        </div>
        <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--muted)" }}>
          User and role management (admin, operator, technician, viewer) will be managed here. The backend
          exposes user endpoints, but this page does not call them yet.
        </p>
      </div>
    </>
  );
}
