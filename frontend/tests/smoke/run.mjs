#!/usr/bin/env node
/**
 * REAL smoke test (prompt 01 Phase D): drives a built frontend against a live, seeded API in a real browser.
 * No API mocking. Exits non-zero if ANY check fails (including an unreachable API or frontend).
 *
 * Required env:
 *   SMOKE_BASE_URL   frontend origin, e.g. http://localhost:3000        (next build && next start)
 *   SMOKE_API_URL    API origin the frontend was BUILT against (NEXT_PUBLIC_API_URL), e.g. http://localhost:8000
 *   SMOKE_EMAIL / SMOKE_PASSWORD   seeded admin (registered through the API first if the login is rejected with 401)
 * Optional: CHROMIUM_PATH (browser executable), SMOKE_PLANT_NAMES (comma list; default = the 3 seeded demo plants).
 *
 * Checks, per page: HTTP 2xx, key heading text, zero console errors, zero page errors, zero failed requests to the
 * API (4xx/5xx or network failure) except the one expected 404 (forecast summary "no forecasts yet", which the
 * client maps to null). The plants table must list the 3 seeded plants, each with the SIMULATED badge.
 * Finally: Sign out lands on /login and /dashboard then redirects back to /login.
 */
import { chromium } from "playwright";

const env = (k) => process.env[k]?.trim();
const missing = ["SMOKE_BASE_URL", "SMOKE_API_URL", "SMOKE_EMAIL", "SMOKE_PASSWORD"].filter((k) => !env(k));
if (missing.length) {
  console.error(`smoke: missing required env ${missing.join(", ")}`);
  process.exit(2);
}
const BASE = env("SMOKE_BASE_URL").replace(/\/$/, "");
const API = env("SMOKE_API_URL").replace(/\/$/, "");
const EMAIL = env("SMOKE_EMAIL");
const PASSWORD = env("SMOKE_PASSWORD");
const PLANTS = (env("SMOKE_PLANT_NAMES") ?? "Bhadla Block C,PCCoE Rooftop,Pavagada Unit 4").split(",").map((s) => s.trim());

/** Only API calls that may legitimately answer 404: forecast summary for a plant with no forecasts yet. */
const EXPECTED_404 = [/\/api\/v1\/forecast\/[^?]*summary/];
const isExpected404 = (url, status) => status === 404 && EXPECTED_404.some((re) => re.test(url));

const TRACKER_NAME = "SMOKE PVDAQ-style tracker";

const failures = [];
let passes = 0;
function check(name, ok, detail = "") {
  if (ok) {
    passes++;
    console.log(`  ok   ${name}`);
  } else {
    failures.push(`${name}${detail ? ` -- ${detail}` : ""}`);
    console.log(`  FAIL ${name}${detail ? ` -- ${detail}` : ""}`);
  }
}

