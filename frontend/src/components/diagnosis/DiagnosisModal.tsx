"use client";

import React, { useEffect, useRef } from "react";
import type { DiagnosisResponse } from "@/lib/api";
import { CURRENCY_UNSET, formatMoney } from "@/lib/money";
import { SourceBadge } from "@/components/ui/SourceBadge";

interface DiagnosisModalProps {
  diagnosis: DiagnosisResponse;
  onClose: () => void;
  onResolveAlert?: (alertId: number) => void;
}

export default function DiagnosisModal({
  diagnosis,
  onClose,
  onResolveAlert,
}: DiagnosisModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Dialog behaviour (DESIGN.md §11): focus moves in, Tab is trapped, Esc closes, focus returns on close.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusables = () =>
      Array.from(
        panel?.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "Tab") {
        const items = focusables();
        if (items.length === 0) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  const getUrgencyColor = (urgency: string) => {
    switch (urgency.toUpperCase()) {
      case "CRITICAL":
        return "var(--danger)";
      case "HIGH":
        return "var(--sun)";
      case "MEDIUM":
        return "var(--sun)";
      default:
        return "var(--field)";
    }
  };

  const urgencyColor = getUrgencyColor(diagnosis.urgency_level);
  const moneyUnset = !diagnosis.currency || diagnosis.currency.toLowerCase() === CURRENCY_UNSET;
  const revenueValue = moneyUnset
    ? formatMoney(0, diagnosis.currency)
    : `${formatMoney(diagnosis.financial_impact_per_day, diagnosis.currency)}/day`;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(20, 24, 20, 0.5)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.25rem",
      }}
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnosis-title"
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 2,
          maxWidth: 720,
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
          color: "var(--ink)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: "1.15rem 1.35rem",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <p
              style={{
                margin: 0,
                fontSize: "0.72rem",
                fontWeight: 600,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "var(--muted)",
              }}
            >
              Root-cause diagnosis
            </p>
            <h2
              id="diagnosis-title"
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontSize: "1.2rem",
                fontWeight: 700,
                margin: "0.25rem 0 0",
                letterSpacing: "-0.02em",
                overflowWrap: "anywhere",
              }}
            >
              {diagnosis.root_cause_title} <SourceBadge source={diagnosis.telemetry_source} />
            </h2>
            <p style={{ margin: "0.35rem 0 0", fontSize: "0.8rem", color: "var(--muted)" }}>
              Plant #{diagnosis.plant_id}
              {diagnosis.plant_name ? ` · ${diagnosis.plant_name}` : ""} ·{" "}
              {new Date(diagnosis.timestamp).toLocaleString()}
              {diagnosis.telemetry_ts
                ? ` · telemetry as of ${new Date(diagnosis.telemetry_ts).toLocaleString()}`
                : ""}
              {diagnosis.telemetry_source ? ` · source ${diagnosis.telemetry_source}` : ""}
            </p>
          </div>

          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "none",
              border: "none",
              color: "var(--muted)",
              fontSize: "1.15rem",
              cursor: "pointer",
              padding: "0.2rem 0.4rem",
              flexShrink: 0,
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ padding: "1.35rem" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 0,
              marginBottom: "1.25rem",
              border: "1px solid var(--line)",
            }}
          >
            {[
              {
                label: "Urgency",
                value: diagnosis.urgency_level,
                color: urgencyColor,
              },
              {
                label: "Confidence",
                value: `${diagnosis.confidence_score.toFixed(0)}%`,
                color: "var(--field)",
              },
              {
                label: "Revenue impact",
                value: revenueValue,
                color: "var(--sun)",
              },
              {
                label: "Power deficit",
                value: `${diagnosis.estimated_loss_kw.toFixed(1)} kW`,
                color: "var(--ink)",
              },
            ].map((item, i, arr) => (
              <div
                key={item.label}
                style={{
                  padding: "0.85rem 1rem",
                  borderRight: i < arr.length - 1 ? "1px solid var(--line)" : undefined,
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 600,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--muted)",
                    marginBottom: "0.25rem",
                  }}
                >
                  {item.label}
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-display), sans-serif",
                    fontWeight: 700,
                    fontSize: "0.95rem",
                    color: item.color,
                    overflowWrap: "anywhere",
                  }}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </div>

          {(moneyUnset || diagnosis.financial_assumption) && (
            <p style={{ margin: "-0.6rem 0 1.25rem", fontSize: "0.78rem", color: "var(--muted)" }}>
              {moneyUnset
                ? "Revenue impact not estimated: this plant has no energy tariff set."
                : null}
              {diagnosis.financial_assumption ? ` ${diagnosis.financial_assumption}` : ""}
            </p>
          )}

          <div
            style={{
              border: "1px solid var(--line)",
              borderLeft: "3px solid var(--field)",
              padding: "0.95rem 1.1rem",
              marginBottom: "1.25rem",
            }}
          >
            <div
              style={{
                fontSize: "0.7rem",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                color: "var(--field)",
                fontWeight: 700,
                marginBottom: "0.35rem",
              }}
            >
              Finding
            </div>
            <p
              style={{
                margin: 0,
                fontSize: "0.9rem",
                color: "var(--muted)",
                lineHeight: 1.55,
                overflowWrap: "anywhere",
              }}
            >
              {diagnosis.root_cause_details}
            </p>
          </div>

          {diagnosis.telemetry_evidence && (
            <div style={{ marginBottom: "1.25rem" }}>
              <div
                style={{
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "var(--muted)",
                  marginBottom: "0.5rem",
                }}
              >
                Evidence
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {diagnosis.inverter_error_code && (
                  <span className="dash-badge dash-badge-red">
                    {diagnosis.inverter_error_code}
                  </span>
                )}
                {diagnosis.telemetry_evidence.deficit_percentage != null && (
                  <span className="dash-badge dash-badge-orange">
                    {String(diagnosis.telemetry_evidence.deficit_percentage)}% deficit
                  </span>
                )}
                {diagnosis.telemetry_evidence.irradiance_w_m2 != null && (
                  <span className="dash-badge dash-badge-muted">
                    {String(diagnosis.telemetry_evidence.irradiance_w_m2)} W/m²
                  </span>
                )}
                {diagnosis.telemetry_evidence.temperature_c != null && (
                  <span className="dash-badge dash-badge-muted">
                    Ambient {String(diagnosis.telemetry_evidence.temperature_c)}°C
                  </span>
                )}
                {diagnosis.telemetry_evidence.module_temp_c != null && (
                  <span className="dash-badge dash-badge-muted">
                    Module {String(diagnosis.telemetry_evidence.module_temp_c)}°C
                  </span>
                )}
              </div>
            </div>
          )}

          {diagnosis.safety_warning && (
            <div
              style={{
                background: "var(--dash-danger-dim)",
                borderLeft: "3px solid var(--danger)",
                padding: "0.85rem 1rem",
                marginBottom: "1.25rem",
                fontSize: "0.86rem",
                color: "var(--danger)",
                lineHeight: 1.45,
                overflowWrap: "anywhere",
              }}
            >
              {diagnosis.safety_warning}
            </div>
          )}

          <div style={{ marginBottom: "1.25rem" }}>
            <h4
              style={{
                fontFamily: "var(--font-display), sans-serif",
                fontSize: "1rem",
                fontWeight: 700,
                margin: "0 0 0.75rem",
                letterSpacing: "-0.02em",
              }}
            >
              Technician steps
            </h4>

            <ol
              style={{
                margin: 0,
                padding: 0,
                listStyle: "none",
                borderTop: "1px solid var(--line)",
              }}
            >
              {diagnosis.technician_steps.map((s) => (
                <li
                  key={s.step_number}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "2.5rem minmax(0, 1fr)",
                    gap: "0.85rem",
                    padding: "0.9rem 0",
                    borderBottom: "1px solid var(--line)",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-display), sans-serif",
                      fontWeight: 700,
                      fontSize: "1rem",
                      color: "var(--field)",
                    }}
                  >
                    {String(s.step_number).padStart(2, "0")}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "0.9rem",
                        lineHeight: 1.45,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {s.action}
                    </div>
                    {(s.required_tools ?? []).length > 0 && (
                      <div
                        style={{
                          marginTop: "0.4rem",
                          fontSize: "0.78rem",
                          color: "var(--muted)",
                          overflowWrap: "anywhere",
                        }}
                      >
                        Tools: {(s.required_tools ?? []).join(", ")}
                      </div>
                    )}
                    {s.safety_note && (
                      <div
                        style={{
                          marginTop: "0.3rem",
                          fontSize: "0.78rem",
                          color: "var(--sun)",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {s.safety_note}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {diagnosis.preventative_advice && (
            <div
              style={{
                border: "1px dashed var(--line)",
                padding: "0.85rem 1rem",
                fontSize: "0.85rem",
                color: "var(--muted)",
                lineHeight: 1.5,
                overflowWrap: "anywhere",
              }}
            >
              <strong style={{ color: "var(--ink)" }}>Prevention: </strong>
              {diagnosis.preventative_advice}
            </div>
          )}
        </div>

        <div
          style={{
            padding: "1rem 1.35rem",
            borderTop: "1px solid var(--line)",
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.65rem",
            flexWrap: "wrap",
            background: "var(--paper)",
          }}
        >
          {diagnosis.alert_id && onResolveAlert && (
            <button
              className="dash-btn dash-btn-primary"
              onClick={() => {
                if (diagnosis.alert_id) {
                  onResolveAlert(diagnosis.alert_id);
                  onClose();
                }
              }}
            >
              Resolve alert
            </button>
          )}
          <button className="dash-btn dash-btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
