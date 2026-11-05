import { describe, expect, it } from "vitest";
import nextConfig, { contentSecurityPolicy, securityHeaders } from "../../next.config";

const headers = Object.fromEntries(securityHeaders.map((h) => [h.key, h.value]));

describe("security headers", () => {
  it("applies to every route", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");
  });

  it("sets the standard hardening headers", () => {
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["Permissions-Policy"]).toContain("geolocation=()");
  });

  it("CSP forbids framing, plugins and remote scripts, and allows only self + the API for connections", () => {
    const csp = contentSecurityPolicy();
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    // next/font self-hosts fonts, so no font CDN is needed
    expect(csp).toContain("font-src 'self' data:");
    expect(csp).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
    expect(csp).not.toContain("unsplash");
    const script = csp.split("; ").find((d) => d.startsWith("script-src "))!;
    expect(script).not.toMatch(/https?:/);
    const connect = csp.split("; ").find((d) => d.startsWith("connect-src "))!;
    expect(connect).toContain("'self'");
    expect(connect).toContain("http://localhost:8000"); // default NEXT_PUBLIC_API_URL
  });
});
