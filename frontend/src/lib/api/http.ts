/**
 * Thin fetch wrapper: bearer token, one-shot refresh on 401 or on a network failure of an authenticated call,
 * normalised errors.
 *
 * Why network failures trigger a refresh: when an error response carries no CORS headers (for example a 401 from
 * middleware that sits outside the CORS layer) the browser reports it as a network error, not as a 401. So with a
 * stored token, "status 0" is ambiguous: the API may be down, or the token may simply be expired. We resolve it by
 * trying one refresh, and, if that is also unreadable, by probing the public health endpoint.
 */
import type { components } from "./schema";
import { ApiError, errorFromResponse, networkError } from "./errors";
import { clearSession, cookieLifetimeSeconds, getAccessToken, getRefreshToken, saveTokens } from "./storage";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface TokenPayload {
  token?: string;
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  refresh_expires_at?: string;
}

/** Accept either `token` (SolarDoctor backend) or `access_token` (OAuth style). */
export function pickAccessToken(data: TokenPayload | null | undefined): string | null {
  return data?.token ?? data?.access_token ?? null;
}

export type RefreshOutcome =
  | { kind: "ok"; token: string }
  | { kind: "rejected" } // the server answered and said no (or there is no refresh token)
  | { kind: "unreadable" }; // network failure: no readable response

export async function refreshAccessToken(): Promise<RefreshOutcome> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return { kind: "rejected" };
  const refreshBody: components["schemas"]["RefreshRequest"] = { refresh_token: refreshToken };
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(refreshBody),
    });
    if (!res.ok) return { kind: "rejected" };
    const data = (await res.json()) as TokenPayload;
    const access = pickAccessToken(data);
    if (!access) return { kind: "rejected" };
    saveTokens(access, data.refresh_token, cookieLifetimeSeconds(data));
    return { kind: "ok", token: access };
  } catch {
    return { kind: "unreadable" };
  }
}

let refreshInFlight: Promise<RefreshOutcome> | null = null;

/** Concurrent callers share one refresh: refresh tokens are single use. */
function refreshOnce(): Promise<RefreshOutcome> {
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** True if the API answers at all. The health endpoint is public and carries CORS headers on success. */
export async function apiReachable(timeoutMs = 4000): Promise<boolean> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    await fetch(`${API_URL}/api/v1/health`, { signal: ctl.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function redirectToLogin(): void {
  clearSession();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

function buildInit(options: RequestInit, token: string | null): RequestInit {
  const headers = new Headers(options.headers);
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...options, headers };
}

/** Resolves with a Response, or null when the request failed at the network level. */
async function attempt(path: string, options: RequestInit, token: string | null): Promise<{ res: Response | null; cause?: unknown }> {
  try {
    return { res: await fetch(`${API_URL}${path}`, buildInit(options, token)) };
  } catch (cause) {
    return { res: null, cause };
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface ApiFetchOptions extends RequestInit {
  /** Do not try to refresh or redirect on 401 or network failure (used by the login call itself). */
  skipAuthRetry?: boolean;
}

function sessionExpired(): ApiError {
  return new ApiError(401, "Your session has expired. Please log in again.");
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { skipAuthRetry, ...init } = options;
  const token = getAccessToken();
  const first = await attempt(path, init, token);
  const canRecover = !skipAuthRetry && typeof window !== "undefined" && !!token;

  // Network-level failure
  if (!first.res) {
    if (!canRecover) throw networkError(API_URL, first.cause);
    const outcome = await refreshOnce();
    if (outcome.kind === "ok") {
      const retry = await attempt(path, init, outcome.token);
      if (!retry.res) throw networkError(API_URL, retry.cause);
      if (!retry.res.ok) throw await errorFromResponse(retry.res);
      return parse<T>(retry.res);
    }
    if (outcome.kind === "rejected") {
      redirectToLogin();
      throw sessionExpired();
    }
    // Refresh was unreadable too: genuinely unreachable, or an auth error the browser cannot read.
    if (await apiReachable()) {
      redirectToLogin();
      throw sessionExpired();
    }
    throw networkError(API_URL, first.cause);
  }

  let res = first.res;
  if (res.status === 401 && !skipAuthRetry && typeof window !== "undefined") {
    const outcome = await refreshOnce();
    if (outcome.kind === "ok") {
      const retry = await attempt(path, init, outcome.token);
      if (!retry.res) throw networkError(API_URL, retry.cause);
      res = retry.res;
      if (res.ok) return parse<T>(res);
    }
    if (res.status === 401) {
      redirectToLogin();
    }
  }

  if (!res.ok) throw await errorFromResponse(res);
  return parse<T>(res);
}

export { ApiError };
