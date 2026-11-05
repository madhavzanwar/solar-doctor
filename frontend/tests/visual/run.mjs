#!/usr/bin/env node
/**
 * Visual acceptance harness (DESIGN.md, prompt 01 Phase D.8).
 *
 * Builds the app with NEXT_PUBLIC_FONT_MODE=clone into .next-visual, serves it, mocks every API call with the
 * fixtures in tests/fixtures (Playwright route interception), screenshots each route full-page at 1440x900 and
 * 390x844, and compares with docs/solardoctor/design/reference/*.webp using pixelmatch.
 * Output: docs/solardoctor/qa/visual/{<name>.actual.png,<name>.diff.png,results.json,results.md}
 *
 * PASS/FAIL GATE (thresholds are fixed here and in README.md; they are not tuned after seeing results):
 *   - dashboard and auth routes (login, register, overview, plants, plant-new, plant-detail, alerts, performance):
 *     full-canvas pixelmatch ratio <= APP_MAX (2.0 %), desktop and mobile wherever a reference image exists.
 *     Full canvas counts a page-height mismatch as differing pixels (padded magenta), so it is the strict metric.
 *   - landing (new hero photo, new copy, so it can never match unmasked): compared with MASKS applied to both images,
 *     ratio <= LANDING_MAX (3.0 %). Masking rule: from the rendered page, every rectangle (+2 px) of (a) the hero
 *     <section>, i.e. the photo plus its scrim and headline, (b) every <img>/<picture>, and (c) every element that
 *     directly contains non-empty text (h1-h4, p, li, a, button, label, span, td, th, ...) is painted flat grey in
 *     BOTH the screenshot and the reference at identical coordinates. The ratio is differing pixels divided by
 *     the UNMASKED pixels of the region both images cover (page-height difference from new copy is not gated).
 *   - routes with no reference image (mobile login/register/plant-new/plants/alerts/performance) are screenshot-only.
 * Exit code 1 if any gated row fails.
 *
 * Usage: node tests/visual/run.mjs [--no-build] [--only=<name-substring>]
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

/** Preset acceptance thresholds. Do not change after looking at a result; fix the UI instead. */
const APP_MAX = 0.02;
const LANDING_MAX = 0.03;

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
  let masks = [];
  if (page.name === "landing") {
    masks = await p.evaluate(() => {
      const out = [];
      const sy = window.scrollY;
      const sx = window.scrollX;
      const add = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) out.push([r.left + sx - 2, r.top + sy - 2, r.right + sx + 2, r.bottom + sy + 2]);
      };
      const hero = document.querySelector("main section");
      if (hero) add(hero);
      document.querySelectorAll("img, picture, svg").forEach(add);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const seen = new Set();
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim()) continue;
        const el = n.parentElement;
        if (!el || seen.has(el) || ["SCRIPT", "STYLE", "NOSCRIPT"].includes(el.tagName)) continue;
        seen.add(el);
        add(el);
      }
      return out;
    });
  }
  await context.close();
  return { buf, masks };
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

/** Paint rectangles flat grey (in place) and return a per-pixel "masked" bitmap for the image's own size. */
function applyMasks(img, masks) {
  const flag = new Uint8Array(img.width * img.height);
  for (const [x0, y0, x1, y1] of masks) {
    const xa = Math.max(0, Math.floor(x0));
    const ya = Math.max(0, Math.floor(y0));
    const xb = Math.min(img.width, Math.ceil(x1));
    const yb = Math.min(img.height, Math.ceil(y1));
    for (let y = ya; y < yb; y++) {
      for (let x = xa; x < xb; x++) {
        const i = y * img.width + x;
        flag[i] = 1;
        img.data[i * 4] = 128;
        img.data[i * 4 + 1] = 128;
        img.data[i * 4 + 2] = 128;
        img.data[i * 4 + 3] = 255;
      }
    }
  }
  return flag;
}

