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

const DEFAULT_LIFETIME_S = 7 * 24 * 3600;

function setSessionCookie(maxAgeSeconds: number): void {
  if (typeof document === "undefined") return;
  const secure = typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${SESSION_COOKIE}=1; Path=/; Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}; SameSite=Lax${secure}`;
}

/** The backend sends naive UTC timestamps ("2026-11-05T21:27:59.6"); a missing zone means UTC, not local time. */
export function parseUtc(iso: string): number {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  return Date.parse(hasZone ? iso : `${iso}Z`);
}

export interface TokenLifetimeFields {
  expires_in?: number;
  refresh_expires_at?: string;
}

/**
 * How long the presence cookie should live. The middleware only checks the cookie, and a page load is what
 * triggers a refresh, so the cookie must outlive the access token for as long as the refresh token is good:
 * use the refresh token's remaining life (UTC-parsed), else `expires_in`, else 7 days.
 */
export function cookieLifetimeSeconds(body: TokenLifetimeFields | null | undefined, now = Date.now()): number {
  if (body?.refresh_expires_at) {
    const secs = Math.floor((parseUtc(body.refresh_expires_at) - now) / 1000);
    if (Number.isFinite(secs) && secs > 0) return secs;
  }
  if (typeof body?.expires_in === "number" && body.expires_in > 0) return body.expires_in;
  return DEFAULT_LIFETIME_S;
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
  setSessionCookie(s.expiresInSeconds ?? DEFAULT_LIFETIME_S);
}

/** Store rotated tokens and renew the presence cookie. */
export function saveTokens(accessToken: string, refreshToken?: string | null, lifetimeSeconds?: number): void {
  const store = ls();
  if (store) {
    store.setItem(ACCESS_KEY, accessToken);
    if (refreshToken) store.setItem(REFRESH_KEY, refreshToken);
  }
  setSessionCookie(lifetimeSeconds ?? DEFAULT_LIFETIME_S);
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
