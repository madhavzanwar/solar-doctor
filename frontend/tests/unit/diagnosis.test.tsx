import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import DiagnosisModal from "@/components/diagnosis/DiagnosisModal";
import { diagnosisApi, type DiagnosisResponse } from "@/lib/api";
import { formatMoney } from "@/lib/money";

const base: DiagnosisResponse = {
  id: 1,
  plant_id: 2,
  plant_name: "PCCoE Rooftop",
  alert_id: 7,
  timestamp: "2026-11-04T11:30:00Z",
  root_cause_category: "SOILING",
  root_cause_title: "Soiling loss",
  confidence_score: 82,
  estimated_loss_kw: 12.5,
  financial_impact_per_day: 12450,
  currency: "INR",
  urgency_level: "HIGH",
  summary: "s",
  root_cause_details: "details",
  technician_steps: [{ step_number: 1, action: "Clean panels" }],
  created_at: "2026-11-04T11:30:00Z",
};

const html = (d: Partial<DiagnosisResponse>) =>
  renderToStaticMarkup(<DiagnosisModal diagnosis={{ ...base, ...d }} onClose={() => undefined} />);

describe("formatMoney", () => {
  it("says not estimated when the currency is unset", () => {
    expect(formatMoney(100, "unset")).toBe("Not estimated");
    expect(formatMoney(100, null)).toBe("Not estimated");
  });
  it("formats INR with the rupee sign and Indian grouping", () => {
    const out = formatMoney(124500, "INR");
    expect(out).toContain("₹");
    expect(out).toContain("1,24,500");
  });
  it("uses the real currency, never a hard-coded dollar sign", () => {
    expect(formatMoney(10, "EUR")).toContain("€");
    expect(formatMoney(10, "ZZZ")).toContain("ZZZ");
  });
});

describe("DiagnosisModal", () => {
  it("shows the rupee amount for INR", () => {
    const out = html({});
    expect(out).toContain("₹12,450/day");
    expect(out).not.toContain("$");
  });

  it("shows 'Not estimated' and an explanation when the currency is unset", () => {
    const out = html({ currency: "unset", financial_impact_per_day: 0 });
    expect(out).toContain("Not estimated");
    expect(out).toContain("no energy tariff");
    expect(out).not.toContain("/day");
  });

  it("shows a SIMULATED badge when telemetry_source is SIMULATED, and none otherwise", () => {
    expect(html({ telemetry_source: "SIMULATED" })).toContain("SIMULATED");
    expect(html({ telemetry_source: "PVDAQ" })).not.toContain("SIMULATED");
    expect(html({ telemetry_source: null })).not.toContain("SIMULATED");
  });

  it("is an accessible dialog", () => {
    const out = html({});
    expect(out).toContain('role="dialog"');
    expect(out).toContain('aria-modal="true"');
  });
});

describe("diagnosis 422 handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("surfaces the backend detail text of a 422", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Telemetry is simulated; pass allow_simulated to diagnose it" }), {
          status: 422,
        }),
      ),
    );
    await expect(diagnosisApi.diagnoseAlert(1)).rejects.toThrow(
      "Telemetry is simulated; pass allow_simulated to diagnose it",
    );
  });

  it("flattens pydantic 422 lists into readable text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: [{ loc: ["body", "expected_power_kw"], msg: "Input should be less than or equal to 100000000" }] }),
          { status: 422 },
        ),
      ),
    );
    await expect(diagnosisApi.diagnose({ plant_id: 1 })).rejects.toThrow(
      "expected_power_kw: Input should be less than or equal to 100000000",
    );
  });
});
