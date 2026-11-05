import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const flush = async () => {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
};

afterEach(() => {
  vi.resetModules();
  vi.doUnmock("@/lib/api");
  vi.doUnmock("@/components/forecast/OnlineAdapterChip");
  document.body.innerHTML = "";
});

const tracker = {
  id: 9,
  name: "PVDAQ 9068",
  location: "Colorado [single-axis tracker, fixed-tilt baseline invalid]",
  capacity_kw: 100,
  inverter_capacity_kw: 90,
  latitude: 1,
  longitude: 2,
  timezone: "UTC",
  is_active: true,
  source: "PVDAQ",
  created_at: "2026-01-01T00:00:00Z",
};
const NOTICE = "Not supported for single-axis trackers (fixed-tilt baseline invalid)";

describe("single-axis tracker plants (baseline_unsupported_for_trackers)", () => {
  it("performance page: labelled state, no forecast call for a tracker plant, no error banner", async () => {
    const getProbabilistic = vi.fn();
    vi.doMock("@/lib/api", () => ({
      plantsApi: { list: vi.fn(async () => [tracker]) },
      forecastApi: { getProbabilistic, list: vi.fn(async () => []), generate: vi.fn() },
    }));
    vi.doMock("@/components/forecast/OnlineAdapterChip", () => ({ default: () => null }));
    const { default: Page } = await import("@/app/dashboard/performance/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<Page />));
    await flush();
    expect(host.querySelector('[data-testid="tracker-unsupported"]')?.textContent).toContain(NOTICE);
    expect(getProbabilistic).not.toHaveBeenCalled();
    expect(host.querySelector(".dash-error")).toBeNull();
    act(() => root.unmount());
  });

  it("performance page: a 422 object detail shows the labelled state, never 'Unprocessable Entity'", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    const plain = { ...tracker, id: 3, location: "Pune" }; // plant record does not reveal it; the API does
    const err = new ApiError(422, "Baseline unsupported.", {
      detail: { status: "baseline_unsupported_for_trackers", message: "Baseline unsupported." },
    });
    vi.doMock("@/lib/api", () => ({
      plantsApi: { list: vi.fn(async () => [plain]) },
      forecastApi: { getProbabilistic: vi.fn(async () => Promise.reject(err)), list: vi.fn(), generate: vi.fn() },
    }));
    vi.doMock("@/components/forecast/OnlineAdapterChip", () => ({ default: () => null }));
    const { default: Page } = await import("@/app/dashboard/performance/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<Page />));
    await flush();
    const box = host.querySelector('[data-testid="tracker-unsupported"]');
    expect(box?.textContent).toContain(NOTICE);
    expect(box?.textContent).toContain("Baseline unsupported.");
    expect(host.textContent).not.toContain("Unprocessable");
    expect(host.querySelector(".dash-error")).toBeNull();
    act(() => root.unmount());
  });

  it("plant detail: labelled state and disabled Run forecast, no forecast requests", async () => {
    const list = vi.fn();
    vi.doMock("@/lib/api", () => ({
      alertsApi: { list: vi.fn(async () => []), resolve: vi.fn() },
      forecastApi: { list, summary: vi.fn(), generate: vi.fn() },
      plantsApi: { get: vi.fn(async () => tracker), getConfig: vi.fn(async () => null) },
      weatherApi: { current: vi.fn(async () => null) },
    }));
    const { default: Page } = await import("@/app/dashboard/plants/[id]/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<Page params={Promise.resolve({ id: "9" })} />);
    });
    await flush();
    await flush();
    expect(host.querySelector('[data-testid="tracker-unsupported"]')?.textContent).toContain(NOTICE);
    const run = [...host.querySelectorAll("button")].find((b) => /Run forecast/.test(b.textContent ?? ""));
    expect(run?.hasAttribute("disabled")).toBe(true);
    expect(list).not.toHaveBeenCalled();
    act(() => root.unmount());
  });
});
