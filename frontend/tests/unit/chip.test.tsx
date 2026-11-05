import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import OnlineAdapterChip from "@/components/forecast/OnlineAdapterChip";

// Server render = the state before any status has arrived (or after the call failed).
describe("OnlineAdapterChip without data", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

  it("compact chip shows a neutral 'No data yet', never an invented healthy state", () => {
    const out = renderToStaticMarkup(<OnlineAdapterChip plantId={1} />);
    expect(out).toContain("No data yet");
    expect(out).not.toContain("+0.0%");
    expect(out).not.toMatch(/on track/i);
  });

  it("expanded panel shows dashes instead of default numbers", () => {
    const out = renderToStaticMarkup(<OnlineAdapterChip plantId={1} expanded />);
    expect(out).toContain("No data yet");
    expect(out).not.toContain("1.000×");
    expect(out).not.toMatch(/on track/i);
  });

  it("renders nothing without a plant", () => {
    expect(renderToStaticMarkup(<OnlineAdapterChip plantId={null} />)).toBe("");
  });
});
