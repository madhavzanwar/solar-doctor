import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { apiFetch } from "@/lib/api/http";
import { ACCESS_KEY, REFRESH_KEY, saveSession } from "@/lib/api/storage";
import { getCurrentUser, isLoggedIn, login, logout, register } from "@/lib/api/auth";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;
let location: { href: string };

beforeEach(() => {
  localStorage.clear();
  document.cookie = "sd_session=; Max-Age=0; Path=/";
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  location = { href: "/dashboard" };
  Object.defineProperty(window, "location", { value: location, writable: true, configurable: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function authHeader(call: number): string | null {
  const init = fetchMock.mock.calls[call][1] as RequestInit;
  return new Headers(init.headers).get("Authorization");
}

describe("apiFetch", () => {
  it("attaches the bearer token and returns JSON", async () => {
    saveSession({ accessToken: "tok-1" });
    fetchMock.mockResolvedValueOnce(json([{ id: 1 }]));
    await expect(apiFetch("/api/v1/plants")).resolves.toEqual([{ id: 1 }]);
    expect(authHeader(0)).toBe("Bearer tok-1");
  });

  it("returns undefined for 204", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(apiFetch("/api/v1/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    saveSession({ accessToken: "old", refreshToken: "ref" });
    fetchMock
      .mockResolvedValueOnce(json({ detail: "expired" }, 401))
      .mockResolvedValueOnce(json({ token: "new", refresh_token: "ref2" }))
      .mockResolvedValueOnce(json({ ok: true }));
    await expect(apiFetch("/api/v1/alerts")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/refresh");
    expect(authHeader(2)).toBe("Bearer new");
    expect(localStorage.getItem(ACCESS_KEY)).toBe("new");
    expect(localStorage.getItem(REFRESH_KEY)).toBe("ref2");
  });

  it("shares one refresh between concurrent 401s", async () => {
    saveSession({ accessToken: "old", refreshToken: "ref" });
    let refreshCalls = 0;
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (String(url).includes("/auth/refresh")) {
        refreshCalls += 1;
        return json({ access_token: "new" });
      }
      const bearer = new Headers(init.headers).get("Authorization");
      return bearer === "Bearer new" ? json({ ok: true }) : json({ detail: "expired" }, 401);
    });
    await Promise.all([apiFetch("/api/v1/a"), apiFetch("/api/v1/b")]);
    expect(refreshCalls).toBe(1);
  });

  it("clears the session and redirects to /login when refresh fails", async () => {
    saveSession({ accessToken: "old", refreshToken: "ref" });
    fetchMock
      .mockResolvedValueOnce(json({ detail: "expired" }, 401))
      .mockResolvedValueOnce(json({ detail: "bad refresh" }, 401));
    await expect(apiFetch("/api/v1/alerts")).rejects.toMatchObject({ status: 401 });
    expect(isLoggedIn()).toBe(false);
    expect(location.href).toBe("/login");
  });

  it("normalises network failures", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const err = (await apiFetch("/api/v1/plants").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/Could not reach the SolarDoctor API/);
  });

  it("surfaces server error detail", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Plant not found" }, 404));
    await expect(apiFetch("/api/v1/plants/9")).rejects.toThrow("Plant not found");
  });
});

describe("login / register", () => {
  it("login posts email + password, stores tokens and sets the presence cookie", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ token: "t", refresh_token: "r", expires_at: "2099-01-01T00:00:00Z", user: { email: "a@b.in" } }),
    );
    await login("  a@b.in ", "secret-pass");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/auth/login");
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@b.in", password: "secret-pass" });
    expect(localStorage.getItem(ACCESS_KEY)).toBe("t");
    expect(localStorage.getItem(REFRESH_KEY)).toBe("r");
    expect(getCurrentUser()).toBe("a@b.in");
    expect(document.cookie).toContain("sd_session=1");
  });

  it("login does not try to refresh on 401 and reports the server message", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Invalid email or password" }, 401));
    await expect(login("a@b.in", "nope")).rejects.toThrow("Invalid email or password");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(isLoggedIn()).toBe(false);
  });

  it("register posts, then logs in with the same credentials", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ email: "a@b.in", role: "viewer", status: "registered" }, 201))
      .mockResolvedValueOnce(json({ token: "t2", access_token: "t2", refresh_token: "r2" }));
    await expect(register({ email: " a@b.in", password: "longenough1", full_name: "A" })).resolves.toBe("signed-in");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/auth/register");
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/login");
    expect(JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string)).toEqual({
      email: "a@b.in",
      password: "longenough1",
    });
    expect(localStorage.getItem(ACCESS_KEY)).toBe("t2");
  });

  it("register reports login-required when the follow-up login is 401 (duplicate email, other password)", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ email: "a@b.in", role: "viewer", status: "registered" }, 201))
      .mockResolvedValueOnce(json({ detail: "Invalid email or password" }, 401));
    await expect(register({ email: "a@b.in", password: "longenough1" })).resolves.toBe("login-required");
    expect(isLoggedIn()).toBe(false);
  });

  it("register surfaces a 400 weak-password message and does not try to log in", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Password must be 10-256 characters" }, 400));
    await expect(register({ email: "a@b.in", password: "short" })).rejects.toThrow("Password must be 10-256 characters");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("turns 429 into a readable message using Retry-After", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Too many login attempts. Try again later." }), {
        status: 429,
        headers: { "Retry-After": "600" },
      }),
    );
    const err = (await login("a@b.in", "longenough1").catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(429);
    expect(err.retryAfterSeconds).toBe(600);
    expect(err.message).toBe("Too many attempts. Please try again in about 10 minutes.");
  });

  it("rotating refresh: stores the new refresh token and uses it next time, never the old one", async () => {
    saveSession({ accessToken: "a0", refreshToken: "r0" });
    const sent: string[] = [];
    let n = 0;
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (String(url).includes("/auth/refresh")) {
        sent.push(JSON.parse(init.body as string).refresh_token);
        n += 1;
        return json({ token: `a${n}`, refresh_token: `r${n}` });
      }
      const bearer = new Headers(init.headers).get("Authorization");
      return bearer === `Bearer a${n}` && n > 0 ? json({ ok: true }) : json({ detail: "expired" }, 401);
    });
    await apiFetch("/api/v1/x");
    expect(localStorage.getItem(REFRESH_KEY)).toBe("r1");
    await apiFetch("/api/v1/y"); // a1 is current, so no refresh needed
    saveSession({ accessToken: "stale", refreshToken: localStorage.getItem(REFRESH_KEY) });
    await apiFetch("/api/v1/z");
    expect(sent).toEqual(["r0", "r1"]);
  });

  it("logout posts the bearer token and the refresh token, then clears local state", async () => {
    saveSession({ accessToken: "a", refreshToken: "r" });
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await logout();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/auth/logout");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer a");
    expect(JSON.parse(init.body as string)).toEqual({ refresh_token: "r" });
    expect(isLoggedIn()).toBe(false);
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(location.href).toBe("/login");
  });

  it("logout still clears local state when the server call fails", async () => {
    saveSession({ accessToken: "a", refreshToken: "r" });
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await logout();
    expect(isLoggedIn()).toBe(false);
  });
});
