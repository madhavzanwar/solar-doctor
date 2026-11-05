/** Thin fetch wrapper: bearer token, one-shot refresh on 401, normalised errors. */
import { ApiError, errorFromResponse, networkError } from "./errors";
import { clearSession, getAccessToken, getRefreshToken, saveTokens } from "./storage";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let refreshInFlight: Promise<string | null> | null = null;

interface TokenPayload {
  token?: string;
  access_token?: string;
  refresh_token?: string;
}

/** Accept either `token` (SolarDoctor backend) or `access_token` (OAuth style). */
export function pickAccessToken(data: TokenPayload | null | undefined): string | null {
  return data?.token ?? data?.access_token ?? null;
}

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as TokenPayload;
    const access = pickAccessToken(data);
    if (!access) return null;
    saveTokens(access, data.refresh_token);
    return access;
  } catch {
    return null;
  }
}

function refreshOnce(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
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

async function send(path: string, options: RequestInit, token: string | null): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, buildInit(options, token));
  } catch (cause) {
    throw networkError(API_URL, cause);
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface ApiFetchOptions extends RequestInit {
  /** Do not try to refresh or redirect on 401 (used by the login call itself). */
  skipAuthRetry?: boolean;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { skipAuthRetry, ...init } = options;
  let res = await send(path, init, getAccessToken());

  if (res.status === 401 && !skipAuthRetry && typeof window !== "undefined") {
    const fresh = await refreshOnce();
    if (fresh) {
      res = await send(path, init, fresh);
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
