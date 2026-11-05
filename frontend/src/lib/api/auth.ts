import type { components } from "./schema";
import { ApiError } from "./errors";
import { apiFetch, pickAccessToken } from "./http";
import { clearSession, getAccessToken, getRefreshToken, getStoredUser, saveSession } from "./storage";

export type UserLoginBody = components["schemas"]["UserLogin"];

/** Contract in docs/solardoctor/API_AUTH.md: `username`/`full_name` are accepted and ignored by the backend. */
export type UserRegisterBody = components["schemas"]["UserRegister"];
export interface RegisterBody extends UserRegisterBody {
  email: string;
  password: string;
  full_name?: string;
}

/** Token body of login, token and refresh (API_AUTH.md). `token` and `access_token` are the same value. */
export interface AuthResponse {
  token?: string;
  access_token?: string;
  refresh_token?: string;
  expires_at?: string;
  user?: { email?: string; role?: string } | null;
}

function secondsUntil(iso: string | undefined): number | undefined {
  if (!iso) return undefined;
  const ms = Date.parse(iso) - Date.now();
  return Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : undefined;
}

function persist(data: AuthResponse, fallbackUser: string): void {
  const access = pickAccessToken(data);
  if (!access) throw new Error("The server did not return a session token.");
  saveSession({
    accessToken: access,
    refreshToken: data.refresh_token,
    user: data.user?.email ?? fallbackUser,
    expiresInSeconds: secondsUntil(data.expires_at),
  });
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const body: UserLoginBody = { email: email.trim(), password };
  const data = await apiFetch<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
    skipAuthRetry: true,
  });
  persist(data, email.trim());
  return data;
}

/**
 * Registers, then signs in with the same credentials. The backend answers 201 with no token, and the same
 * response for an already-registered email (no account enumeration), so the follow-up login is what tells the
 * caller whether this password works for the account. A 401 from that login is reported as "login-required".
 */
export async function register(body: RegisterBody): Promise<"signed-in" | "login-required"> {
  await apiFetch<{ status?: string }>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ ...body, email: body.email.trim() }),
    skipAuthRetry: true,
  });
  try {
    await login(body.email, body.password);
    return "signed-in";
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return "login-required";
    throw err;
  }
}

export function me() {
  return apiFetch<{ role?: string; user?: { email?: string } | null }>("/api/v1/auth/me");
}

/** Revoke the access session and the refresh family on the server (best effort), clear local state, go to /login. */
export async function logout(): Promise<void> {
  try {
    const refreshToken = getRefreshToken();
    const logoutBody: components["schemas"]["LogoutRequest"] = refreshToken ? { refresh_token: refreshToken } : {};
    if (getAccessToken() || refreshToken) {
      await apiFetch<void>("/api/v1/auth/logout", {
        method: "POST",
        body: JSON.stringify(logoutBody),
        skipAuthRetry: true,
      });
    }
  } catch {
    // The local session is cleared regardless.
  }
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/login";
}

export function isLoggedIn(): boolean {
  return !!getAccessToken();
}

export function getCurrentUser(): string | null {
  return getStoredUser();
}
