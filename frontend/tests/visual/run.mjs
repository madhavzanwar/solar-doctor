#!/usr/bin/env node
/**
 * Visual acceptance harness (DESIGN.md, prompt 01 Phase D.8).
 *
 * Builds the app with NEXT_PUBLIC_FONT_MODE=clone into .next-visual, serves it, mocks every API call with the
 * fixtures in tests/fixtures (Playwright route interception), screenshots each route full-page at 1440x900 and
 * 390x844, and compares with docs/solardoctor/design/reference/*.webp using pixelmatch.
 * Output: docs/solardoctor/qa/visual/{<name>.actual.png,<name>.diff.png,results.json,results.md}
 *
 * Usage: node tests/visual/run.mjs [--no-build] [--only=<name-substring>]
 * The ratios are reported as measured. There is no pass/fail threshold baked in; see results.md.
 */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";
import { chromium } from "playwright";
import { loginResponse, routes } from "../fixtures/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, "../..");
const repo = resolve(frontend, "..");
const refDir = join(repo, "docs/solardoctor/design/reference");
const outDir = join(repo, "docs/solardoctor/qa/visual");
const PORT = Number(process.env.VISUAL_PORT ?? 3100);
const API = "http://localhost:8000";
const BASE = `http://localhost:${PORT}`;
const DIST = ".next-visual";

const args = process.argv.slice(2);
const noBuild = args.includes("--no-build");
const only = args.find((a) => a.startsWith("--only="))?.slice(7);

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

/** name, path, auth required, reference stems per viewport */
const PAGES = [
  { name: "landing", path: "/", auth: false, desk: "desk-landing", mob: "mob-landing" },
  { name: "login", path: "/login", auth: false, desk: "desk-login" },
  { name: "register", path: "/register", auth: false, desk: "desk-register" },
  { name: "overview", path: "/dashboard", auth: true, desk: "desk-overview", mob: "mob-overview" },
  { name: "plants", path: "/dashboard/plants", auth: true, desk: "desk-plants" },
  { name: "plant-new", path: "/dashboard/plants/new", auth: true, desk: "desk-plant-new" },
  { name: "plant-detail", path: "/dashboard/plants/2", auth: true, desk: "desk-plant-detail", mob: "mob-plant-detail" },
  { name: "alerts", path: "/dashboard/alerts", auth: true, desk: "desk-alerts" },
  { name: "performance", path: "/dashboard/performance", auth: true, desk: "desk-forecasts" },
];

mkdirSync(outDir, { recursive: true });

function build() {
  console.log("Building with NEXT_PUBLIC_FONT_MODE=clone ...");
  const r = spawnSync("npx", ["next", "build", "--turbopack"], {
    cwd: frontend,
    stdio: "inherit",
    env: { ...process.env, NEXT_PUBLIC_FONT_MODE: "clone", NEXT_DIST_DIR: DIST, NEXT_PUBLIC_API_URL: API },
  });
  if (r.status !== 0) throw new Error("next build failed");
}

async function startServer() {
  const proc = spawn("npx", ["next", "start", "-p", String(PORT)], {
    cwd: frontend,
    env: { ...process.env, NEXT_DIST_DIR: DIST },
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("next start timed out")), 60000);
    proc.stdout.on("data", (d) => {
      if (String(d).includes("Ready") || String(d).includes("started server")) {
        clearTimeout(t);
        res();
      }
    });
    proc.on("exit", (c) => rej(new Error(`next start exited ${c}`)));
  });
  return proc;
}

const CORS = {
  "access-control-allow-origin": BASE,
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
};

async function mockApi(context) {
  await context.route(`${API}/**`, (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const { pathname } = new URL(req.url());
    for (const [method, re, body] of routes) {
      const m = re.exec(pathname);
      if (m && method === req.method()) {
        return route.fulfill({
          status: 200,
          headers: { ...CORS, "content-type": "application/json" },
          body: JSON.stringify(body(m)),
        });
      }
    }
    console.warn(`  unmocked API call: ${req.method()} ${pathname}`);
    return route.fulfill({ status: 404, headers: { ...CORS, "content-type": "application/json" }, body: '{"detail":"not mocked"}' });
  });
}

async function shoot(browser, page, viewport) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    locale: "en-US",
    timezoneId: "UTC",
    reducedMotion: "reduce",
  });
  await mockApi(context);
  if (page.auth) {
    await context.addCookies([{ name: "sd_session", value: "1", url: BASE }]);
    await context.addInitScript(
      ([access, refresh, user]) => {
        localStorage.setItem("solardoctor_access_token", access);
        localStorage.setItem("solardoctor_refresh_token", refresh);
        localStorage.setItem("solardoctor_user", user);
      },
      [loginResponse.token, loginResponse.refresh_token, loginResponse.user.email],
    );
  }
  const p = await context.newPage();
  await p.goto(`${BASE}${page.path}`, { waitUntil: "networkidle" });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(600);
  const buf = await p.screenshot({ fullPage: true });
  await context.close();
  return buf;
}

