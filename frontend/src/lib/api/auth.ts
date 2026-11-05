import type { components } from "./schema";
import { apiFetch, pickAccessToken } from "./http";
import { clearSession, getAccessToken, getStoredUser, saveSession } from "./storage";

export type UserLoginBody = components["schemas"]["UserLogin"];

/** `/auth/register` is not in the schema yet (backend work in parallel); contract: email + password + full_name. */
export interface RegisterBody {
  email: string;
  password: string;
  full_name?: string;
}

/** Contract: opaque token + refresh token JSON. `user` mirrors the backend's serialised user. */
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

/** Registers and, when the backend returns a token, signs the user in. Returns true if signed in. */
export async function register(body: RegisterBody): Promise<boolean> {
  const data = await apiFetch<AuthResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ ...body, email: body.email.trim() }),
    skipAuthRetry: true,
  });
  if (pickAccessToken(data)) {
    persist(data, body.email.trim());
    return true;
  }
  return false;
}

export function me() {
  return apiFetch<{ role?: string; user?: { email?: string } | null }>("/api/v1/auth/me");
}

/** Revoke the server session (best effort), clear local state, go to /login. */
export async function logout(): Promise<void> {
  try {
    if (getAccessToken()) {
      await apiFetch<void>("/api/v1/auth/logout", { method: "POST", skipAuthRetry: true });
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
