import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import DiagnosisModal from "@/components/diagnosis/DiagnosisModal";
import { forecastApi, type DiagnosisResponse } from "@/lib/api";
import { roleLabel } from "@/lib/roles";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("roleLabel", () => {
  it("maps the four backend roles and never guesses", () => {
    expect(roleLabel("admin")).toBe("Administrator");
    expect(roleLabel("operator")).toBe("Operator");
    expect(roleLabel("technician")).toBe("Technician");
    expect(roleLabel("viewer")).toBe("Viewer");
    expect(roleLabel(null)).toBe("");
    expect(roleLabel(undefined)).toBe("");
  });
});

describe("forecastApi.summary", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("resolves to null on 404 (no forecasts yet) and still throws other errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "No forecasts" }), { status: 404 })));
    await expect(forecastApi.summary(1)).resolves.toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 })));
    await expect(forecastApi.summary(1)).rejects.toThrow("boom");
  });
});

const diag: DiagnosisResponse = {
  plant_id: 1,
  timestamp: "2026-11-04T11:30:00Z",
  root_cause_category: "SOILING",
  root_cause_title: "Soiling loss",
  confidence_score: 80,
  estimated_loss_kw: 1,
  financial_impact_per_day: 0,
  currency: "unset",
  urgency_level: "LOW",
  summary: "s",
  root_cause_details: "d",
  technician_steps: [],
  created_at: "2026-11-04T11:30:00Z",
};

describe("DiagnosisModal focus handling", () => {
  it("moves focus in, closes on Escape, and returns focus to the trigger that stays focusable", () => {
    const trigger = document.createElement("button");
    trigger.setAttribute("aria-disabled", "true"); // busy state: still focusable, unlike `disabled`
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const onClose = vi.fn();
    act(() => root.render(<DiagnosisModal diagnosis={diag} onClose={onClose} />));
    expect(host.querySelector('[role="dialog"]')?.contains(document.activeElement)).toBe(true);

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(onClose).toHaveBeenCalled();

    act(() => root.unmount());
    expect(document.activeElement).toBe(trigger);
    host.remove();
    trigger.remove();
  });
});