async function apiJson(path, init) {
  const res = await fetch(`${API}${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  let body = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON body
  }
  return { status: res.status, body };
}

async function ensureAccountAndToken() {
  const creds = JSON.stringify({ email: EMAIL, password: PASSWORD });
  let r = await apiJson("/api/v1/auth/login", { method: "POST", body: creds });
  if (r.status === 401) {
    console.log("  seeded login rejected (401): registering the account first");
    const reg = await apiJson("/api/v1/auth/register", { method: "POST", body: creds });
    check("register account", reg.status >= 200 && reg.status < 300, `status ${reg.status}`);
    r = await apiJson("/api/v1/auth/login", { method: "POST", body: creds });
  }
  check("API login", r.status === 200 && !!(r.body?.access_token ?? r.body?.token), `status ${r.status}`);
  return r.body?.access_token ?? r.body?.token ?? null;
}

async function main() {
  console.log(`smoke: frontend ${BASE}  api ${API}  user ${EMAIL}`);
  const health = await apiJson("/api/v1/health").catch((e) => ({ status: 0, body: String(e) }));
  check("API reachable (/api/v1/health 200)", health.status === 200, `status ${health.status}`);
  const front = await fetch(`${BASE}/`).catch(() => null);
  check("frontend reachable", !!front && front.ok, front ? `status ${front.status}` : "no response");
  if (failures.length) return;

  const token = await ensureAccountAndToken();
  if (!token) return;
  const plantsRes = await apiJson("/api/v1/plants", { headers: { authorization: `Bearer ${token}` } });
  const apiPlants = Array.isArray(plantsRes.body) ? plantsRes.body : [];
  check("API lists plants", plantsRes.status === 200 && apiPlants.length > 0, `status ${plantsRes.status}, ${apiPlants.length} plants`);
  if (!apiPlants.length) return;
  const firstId = apiPlants[0].id;

  // The PVDAQ-style tracker plant is created by `python scripts/seed_smoke_tracker.py` (the API refuses the marker on
  // purpose: only the importer/seed may set it). The smoke test fails, not skips, when it is missing.
  const trackerPlant = apiPlants.find((p) => p.name === TRACKER_NAME);
  check("tracker fixture plant present (run scripts/seed_smoke_tracker.py)", Boolean(trackerPlant), "missing");
  if (!trackerPlant?.id) return;
  const trackerId = trackerPlant.id;

  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  let current = "(start)";
  let apiSeen = 0;
  const consoleErrors = [];
  const pageErrors = [];
  const badRequests = [];
  const expected404Urls = new Set();
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const url = m.location()?.url ?? "";
    // Chromium logs "Failed to load resource" for the expected 404 on its own; that one is allowed.
    if (/Failed to load resource/.test(m.text()) && expected404Urls.has(url)) return;
    consoleErrors.push(`[${current}] ${m.text()} ${url}`);
  });
  page.on("pageerror", (e) => pageErrors.push(`[${current}] ${e.message}`));
  page.on("requestfailed", async (r) => {
    if (!r.url().startsWith(API)) return;
    // Navigating right after a bodiless 204 (logout) makes Chromium report ERR_ABORTED although the server answered
    // 2xx. A request that got a successful response is not a failure; one with no response (or 4xx/5xx) is.
    const got = await r.response().catch(() => null);
    if (got && got.status() < 400) return;
    {
      badRequests.push(`[${current}] ${r.method()} ${r.url()} failed: ${r.failure()?.errorText}`);
    }
  });
  page.on("response", (r) => {
    if (!r.url().startsWith(API)) return;
    apiSeen++;
    const s = r.status();
    if (s < 400) return;
    if (isExpected404(r.url(), s)) {
      expected404Urls.add(r.url());
      return;
    }
    badRequests.push(`[${current}] ${r.request().method()} ${r.url()} -> ${s}`);
  });

  async function visit(path, heading, { expectUrl } = {}) {
    current = path;
    console.log(`page ${path}`);
    const res = await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    check(`${path} HTTP ok`, !!res && res.ok(), `status ${res?.status()}`);
    if (expectUrl) check(`${path} ends at ${expectUrl}`, new URL(page.url()).pathname === expectUrl, page.url());
    const h = page.locator("h1").first();
    let text = "";
    try {
      await h.waitFor({ timeout: 10000 });
      text = (await h.innerText()).replace(/\s+/g, " ");
    } catch {
      // reported below
    }
    check(`${path} heading matches ${heading}`, heading.test(text), `h1 was "${text}"`);
  }

  try {
    // Logged out
    await visit("/", /solardoctor/i);
    await visit("/login", /^log in$/i);
    await visit("/dashboard", /^log in$/i, { expectUrl: "/login" });

    // Log in through the real form
    current = "/login (submit)";
    await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /^log in$/i }).click();
    const reached = await page.waitForURL(/\/dashboard/, { timeout: 15000 }).then(() => true, () => false);
    check("login form redirects to /dashboard", reached, page.url());
    if (!reached) throw new Error("login did not complete");

    await visit("/dashboard", /^overview$/i, { expectUrl: "/dashboard" });
    await visit("/dashboard/plants", /^plants$/i);
    const rows = page.locator("table.dash-table tbody tr");
    check("plants table has rows", (await rows.count()) >= PLANTS.length, `${await rows.count()} rows`);
    for (const name of PLANTS) {
      const row = rows.filter({ hasText: name });
      const found = (await row.count()) === 1;
      check(`plants table lists "${name}"`, found);
      if (found) {
        const badge = (await row.first().locator('[data-testid="source-badge"]').allInnerTexts()).map((t) => t.trim());
        check(`"${name}" carries the SIMULATED badge`, badge.includes("SIMULATED"), `badges: ${JSON.stringify(badge)}`);
      }
    }
    const emptyShown = await page.getByText("No plants registered yet").count();
    check("plants empty state is not shown", emptyShown === 0);

    await visit(`/dashboard/plants/${firstId}`, new RegExp(escapeRe(apiPlants[0].name), "i"));
    await visit("/dashboard/alerts", /^alerts$/i);
    await visit("/dashboard/performance", /^performance$/i);

    // PVDAQ-style single-axis tracker plant: labelled "not supported" state, Generate disabled, no failed API calls
    await visit(`/dashboard/plants/${trackerId}`, new RegExp(escapeRe(TRACKER_NAME), "i"));
    const notice = "Not supported for single-axis trackers (fixed-tilt baseline invalid)";
    check("tracker plant detail shows the labelled unsupported state", (await page.getByText(notice).count()) === 1);
    check("tracker plant 'Run forecast' is disabled", await page.getByRole("button", { name: /run forecast/i }).isDisabled());
    await visit("/dashboard/performance", /^performance$/i);
    await page.locator("#forecast-plant-select").selectOption(String(trackerId));
    await page.waitForLoadState("networkidle");
    check("performance shows the unsupported state for the tracker plant", (await page.getByText(notice).count()) >= 1);
    check("performance 'Generate forecast' is disabled for the tracker plant", await page.getByRole("button", { name: /generate forecast|refresh/i }).first().isDisabled());
    check("no 'Unprocessable Entity' text shown", (await page.getByText(/unprocessable/i).count()) === 0);

    // Logout
    current = "logout";
    console.log("logout");
    await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /^sign out$/i }).click();
    const loggedOut = await page.waitForURL(/\/login/, { timeout: 15000 }).then(() => true, () => false);
    check("sign out returns to /login", loggedOut, page.url());
    await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
    check("/dashboard redirects to /login after logout", new URL(page.url()).pathname === "/login", page.url());
  } catch (e) {
    failures.push(`aborted: ${e instanceof Error ? e.message : String(e)}`);
    console.log(`  FAIL aborted: ${e instanceof Error ? e.message : e}`);
  } finally {
    check("frontend talked to the API at SMOKE_API_URL", apiSeen > 0, `${apiSeen} API responses (was the build made with NEXT_PUBLIC_API_URL=${API}?)`);
    check("zero console errors", consoleErrors.length === 0, consoleErrors.join(" | "));
    check("zero uncaught page errors", pageErrors.length === 0, pageErrors.join(" | "));
    check("zero failed API requests", badRequests.length === 0, badRequests.join(" | "));
    await browser.close();
  }
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

main()
  .catch((e) => {
    failures.push(`unexpected: ${e instanceof Error ? e.stack : e}`);
  })
  .finally(() => {
    console.log(`\nsmoke: ${passes} checks passed, ${failures.length} failed`);
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(failures.length ? 1 : 0);
  });
