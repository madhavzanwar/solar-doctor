import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/lib/api/http";
import { ACCESS_KEY, REFRESH_KEY, cookieLifetimeSeconds, parseUtc, saveSession, saveTokens } from "@/lib/api/storage";
import { login } from "@/lib/api/auth";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
let location: { href: string; protocol: string };
let cookieWrites: string[];

beforeEach(() => {
  localStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  location = { href: "/dashboard", protocol: "http:" };
  Object.defineProperty(window, "location", { value: location, writable: true, configurable: true });
  cookieWrites = [];
  Object.defineProperty(document, "cookie", {
    configurable: true,
    get: () => cookieWrites[cookieWrites.length - 1] ?? "",
    set: (v: string) => {
      cookieWrites.push(v);
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const isRefresh = (u: unknown) => String(u).includes("/auth/refresh");
const isHealth = (u: unknown) => String(u).includes("/health");

describe("network failure on an authenticated call (status 0)", () => {
  it("refreshes once and retries when the first call is unreadable", async () => {
    saveSession({ accessToken: "old", refreshToken: "r0" });
    let calls = 0;
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (isRefresh(url)) return json({ token: "new", refresh_token: "r1", expires_in: 43200 });
      calls += 1;
      if (calls === 1) throw new TypeError("Failed to fetch"); // e.g. a 401 without CORS headers
      expect(new Headers(init.headers).get("Authorization")).toBe("Bearer new");
      return json([{ id: 1 }]);
    });
    await expect(apiFetch("/api/v1/plants")).resolves.toEqual([{ id: 1 }]);
    expect(localStorage.getItem(REFRESH_KEY)).toBe("r1");
  });

  it("clears the session and goes to /login when the refresh is rejected", async () => {
    saveSession({ accessToken: "old", refreshToken: "r0" });
    fetchMock.mockImplementation(async (url: string) => {
      if (isRefresh(url)) return json({ detail: "bad refresh" }, 401);
      throw new TypeError("Failed to fetch");
    });
    await expect(apiFetch("/api/v1/plants")).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(location.href).toBe("/login");
  });

  it("treats an unreadable refresh as an auth failure when the API itself is reachable", async () => {
    saveSession({ accessToken: "old", refreshToken: "r0" });
    fetchMock.mockImplementation(async (url: string) => {
      if (isHealth(url)) return json({ status: "ok" });
      throw new TypeError("Failed to fetch"); // both the call and the refresh are CORS-blocked 401s
    });
    await expect(apiFetch("/api/v1/plants")).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe("/login");
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
  });

  it("reports 'could not reach the API' only when the API is genuinely unreachable, and keeps the session", async () => {
    saveSession({ accessToken: "old", refreshToken: "r0" });
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await apiFetch("/api/v1/plants").catch((e: unknown) => e)) as { status: number; message: string };
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/Could not reach the SolarDoctor API/);
    expect(localStorage.getItem(ACCESS_KEY)).toBe("old");
    expect(location.href).toBe("/dashboard");
  });

  it("does not attempt a refresh for unauthenticated calls", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiFetch("/api/v1/health")).rejects.toMatchObject({ status: 0 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("presence cookie", () => {
  it("parses the backend's naive timestamps as UTC regardless of the local zone", () => {
    expect(parseUtc("2026-11-05T21:27:59.620538")).toBe(Date.UTC(2026, 10, 5, 21, 27, 59, 620));
    expect(parseUtc("2026-11-05T21:27:59Z")).toBe(Date.UTC(2026, 10, 5, 21, 27, 59));
    expect(parseUtc("2026-11-05T21:27:59+05:30")).toBe(Date.UTC(2026, 10, 5, 15, 57, 59));
  });

  it("lives as long as the refresh token, else expires_in, else seven days", () => {
    const now = Date.UTC(2026, 10, 5, 0, 0, 0);
    expect(cookieLifetimeSeconds({ expires_in: 43200, refresh_expires_at: "2026-11-12T00:00:00" }, now)).toBe(7 * 86400);
    expect(cookieLifetimeSeconds({ expires_in: 43199 }, now)).toBe(43199);
    expect(cookieLifetimeSeconds({ refresh_expires_at: "2020-01-01T00:00:00" }, now)).toBe(7 * 86400);
    expect(cookieLifetimeSeconds(null, now)).toBe(7 * 86400);
  });

  it("login sets the cookie from expires_in and adds Secure only on https", async () => {
    fetchMock.mockImplementation(async () => json({ token: "t", refresh_token: "r", expires_in: 43199, user: { email: "a@b.in" } }));
    await login("a@b.in", "longenough1");
    expect(cookieWrites.at(-1)).toContain("Max-Age=43199");
    expect(cookieWrites.at(-1)).not.toContain("Secure");

    location.protocol = "https:";
    await login("a@b.in", "longenough1");
    expect(cookieWrites.at(-1)).toContain("; Secure");
  });

  it("is renewed when tokens are rotated", () => {
    saveTokens("a", "r", 1234);
    expect(cookieWrites.at(-1)).toContain("sd_session=1");
    expect(cookieWrites.at(-1)).toContain("Max-Age=1234");
  });
});
