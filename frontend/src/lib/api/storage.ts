/**
 * Token storage. Tokens live in localStorage (read by the fetch wrapper). A separate presence cookie lets the
 * Next.js middleware redirect unauthenticated page requests before any client code runs; it carries no secret and
 * the backend still authorises every API call.
 */
import { SESSION_COOKIE } from "../auth-guard";

export const ACCESS_KEY = "solardoctor_access_token";
export const REFRESH_KEY = "solardoctor_refresh_token";
export const USER_KEY = "solardoctor_user";

function ls(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return ls()?.getItem(ACCESS_KEY) ?? null;
}

export function getRefreshToken(): string | null {
  return ls()?.getItem(REFRESH_KEY) ?? null;
}

export function getStoredUser(): string | null {
  return ls()?.getItem(USER_KEY) ?? null;
}

function setSessionCookie(maxAgeSeconds: number): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}; SameSite=Lax`;
}

export interface SessionInput {
  accessToken: string;
  refreshToken?: string | null;
  user?: string | null;
  /** Seconds until the session expires; defaults to 7 days. */
  expiresInSeconds?: number;
}

export function saveSession(s: SessionInput): void {
  const store = ls();
  if (store) {
    store.setItem(ACCESS_KEY, s.accessToken);
    if (s.refreshToken) store.setItem(REFRESH_KEY, s.refreshToken);
    if (s.user) store.setItem(USER_KEY, s.user);
  }
  setSessionCookie(s.expiresInSeconds ?? 7 * 24 * 3600);
}

export function saveTokens(accessToken: string, refreshToken?: string | null): void {
  const store = ls();
  if (store) {
    store.setItem(ACCESS_KEY, accessToken);
    if (refreshToken) store.setItem(REFRESH_KEY, refreshToken);
  }
}

export function clearSession(): void {
  const store = ls();
  if (store) {
    store.removeItem(ACCESS_KEY);
    store.removeItem(REFRESH_KEY);
    store.removeItem(USER_KEY);
  }
  setSessionCookie(0);
}
