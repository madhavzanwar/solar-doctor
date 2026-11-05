#!/usr/bin/env node
/**
 * Accessibility audit: axe-core (WCAG 2.0/2.1/2.2 A + AA rules) on every route at 1440x900 and 390x844, default
 * (non-clone) fonts, API mocked with tests/fixtures. Writes docs/solardoctor/qa/a11y/results.{json,md}.
 * Usage: node tests/a11y/run.mjs [--no-build]
 */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";
import { loginResponse, routes } from "../fixtures/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, "../..");
const outDir = join(resolve(frontend, ".."), "docs/solardoctor/qa/a11y");
const PORT = Number(process.env.A11Y_PORT ?? 3200);
const API = "http://localhost:8000";
const BASE = `http://localhost:${PORT}`;
const DIST = ".next-a11y";
const noBuild = process.argv.includes("--no-build");

const PAGES = [
  ["/", false],
  ["/login", false],
  ["/register", false],
  ["/dashboard", true],
  ["/dashboard/plants", true],
  ["/dashboard/plants/new", true],
  ["/dashboard/plants/2", true],
  ["/dashboard/alerts", true],
  ["/dashboard/performance", true],
  ["/dashboard/inspections", true],
  ["/dashboard/work-orders", true],
  ["/dashboard/roi", true],
  ["/dashboard/map", true],
  ["/dashboard/reports", true],
  ["/dashboard/settings", true],
];
const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
];

const CORS = {
  "access-control-allow-origin": BASE,
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
};

async function main() {
  mkdirSync(outDir, { recursive: true });
  if (!noBuild) {
    const r = spawnSync("npx", ["next", "build", "--turbopack"], {
      cwd: frontend,
      stdio: "inherit",
      env: { ...process.env, NEXT_DIST_DIR: DIST, NEXT_PUBLIC_API_URL: API, NEXT_PUBLIC_FONT_MODE: "" },
    });
    if (r.status !== 0) throw new Error("next build failed");
  }
  const server = spawn("npx", ["next", "start", "-p", String(PORT)], {
    cwd: frontend,
    env: { ...process.env, NEXT_DIST_DIR: DIST },
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("next start timed out")), 60000);
    server.stdout.on("data", (d) => {
      if (String(d).includes("Ready") || String(d).includes("started server")) {
        clearTimeout(t);
        res();
      }
    });
  });

  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const rows = [];
  try {
    for (const [path, auth] of PAGES) {
      for (const [vpName, viewport] of VIEWPORTS) {
        const context = await browser.newContext({ viewport, locale: "en-US", timezoneId: "UTC", reducedMotion: "reduce" });
        await context.route(`${API}/**`, (route) => {
          const req = route.request();
          if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
          const { pathname } = new URL(req.url());
          for (const [method, re, body] of routes) {
            const m = re.exec(pathname);
            if (m && method === req.method()) {
              return route.fulfill({ status: 200, headers: { ...CORS, "content-type": "application/json" }, body: JSON.stringify(body(m)) });
            }
          }
          return route.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/json" }, body: '{"detail":"not mocked"}' });
        });
        if (auth) {
          await context.addCookies([{ name: "sd_session", value: "1", url: BASE }]);
          await context.addInitScript(
            ([a, r, u]) => {
              localStorage.setItem("solardoctor_access_token", a);
              localStorage.setItem("solardoctor_refresh_token", r);
              localStorage.setItem("solardoctor_user", u);
            },
            [loginResponse.token, loginResponse.refresh_token, loginResponse.user.email],
          );
        }
        const page = await context.newPage();
        await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(500);
        const res = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .analyze();
        const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0 };
        for (const v of res.violations) byImpact[v.impact ?? "minor"] += 1;
        rows.push({
          route: path,
          viewport: vpName,
          ...byImpact,
          violations: res.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            nodes: v.nodes.length,
            targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
          })),
        });
        console.log(`${vpName} ${path}: critical=${byImpact.critical} serious=${byImpact.serious} moderate=${byImpact.moderate} minor=${byImpact.minor}`);
        await context.close();
      }
    }
  } finally {
    await browser.close();
    try {
      process.kill(-server.pid);
    } catch {
      // already gone
    }
  }
  writeFileSync(join(outDir, "results.json"), JSON.stringify(rows, null, 2));
  const total = (k) => rows.reduce((s, r) => s + r[k], 0);
  const md = [
    "# axe-core results",
    "",
    "Generated by `npm run test:a11y` (frontend/tests/a11y/run.mjs). Rules: WCAG 2.0/2.1/2.2 A and AA plus axe best-practice. Default fonts, API mocked with fixtures. axe finds only automatically detectable issues; it does not replace manual keyboard and screen-reader testing.",
    "",
    `Totals across ${rows.length} page views: critical ${total("critical")}, serious ${total("serious")}, moderate ${total("moderate")}, minor ${total("minor")}.`,
    "",
    "| Route | Viewport | Critical | Serious | Moderate | Minor |",
    "|---|---|---|---|---|---|",
    ...rows.map((r) => `| ${r.route} | ${r.viewport} | ${r.critical} | ${r.serious} | ${r.moderate} | ${r.minor} |`),
    "",
    "## Violations",
    "",
    ...rows.flatMap((r) =>
      r.violations.map((v) => `- ${r.viewport} ${r.route}: **${v.impact}** ${v.id} (${v.nodes} nodes) ${v.help}; e.g. ${v.targets.join(" | ")}`),
    ),
  ];
  writeFileSync(join(outDir, "results.md"), md.join("\n") + "\n");
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
  console.error(e);
  process.exit(1);
});