async function decode(input) {
  const { data, info } = await sharp(input).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { data, width: info.width, height: info.height };
}

/** Pad both images to the same canvas (magenta) so size differences count as differing pixels. */
function padTo(img, w, h) {
  const out = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    out[i * 4] = 255;
    out[i * 4 + 1] = 0;
    out[i * 4 + 2] = 255;
    out[i * 4 + 3] = 255;
  }
  for (let y = 0; y < img.height; y++) {
    img.data.copy(out, y * w * 4, y * img.width * 4, (y * img.width + img.width) * 4);
  }
  return out;
}

async function compare(actualBuf, refPath, stem) {
  const a = await decode(actualBuf);
  const r = await decode(refPath);
  const w = Math.max(a.width, r.width);
  const h = Math.max(a.height, r.height);
  const diff = new PNG({ width: w, height: h });
  const mismatched = pixelmatch(padTo(a, w, h), padTo(r, w, h), diff.data, w, h, { threshold: 0.1 });
  writeFileSync(join(outDir, `${stem}.diff.png`), PNG.sync.write(diff));
  // Same-region ratio: only the area both images cover (ignores page-height differences)
  const cw = Math.min(a.width, r.width);
  const ch = Math.min(a.height, r.height);
  const crop = (img) => {
    const out = Buffer.alloc(cw * ch * 4);
    for (let y = 0; y < ch; y++) img.data.copy(out, y * cw * 4, y * img.width * 4, (y * img.width + cw) * 4);
    return out;
  };
  const common = pixelmatch(crop(a), crop(r), null, cw, ch, { threshold: 0.1 });
  return {
    actual: `${a.width}x${a.height}`,
    referenceSize: `${r.width}x${r.height}`,
    diffRatioFullCanvas: mismatched / (w * h),
    diffRatioCommonRegion: common / (cw * ch),
  };
}

async function main() {
  if (!noBuild) build();
  const server = await startServer();
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const results = [];
  try {
    for (const page of PAGES) {
      for (const [vpName, viewport] of [["desk", DESKTOP], ["mob", MOBILE]]) {
        const refStem = page[vpName];
        const stem = `${vpName}-${page.name}`;
        if (only && !stem.includes(only)) continue;
        console.log(`Rendering ${stem} (${page.path})`);
        const buf = await shoot(browser, page, viewport);
        writeFileSync(join(outDir, `${stem}.actual.png`), buf);
        if (!refStem) {
          results.push({ name: stem, route: page.path, viewport: `${viewport.width}x${viewport.height}`, reference: null });
          continue;
        }
        const cmp = await compare(buf, join(refDir, `${refStem}.webp`), stem);
        results.push({ name: stem, route: page.path, viewport: `${viewport.width}x${viewport.height}`, reference: `${refStem}.webp`, ...cmp });
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
  writeFileSync(join(outDir, "results.json"), JSON.stringify(results, null, 2));
  const pct = (v) => `${(v * 100).toFixed(1)}%`;
  const lines = [
    "# Visual diff vs SolarPulseAI references",
    "",
    "Generated by `npm run test:visual` (frontend/tests/visual/run.mjs), font mode `clone`, fixtures from frontend/tests/fixtures.",
    "pixelmatch threshold 0.1. `common region` ignores page-height differences; `full canvas` counts them (padded magenta).",
    "No acceptance threshold is applied by the script.",
    "",
    "| Screenshot | Route | Actual | Reference | Diff (common region) | Diff (full canvas) |",
    "|---|---|---|---|---|---|",
    ...results.map((r) =>
      r.reference
        ? `| ${r.name} | ${r.route} | ${r.actual} | ${r.reference} (${r.referenceSize}) | ${pct(r.diffRatioCommonRegion)} | ${pct(r.diffRatioFullCanvas)} |`
        : `| ${r.name} | ${r.route} | n/a | no reference | n/a | n/a |`,
    ),
  ];
  writeFileSync(join(outDir, "results.md"), lines.join("\n") + "\n");
  console.table(results.map((r) => ({ name: r.name, actual: r.actual, ref: r.reference, common: r.reference ? pct(r.diffRatioCommonRegion) : "-", full: r.reference ? pct(r.diffRatioFullCanvas) : "-" })));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
