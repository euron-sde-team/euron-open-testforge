/**
 * Curated README screenshots and tour frames from the seeded stack (real data only).
 *
 *   make up && make demo
 *   QA_PASSWORD=... node screenshots.mjs     (then make-tour.sh stitches docs/assets/tour.gif)
 *
 * Every screen shows the demo as the API seeded it: the Shop API project with its split_bill
 * failure, the Sandbox checks project with its refused network and file access and the run
 * stopped at the wall clock limit, and pull request #12.
 *
 * Writes docs/assets/screenshots/NN-name.png and scripts/qa/output/tour/NN.png.
 */
import { mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.QA_BASE ?? "http://localhost:5610";
const PASSWORD = process.env.QA_PASSWORD ?? process.env.TESTFORGE_DEMO_PASSWORD ?? "";
const SHOTS = path.resolve(HERE, "../../docs/assets/screenshots");
const TOUR = path.resolve(HERE, "output/tour");
const CHROME = process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH) ? process.env.CHROME_PATH : undefined;
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1 };
const PHONE = { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 };

const ADMIN = "maya.chen@example.com";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let tourIndex = 0;

async function api(token, method, url) {
  const resp = await fetch(`${BASE}${url}`, { method, headers: { authorization: `Bearer ${token}`, "x-tf-csrf": "1" } });
  if (!resp.ok) throw new Error(`${method} ${url}: ${resp.status} ${await resp.text()}`);
  return resp.json();
}

async function token(email) {
  const resp = await fetch(`${BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-tf-csrf": "1" },
    body: JSON.stringify({ email, password: PASSWORD }),
  });
  if (!resp.ok) throw new Error(`sign-in for ${email} failed (${resp.status}): run make demo first`);
  return (await resp.json()).session_token;
}

async function settle(page, ms = 900) {
  await page.waitForNetworkIdle({ idleTime: 400, timeout: 8_000 }).catch(() => {});
  await sleep(ms);
}

async function shot(page, name, { tour = true, curated = true } = {}) {
  await page.mouse.move(1, 1);
  await sleep(250);
  if (curated) await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
  if (tour) await page.screenshot({ path: path.join(TOUR, `${String(++tourIndex).padStart(2, "0")}.png`) });
  console.log(`shot ${name}`);
}

async function go(page, url) {
  await page.goto(`${BASE}${url}`, { waitUntil: "networkidle2", timeout: 120_000 });
  await settle(page);
}

/** Scroll so an element sits near the top of the viewport (below the sticky top bar). */
async function scrollTo(page, selector, offset = 72) {
  await page.evaluate(
    (sel, off) => {
      const el = document.querySelector(sel);
      if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off, behavior: "instant" });
    },
    selector,
    offset,
  );
  await sleep(300);
}

async function main() {
  await rm(TOUR, { recursive: true, force: true });
  await mkdir(SHOTS, { recursive: true });
  await mkdir(TOUR, { recursive: true });
  const t = await token(ADMIN);
  const projects = await api(t, "GET", "/api/v1/projects");
  const shop = projects.find((p) => p.slug === "shop-api");
  const sandbox = projects.find((p) => p.slug === "sandbox-checks");
  if (!shop || !sandbox) throw new Error("run make demo first");
  const runs = await api(t, "GET", `/api/v1/projects/${shop.id}/runs`);
  const failRun = runs.find((r) => r.status === "failed");
  const sbRuns = await api(t, "GET", `/api/v1/projects/${sandbox.id}/runs`);
  const escape = sbRuns.find((r) => r.status === "failed");
  const limited = sbRuns.find((r) => r.status === "limit_exceeded");
  const tests = await api(t, "GET", `/api/v1/projects/${shop.id}/tests`);
  const split = tests.find((x) => x.name.startsWith("test_split_bill") && x.last_outcome === "failed") ?? tests.find((x) => x.name.startsWith("test_split_bill"));
  const pull = (await api(t, "GET", `/api/v1/projects/${shop.id}/pulls`))[0];
  const spec = (await api(t, "GET", `/api/v1/projects/${shop.id}/specs`))[0];
  const P = `/projects/${shop.id}`;

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport(DESKTOP);
  await go(page, "/login");
  await page.evaluate(() => localStorage.setItem("theme", "light"));
  await go(page, "/login");
  await page.waitForSelector("#email");
  await shot(page, "01-sign-in", { curated: false });
  await page.type("#email", ADMIN);
  await page.type("#password", PASSWORD);
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle2", timeout: 120_000 }), page.click("button[type=submit]")]);

  await go(page, "/projects");
  await shot(page, "01-projects");
  await go(page, P);
  await shot(page, "02-overview");
  await go(page, `${P}/source?file=app/pricing.py`);
  await scrollTo(page, "[role=tablist]", 76);
  // Show split_bill, whose bug the tests catch, with its covered and missing lines.
  await page.evaluate(() => {
    const region = document.querySelector("[data-qa=code-view] [role=region]");
    const line = document.querySelector("[data-qa=code-view] [data-line='31']");
    if (region && line) region.scrollTop = line.offsetTop - 8;
  });
  await sleep(200);
  await shot(page, "03-source-explorer");
  await go(page, `${P}/source?tab=units&untested=1`);
  await shot(page, "04-untested-units");
  await go(page, `${P}/tests`);
  await shot(page, "05-generated-tests");
  // The generation that refused tests opens by itself, with each refusal and its reason.
  await scrollTo(page, "section:has([data-qa=generations])", 72);
  await shot(page, "06-refused-tests");
  if (split) {
    await go(page, `${P}/tests/${split.id}`);
    await shot(page, "07-test-detail");
  }
  if (failRun) {
    await go(page, `${P}/runs/${failRun.id}`);
    await shot(page, "08-run-detail", { curated: false });
    await scrollTo(page, "#failures-title", 72);
    await shot(page, "08-run-failure-explained");
  }
  if (escape) {
    await go(page, `/projects/${sandbox.id}/runs/${escape.id}`);
    await scrollTo(page, "[data-qa=refusal-summary]", 72);
    await shot(page, "09-sandbox-refusals");
  }
  if (limited) {
    await go(page, `/projects/${sandbox.id}/runs/${limited.id}`);
    await shot(page, "10-limit-crossed");
  }
  await go(page, `${P}/coverage`);
  await shot(page, "11-coverage");
  if (pull) {
    await go(page, `${P}/pulls/${pull.id}`);
    await shot(page, "12-pull-request");
  }
  if (spec) {
    await go(page, `${P}/specs/${spec.id}`);
    await shot(page, "13-api-spec");
  }
  await go(page, `${P}/audit`);
  await shot(page, "14-audit-log", { tour: false });
  await go(page, `${P}/settings`);
  await scrollTo(page, "#lim-run_cpu_s", 260);
  await shot(page, "15-settings", { tour: false });

  await page.evaluate(() => localStorage.setItem("theme", "dark"));
  if (failRun) {
    await go(page, `${P}/runs/${failRun.id}`);
    await scrollTo(page, "#failures-title", 72);
    await shot(page, "16-dark-run-failure");
  }
  await go(page, P);
  await shot(page, "17-dark-overview", { tour: false });

  await page.evaluate(() => localStorage.setItem("theme", "light"));
  await page.setViewport(PHONE);
  if (failRun) {
    await go(page, `${P}/runs/${failRun.id}`);
    await scrollTo(page, "[data-qa=failure]", 70);
    await shot(page, "18-phone-run-failure", { tour: false });
  }
  await browser.close();
  console.log(`\n${tourIndex} tour frames in ${TOUR}; screenshots in ${SHOTS}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
