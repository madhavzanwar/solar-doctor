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
  document.body.innerHTML = "";
});

describe("/dashboard/plants empty state", () => {
  it("does not claim 'No plants registered yet' when the request failed", async () => {
    vi.doMock("@/lib/api", () => ({
      plantsApi: { list: vi.fn(async () => Promise.reject(new Error("API unreachable"))) },
      weatherApi: { current: vi.fn() },
    }));
    const { default: PlantsPage } = await import("@/app/dashboard/plants/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<PlantsPage />));
    await flush();
    expect(host.textContent).toContain("API unreachable");
    expect(host.textContent).not.toContain("No plants registered yet");
    act(() => root.unmount());
  });

  it("shows the empty state when the request succeeded with zero plants", async () => {
    vi.doMock("@/lib/api", () => ({
      plantsApi: { list: vi.fn(async () => []) },
      weatherApi: { current: vi.fn() },
    }));
    const { default: PlantsPage } = await import("@/app/dashboard/plants/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<PlantsPage />));
    await flush();
    expect(host.textContent).toContain("No plants registered yet");
    act(() => root.unmount());
  });
});

describe("alerts fault sandbox 'Run diagnosis' button", () => {
  it("uses aria-disabled/aria-busy (stays focusable), never the disabled attribute", async () => {
    let resolveDiag: (v: unknown) => void = () => undefined;
    const diagnose = vi.fn(() => new Promise((r) => (resolveDiag = r)));
    vi.doMock("@/lib/api", () => ({
      alertsApi: { list: vi.fn(async () => []), resolve: vi.fn() },
      plantsApi: { list: vi.fn(async () => [{ id: 1, name: "P1" }]) },
      diagnosisApi: { getTaxonomy: vi.fn(async () => []), diagnose },
    }));
    vi.doMock("@/components/diagnosis/DiagnosisModal", () => ({ default: () => null }));
    const { default: AlertsPage } = await import("@/app/dashboard/alerts/page");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<AlertsPage />));
    await flush();
    const tab = [...host.querySelectorAll("button")].find((b) => /sandbox/i.test(b.textContent ?? ""));
    expect(tab).toBeTruthy();
    act(() => tab!.click());
    const run = () =>
      [...host.querySelectorAll("button")].find((b) => /Run diagnosis|Running/.test(b.textContent ?? ""))!;
    expect(run().hasAttribute("disabled")).toBe(false);
    expect(run().getAttribute("aria-disabled")).toBe("false");
    act(() => run().click());
    expect(diagnose).toHaveBeenCalledTimes(1);
    expect(run().hasAttribute("disabled")).toBe(false);
    expect(run().getAttribute("aria-disabled")).toBe("true");
    expect(run().getAttribute("aria-busy")).toBe("true");
    run().focus();
    expect(document.activeElement).toBe(run());
    act(() => run().click()); // busy: ignored
    expect(diagnose).toHaveBeenCalledTimes(1);
    resolveDiag({});
    await flush();
    act(() => root.unmount());
    vi.doUnmock("@/components/diagnosis/DiagnosisModal");
  });
});
