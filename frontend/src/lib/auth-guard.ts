/**
 * Pure helpers for the Next.js middleware (src/middleware.ts). Kept free of Next imports so Vitest can test them.
 * The cookie is only a presence flag for redirects; the API enforces real authorisation.
 */
export const SESSION_COOKIE = "sd_session";

export const PROTECTED_PREFIX = "/dashboard";

export function isProtectedPath(pathname: string): boolean {
  return pathname === PROTECTED_PREFIX || pathname.startsWith(`${PROTECTED_PREFIX}/`);
}

/** Only same-origin relative paths are allowed as post-login targets (no open redirects). */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return PROTECTED_PREFIX;
  }
  return next;
}

export type GuardDecision =
  | { action: "next" }
  | { action: "redirect"; location: string };

export function guardDecision(pathname: string, search: string, hasSession: boolean): GuardDecision {
  if (isProtectedPath(pathname) && !hasSession) {
    const next = encodeURIComponent(`${pathname}${search}`);
    return { action: "redirect", location: `/login?next=${next}` };
  }
  return { action: "next" };
}
