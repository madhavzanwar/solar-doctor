import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { apiFetch } from "@/lib/api/http";
import { ACCESS_KEY, REFRESH_KEY, saveSession } from "@/lib/api/storage";
import { getCurrentUser, isLoggedIn, login, register } from "@/lib/api/auth";

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

  it("register signs in when the backend returns a token, otherwise reports false", async () => {
    fetchMock.mockResolvedValueOnce(json({ access_token: "t2", refresh_token: "r2" }));
    await expect(register({ email: "a@b.in", password: "longenough" })).resolves.toBe(true);
    expect(localStorage.getItem(ACCESS_KEY)).toBe("t2");

    localStorage.clear();
    fetchMock.mockResolvedValueOnce(json({ id: 5 }, 201));
    await expect(register({ email: "c@d.in", password: "longenough" })).resolves.toBe(false);
    expect(isLoggedIn()).toBe(false);
  });
});
