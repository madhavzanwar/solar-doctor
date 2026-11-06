import type { NextConfig } from "next";

// Photos are self-hosted in public/images (credits in docs/IMAGE_CREDITS.md); no remote image hosts.
// NEXT_DIST_DIR lets the harnesses build into their own directories without clobbering the normal build.

const isProd = process.env.NODE_ENV === "production";

function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
}

/**
 * Content-Security-Policy. Fonts are self-hosted by next/font (same-origin woff2), photos are in /public, and the
 * only cross-origin call is the API. Next.js App Router injects small inline bootstrap scripts, so script-src
 * keeps 'unsafe-inline' (a nonce-based policy would need dynamic rendering for every page). Tokens live in
 * localStorage, so this policy is a real mitigation against injected scripts, not decoration: no remote script
 * hosts are allowed. When the Leaflet map ships, add its tile host to img-src.
 */
function contentSecurityPolicy(): string {
  const api = apiOrigin();
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", ...(isProd ? [] : ["'unsafe-eval'"])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    "connect-src": ["'self'", api, ...(isProd ? [] : ["ws:", "wss:"])],
    "media-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives)
    .map(([k, v]) => `${k} ${v.join(" ")}`)
    .join("; ");
}

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy() },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // camera is allowed for same-origin pages: the inspection upload offers phone camera capture
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
  ...(isProd ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // next/image serves AVIF when the browser accepts it, WebP otherwise
  images: { formats: ["image/avif", "image/webp"], qualities: [40, 75] },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export { contentSecurityPolicy, securityHeaders };
export default nextConfig;
