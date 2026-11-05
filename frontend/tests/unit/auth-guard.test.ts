import { describe, expect, it } from "vitest";
import { guardDecision, isProtectedPath, safeNextPath } from "@/lib/auth-guard";

describe("isProtectedPath", () => {
  it("protects /dashboard and everything below it", () => {
    expect(isProtectedPath("/dashboard")).toBe(true);
    expect(isProtectedPath("/dashboard/plants/3")).toBe(true);
  });
  it("leaves public pages and look-alike prefixes alone", () => {
    expect(isProtectedPath("/")).toBe(false);
    expect(isProtectedPath("/login")).toBe(false);
    expect(isProtectedPath("/dashboards")).toBe(false);
  });
});

describe("guardDecision", () => {
  it("redirects an anonymous dashboard request to /login with the target preserved", () => {
    const d = guardDecision("/dashboard/alerts", "?filter=open", false);
    expect(d).toEqual({
      action: "redirect",
      location: `/login?next=${encodeURIComponent("/dashboard/alerts?filter=open")}`,
    });
  });
  it("lets an authenticated request through", () => {
    expect(guardDecision("/dashboard", "", true)).toEqual({ action: "next" });
  });
  it("never redirects public routes", () => {
    expect(guardDecision("/login", "", false)).toEqual({ action: "next" });
  });
});

describe("safeNextPath", () => {
  it("accepts same-origin paths", () => {
    expect(safeNextPath("/dashboard/plants")).toBe("/dashboard/plants");
  });
  it("rejects open-redirect targets", () => {
    expect(safeNextPath("https://evil.example")).toBe("/dashboard");
    expect(safeNextPath("//evil.example")).toBe("/dashboard");
    expect(safeNextPath("/\\evil.example")).toBe("/dashboard");
    expect(safeNextPath(null)).toBe("/dashboard");
  });
});
