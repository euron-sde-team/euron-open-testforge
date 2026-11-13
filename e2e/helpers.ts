import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32 } from "node:zlib";

import { type APIRequestContext, type Browser, type BrowserContext, expect, type Page, request } from "@playwright/test";

const BASE = process.env.WEB_URL || "http://localhost:5610";
export const PASSWORD = process.env.E2E_PASSWORD || process.env.TESTFORGE_DEMO_PASSWORD || "";
export const ADMIN = { email: process.env.E2E_EMAIL || "maya.chen@example.com", password: PASSWORD };
export const EDITOR = "arjun.mehta@example.com";
export const VIEWER = "sofia.lopez@example.com";

/** Mutations through the API carry the CSRF header the web app sends. */
export const CSRF = { "x-tf-csrf": "1" };

/** A per-run suffix so suites can run repeatedly against the same seeded stack. */
export const RUN = process.env.E2E_RUN || Date.now().toString(36).slice(-5);

/** Fail the test on any console error or CSP violation the page reports. */
export function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

async function retrying(fn: () => Promise<import("@playwright/test").APIResponse>) {
  for (let i = 0; i < 10; i++) {
    const resp = await fn();
    if (resp.status() !== 429) return resp;
    await new Promise((r) => setTimeout(r, Number(resp.headers()["retry-after"] ?? "5") * 1000));
  }
  return fn();
}

/** An API client signed in as someone (waits out the sign-in limit if needed). */
export async function apiAs(email: string, password = PASSWORD): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: BASE, extraHTTPHeaders: CSRF });
  const resp = await retrying(() => ctx.post("/api/v1/auth/login", { data: { email, password } }));
  expect(resp.status(), await resp.text()).toBe(200);
  return ctx;
}

/** JSON from the API, asserting success. */
export async function call<T = unknown>(ctx: APIRequestContext, method: string, path: string, data?: unknown): Promise<T> {
  const resp = await retrying(() => ctx.fetch(path, { method, data }));
  expect(resp.status(), `${method} ${path}: ${await resp.text()}`).toBeLessThan(300);
  return (resp.status() === 204 ? null : await resp.json()) as T;
}

/** A browser context carrying the session of an existing account. */
export async function signedInContext(browser: Browser, email: string): Promise<{ context: BrowserContext; page: Page }> {
  const api = await apiAs(email);
  const state = await api.storageState();
  await api.dispose();
  const context = await browser.newContext({ storageState: state });
  return { context, page: await context.newPage() };
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  slug: string;
}

/** The seeded demo project by slug ("shop-api", "web-toolkit", "sandbox-checks"). */
export async function demoProject(api: APIRequestContext, slug = "shop-api"): Promise<Project> {
  const projects = await call<Project[]>(api, "GET", "/api/v1/projects");
  const found = projects.find((p) => p.slug === slug);
  expect(found, "run make demo first").toBeTruthy();
  return found as Project;
}

/** A fresh project for a suite, in the demo organization, with the built-in mock provider. */
export async function newProject(api: APIRequestContext, name: string, opts: { mock?: boolean } = {}): Promise<Project> {
  const demo = await demoProject(api);
  const p = await call<Project>(api, "POST", "/api/v1/projects", { org_id: demo.org_id, name: `${name} ${RUN}` });
  if (opts.mock !== false) await call(api, "POST", `/api/v1/projects/${p.id}/providers`, { name: "mock", kind: "mock", is_default: true });
  return p;
}

/** A fresh project with euron-demo/python-shop imported from (mock) GitHub and analyzed. */
export async function projectWithShop(api: APIRequestContext, name: string): Promise<Project> {
  const p = await newProject(api, name);
  const imp = await call<{ id: string; status: string }>(api, "POST", `/api/v1/projects/${p.id}/imports/github?wait=30`, { repo: "euron-demo/python-shop", ref: "main" });
  const done = await until(api, `/api/v1/projects/${p.id}/imports/${imp.id}`, (i: { status: string }) => i.status === "ready" || i.status === "failed");
  expect(done.status).toBe("ready");
  return p;
}

/**
 * Poll a GET until the predicate holds. Long waits go through polling, never one request:
 * the web app's proxy gives up on a single request after two minutes.
 */
export async function until<T>(api: APIRequestContext, path: string, done: (body: T) => boolean, timeoutMs = 150_000): Promise<T> {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const body = await call<T>(api, "GET", path);
    if (done(body) || Date.now() > end) return body;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

/** Pick an option in one of the web app's custom selects. */
export async function choose(page: Page, trigger: string, option: string | RegExp): Promise<void> {
  await page.getByRole("combobox", { name: trigger }).click();
  await page.getByRole("option", { name: option }).first().click();
}

/** The page has no horizontal overflow (phone layout check). */
export async function expectNoOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

/**
 * A ZIP (stored, no compression) of a folder, built in the test so the upload is a real
 * project archive and nothing binary lives in the repository.
 */
export function zipFolder(root: string): Buffer {
  const files: { name: string; data: Buffer }[] = [];
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir).sort()) {
      if (entry === "__pycache__" || entry.startsWith(".")) continue;
      const full = join(dir, entry);
      const rel = prefix ? `${prefix}/${entry}` : entry;
      if (statSync(full).isDirectory()) walk(full, rel);
      else files.push({ name: rel, data: readFileSync(full) });
    }
  };
  walk(root, "");
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const f of files) {
    const name = Buffer.from(f.name, "utf8");
    const crc = crc32(f.data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt32LE(0, 10);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(f.data.length, 18);
    local.writeUInt32LE(f.data.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);
    locals.push(local, name, f.data);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt32LE(0, 12);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(f.data.length, 20);
    central.writeUInt32LE(f.data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(0, 30);
    central.writeUInt32LE(0, 34);
    central.writeUInt32LE(0, 38);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, name);
    offset += 30 + name.length + f.data.length;
  }
  const dir = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(dir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, dir, end]);
}

/** The demo projects that ship with the API (read-only source for the ZIP upload). */
export const DEMO_SOURCES = resolve(dirname(fileURLToPath(import.meta.url)), "../apps/api/src/testforge/demo/projects");
