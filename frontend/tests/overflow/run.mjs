#!/usr/bin/env node
/**
 * Layout stress check: every dashboard route at 390x844 (and 1440x900) with deliberately awkward data
 * (many plants, very long names and locations, long unbroken alert text, wide numbers). Asserts that the page
 * itself never scrolls horizontally (document scrollWidth <= innerWidth); tables and charts may scroll inside
 * their own wrappers. Exits non-zero on any failure and writes docs/solardoctor/qa/overflow/results.md.
 * Usage: node tests/overflow/run.mjs [--no-build]
 */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import * as fx from "../fixtures/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, "../..");
const outDir = join(resolve(frontend, ".."), "docs/solardoctor/qa/overflow");
const PORT = Number(process.env.OVERFLOW_PORT ?? 3300);
const API = "http://localhost:8000";
const BASE = `http://localhost:${PORT}`;
const DIST = ".next-overflow";
const noBuild = process.argv.includes("--no-build");

const LONG = "Pavagada Ultra Mega Solar Park Phase Two Block Seventeen Extension Rooftop Annex";
const stressPlants = Array.from({ length: 14 }, (_, i) => ({
  ...fx.plants[i % 3],
  id: i + 1,
  name: `${LONG} ${i + 1}`,
  location: `${LONG}, Tumakuru District, Karnataka, India ${"X".repeat(40)}`,
  capacity_kw: 123456789.5 + i,
  inverter_capacity_kw: 98765432.1,
  module_count: 1234567890,
  source: "SIMULATED",
}));
const stressAlerts = Array.from({ length: 8 }, (_, i) => ({
  ...fx.alerts[i % 3],
  id: i + 1,
  plant_id: (i % 14) + 1,
  message: `${"Unbrokenstringwithnospacesatalllongerthanthescreen".repeat(3)} ${LONG}`,
  is_resolved: false,
  source: "SIMULATED",
}));
const longWeather = { ...fx.weather, location_name: LONG, source: "mock" };

const overrides = [
  ["GET", /^\/api\/v1\/plants$/, () => stressPlants],
  ["GET", /^\/api\/v1\/plants\/(\d+)$/, (m) => stressPlants.find((p) => p.id === Number(m[1])) ?? stressPlants[0]],
  ["GET", /^\/api\/v1\/alerts$/, () => stressAlerts],
  ["GET", /^\/api\/v1\/weather\/\d+\/(current|forecast)$/, () => longWeather],
];
const routes = [...overrides, ...fx.routes];

const PAGES = [
  "/dashboard",
  "/dashboard/plants",
  "/dashboard/plants/new",
  "/dashboard/plants/1",
  "/dashboard/performance",
  "/dashboard/inspections",
  "/dashboard/alerts",
  "/dashboard/work-orders",
  "/dashboard/roi",
  "/dashboard/map",
  "/dashboard/reports",
  "/dashboard/settings",
];
const VIEWPORTS = [
  ["mobile", { width: 390, height: 844 }],
  ["desktop", { width: 1440, height: 900 }],
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
      env: { ...process.env, NEXT_DIST_DIR: DIST, NEXT_PUBLIC_API_URL: API },
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
    for (const path of PAGES) {
      for (const [vp, viewport] of VIEWPORTS) {
        const ctx = await browser.newContext({ viewport, locale: "en-US", timezoneId: "UTC", reducedMotion: "reduce" });
        await ctx.route(`${API}/**`, (route) => {
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
        await ctx.addCookies([{ name: "sd_session", value: "1", url: BASE }]);
        await ctx.addInitScript(
          ([a, r, u]) => {
            localStorage.setItem("solardoctor_access_token", a);
            localStorage.setItem("solardoctor_refresh_token", r);
            localStorage.setItem("solardoctor_user", u);
          },
          [fx.loginResponse.token, fx.loginResponse.refresh_token, fx.loginResponse.user.email],
        );
        const page = await ctx.newPage();
        const cspErrors = [];
        page.on("console", (msg) => {
          if (/content security policy/i.test(msg.text())) cspErrors.push(msg.text().slice(0, 160));
        });
        await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
        await page.waitForTimeout(500);
        const m = await page.evaluate(() => {
          const docW = document.documentElement.scrollWidth;
          const offenders = [];
          for (const el of document.querySelectorAll("body *")) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.right > window.innerWidth + 1) {
              // Ignore anything inside an element that scrolls on its own
              let p = el.parentElement;
              let contained = false;
              while (p && p !== document.body) {
                const ox = getComputedStyle(p).overflowX;
                if ((ox === "auto" || ox === "scroll" || ox === "hidden") && p.getBoundingClientRect().right <= window.innerWidth + 1) {
                  contained = true;
                  break;
                }
                p = p.parentElement;
              }
              if (!contained) offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
            }
          }
          return { docW, innerW: window.innerWidth, offenders: [...new Set(offenders)].slice(0, 5) };
        });
        const ok = m.docW <= m.innerW && cspErrors.length === 0;
        if (cspErrors.length) m.offenders.push(`CSP: ${cspErrors[0]}`);
        rows.push({ path, vp, ...m, ok });
        console.log(`${ok ? "PASS" : "FAIL"} ${vp} ${path}: scrollWidth ${m.docW} / innerWidth ${m.innerW}${ok ? "" : " offenders " + m.offenders.join(", ")}`);
        await ctx.close();
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
  const failed = rows.filter((r) => !r.ok);
  writeFileSync(
    join(outDir, "results.md"),
    [
      "# Horizontal overflow check (stress data)",
      "",
      "Generated by `npm run test:overflow`. 14 plants with very long names/locations and huge numbers, long unbroken alert text, long weather location. Assertions: `document.documentElement.scrollWidth <= window.innerWidth`, and no Content-Security-Policy violation in the console.",
      "",
      `Result: ${rows.length - failed.length} of ${rows.length} page views pass.`,
      "",
      "| Route | Viewport | scrollWidth | innerWidth | Result |",
      "|---|---|---|---|---|",
      ...rows.map((r) => `| ${r.path} | ${r.vp} | ${r.docW} | ${r.innerW} | ${r.ok ? "pass" : "FAIL " + r.offenders.join(", ")} |`),
    ].join("\n") + "\n",
  );
  return failed.length;
}

main()
  .then((failed) => process.exit(failed ? 1 : 0))
  .catch((e) => {
    console.error(e);
    process.exit(1);
  });