async function compare(actualBuf, refPath, stem, masks = []) {
  const a = await decode(actualBuf);
  const r = await decode(refPath);
  let maskedRatioCommon = null;
  if (masks.length) {
    const ua = await decode(actualBuf);
    const ur = await decode(refPath);
    // unmasked (raw) numbers for information
    const cw0 = Math.min(ua.width, ur.width);
    const ch0 = Math.min(ua.height, ur.height);
    const crop0 = (img) => {
      const out = Buffer.alloc(cw0 * ch0 * 4);
      for (let y = 0; y < ch0; y++) img.data.copy(out, y * cw0 * 4, y * img.width * 4, (y * img.width + cw0) * 4);
      return out;
    };
    const rawCommon = pixelmatch(crop0(ua), crop0(ur), null, cw0, ch0, { threshold: 0.1 });
    // masked: same rectangles painted in both
    applyMasks(a, masks);
    applyMasks(r, masks);
    const crop = (img) => {
      const out = Buffer.alloc(cw0 * ch0 * 4);
      for (let y = 0; y < ch0; y++) img.data.copy(out, y * cw0 * 4, y * img.width * 4, (y * img.width + cw0) * 4);
      return out;
    };
    const ca = crop(a);
    const cr = crop(r);
    const flag = new Uint8Array(cw0 * ch0);
    for (const [x0, y0, x1, y1] of masks) {
      for (let y = Math.max(0, Math.floor(y0)); y < Math.min(ch0, Math.ceil(y1)); y++)
        for (let x = Math.max(0, Math.floor(x0)); x < Math.min(cw0, Math.ceil(x1)); x++) flag[y * cw0 + x] = 1;
    }
    let unmasked = 0;
    for (let i = 0; i < flag.length; i++) if (!flag[i]) unmasked++;
    const diffMasked = new PNG({ width: cw0, height: ch0 });
    const mm = pixelmatch(ca, cr, diffMasked.data, cw0, ch0, { threshold: 0.1 });
    writeFileSync(join(outDir, `${stem}.diff.png`), PNG.sync.write(diffMasked));
    maskedRatioCommon = mm / unmasked;
    return {
      actual: `${a.width}x${a.height}`,
      referenceSize: `${r.width}x${r.height}`,
      diffRatioFullCanvas: null,
      diffRatioCommonRegion: rawCommon / (cw0 * ch0),
      diffRatioMasked: maskedRatioCommon,
      maskedShare: 1 - unmasked / (cw0 * ch0),
    };
  }
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
        const { buf, masks } = await shoot(browser, page, viewport);
        writeFileSync(join(outDir, `${stem}.actual.png`), buf);
        if (!refStem) {
          results.push({ name: stem, route: page.path, viewport: `${viewport.width}x${viewport.height}`, reference: null });
          continue;
        }
        const cmp = await compare(buf, join(refDir, `${refStem}.webp`), stem, masks);
        const landing = page.name === "landing";
        const metric = landing ? cmp.diffRatioMasked : cmp.diffRatioFullCanvas;
        const limit = landing ? LANDING_MAX : APP_MAX;
        results.push({
          name: stem,
          route: page.path,
          viewport: `${viewport.width}x${viewport.height}`,
          reference: `${refStem}.webp`,
          gate: landing ? "masked <= 3.0%" : "full canvas <= 2.0%",
          gated: metric,
          limit,
          pass: metric <= limit,
          ...cmp,
        });
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
  const pct = (v) => `${(v * 100).toFixed(2)}%`;
  const lines = [
    "# Visual diff vs SolarPulseAI references",
    "",
    "Generated by `npm run test:visual` (frontend/tests/visual/run.mjs), font mode `clone`, fixtures from frontend/tests/fixtures. pixelmatch threshold 0.1.",
    "",
    "Gate (preset, not tuned): dashboard/auth routes full-canvas diff <= 2.0 %; landing masked diff <= 3.0 %.",
    "Landing masking: hero `<section>`, every img/picture/svg and every text-bearing element (+2 px) are painted flat grey in both images at the same coordinates; ratio = differing / unmasked pixels of the common region.",
    "Rows without a reference image are screenshot-only (not gated).",
    "",
    "| Screenshot | Route | Actual | Reference | Gate metric | Value | Limit | Result | Raw common-region diff | Raw full-canvas diff |",
    "|---|---|---|---|---|---|---|---|---|---|",
    ...results.map((r) =>
      r.reference
        ? `| ${r.name} | ${r.route} | ${r.actual} | ${r.reference} (${r.referenceSize}) | ${r.gate} | ${pct(r.gated)} | ${pct(r.limit)} | ${r.pass ? "PASS" : "FAIL"} | ${pct(r.diffRatioCommonRegion)} | ${r.diffRatioFullCanvas == null ? "n/a" : pct(r.diffRatioFullCanvas)} |`
        : `| ${r.name} | ${r.route} | ${r.viewport} | no reference | screenshot only | n/a | n/a | n/a | n/a | n/a |`,
    ),
  ];
  writeFileSync(join(outDir, "results.md"), lines.join("\n") + "\n");
  console.table(
    results.map((r) => ({
      name: r.name,
      ref: r.reference,
      gate: r.reference ? r.gate : "screenshot only",
      value: r.reference ? pct(r.gated) : "-",
      result: r.reference ? (r.pass ? "PASS" : "FAIL") : "-",
    })),
  );
  const failed = results.filter((r) => r.reference && !r.pass);
  if (failed.length) {
    console.error(`VISUAL GATE FAILED: ${failed.map((r) => `${r.name} ${pct(r.gated)} > ${pct(r.limit)}`).join("; ")}`);
    process.exit(1);
  }
  console.log(`VISUAL GATE PASSED (${results.filter((r) => r.reference).length} gated rows)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
