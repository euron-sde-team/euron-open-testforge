import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, DEMO_SOURCES, newProject, RUN, watchConsole, zipFolder } from "../helpers";

/**
 * A1 through the web app: create a project, import euron-demo/python-shop from GitHub, see
 * the analysis, generate tests (and the ones refused for having no assertion), accept them,
 * run them in the sandbox and see the result and a real coverage number.
 */
test("import from GitHub, generate, accept, run and see coverage", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/projects");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill(`Checkout ${RUN}`);
  await page.getByRole("button", { name: "Create project" }).click();

  // The new project opens with the import dialog.
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Import code" })).toBeVisible();
  await dialog.getByLabel("Repository").fill("euron-demo/python-shop");
  await dialog.getByLabel("Branch, tag or commit").fill("main");
  await dialog.getByRole("button", { name: "Import repository" }).click();
  const result = dialog.locator("[data-qa=import-result]");
  await expect(result).toBeVisible({ timeout: 90_000 });
  await expect(result).toContainText("Python");
  await expect(result).toContainText("FastAPI");
  await expect(result).toContainText(/\d+ units/);
  await dialog.getByRole("button", { name: "Explore the source" }).click();

  // The source explorer shows the files and the untested units.
  await expect(page.getByRole("heading", { name: "Source" })).toBeVisible();
  await expect(page.locator("[data-qa=tree-file]").filter({ hasText: /^pricing\.py/ })).toBeVisible();
  await page.getByRole("tab", { name: "Units" }).click();
  await expect(page.locator("[data-qa=unit]").first()).toBeVisible();
  await expect(page.locator("[data-qa=unreferenced]").first()).toBeVisible();

  // Generate for the whole import: the built-in mock is one click away for an admin.
  await page.getByRole("link", { name: "Tests", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tests", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Generate tests" }).first().click();
  const gen = page.getByRole("dialog");
  await gen.getByRole("button", { name: "Use the built-in mock" }).click();
  await expect(gen.getByRole("button", { name: "Use the built-in mock" })).toHaveCount(0);
  await gen.getByRole("button", { name: "Generate tests" }).click();
  await expect(gen.locator("[data-qa=generation-result]")).toBeVisible({ timeout: 120_000 });
  const proposed = Number(await gen.locator("[data-qa=proposed-count]").textContent());
  const refused = Number(await gen.locator("[data-qa=refused-count]").textContent());
  expect(proposed).toBeGreaterThan(0);
  expect(refused).toBeGreaterThan(0);
  await expect(gen.locator("[data-qa=rejections] li").first()).toContainText(/no meaningful assertion/i);
  await gen.getByRole("button", { name: /Review \d+ tests?/ }).click();

  // Accept every proposed test, then read one with its assertions.
  await expect(page.locator("[data-qa=test-row]").first()).toBeVisible();
  await page.getByRole("checkbox", { name: "Select every test shown" }).click();
  await page.locator("[data-qa=bulk-actions]").getByRole("button", { name: "Accept" }).click();
  await expect(page.getByText(/tests? accepted/)).toBeVisible();
  await page.goto(page.url().replace(/\?.*$/, "?status=accepted"));
  await page.locator("[data-qa=test-row] a").first().click();
  await expect(page.locator("[data-qa=assertions] li").first()).toBeVisible();
  await expect(page.locator("[data-qa=code-view]").first()).toBeVisible();

  // Run them in the sandbox and see the result and real coverage.
  await page.getByRole("link", { name: "Runs", exact: true }).click();
  await page.getByRole("button", { name: "Start a run" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Run in the sandbox" }).click();
  await expect(page.locator("[data-qa=sandbox-note]")).toBeVisible();
  await expect(page.locator("[data-qa=measurements]")).toBeVisible({ timeout: 150_000 });
  await expect(page.locator("[data-qa=run-status]").first()).toHaveText(/Passed|Failed/);
  await expect(page.locator("[data-qa=cases] li").first()).toBeVisible();
  const coverage = page.getByRole("button", { name: /Coverage \d+(\.\d+)?%/ });
  await expect(coverage).toBeVisible();
  await coverage.click();
  await expect(page.locator("[data-qa=coverage-files]")).toBeVisible();
  await expect(page.getByText(/\d+(\.\d+)?%/).first()).toBeVisible();
  expect(errors).toEqual([]);
});

/** The same project code uploaded as a ZIP built from the demo source, analyzed the same way. */
test("upload a ZIP and see the analysis", async ({ page }) => {
  const admin = await apiAs(ADMIN.email);
  const project = await newProject(admin, "Shop upload");
  const errors = watchConsole(page);
  await page.goto(`/projects/${project.id}`);
  await expect(page.getByText("No code imported yet")).toBeVisible();
  await page.getByRole("button", { name: "Import code" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("radio", { name: /ZIP upload/ }).click();
  await dialog.getByLabel("Project archive").setInputFiles({ name: "python-shop.zip", mimeType: "application/zip", buffer: zipFolder(join(DEMO_SOURCES, "python-shop")) });
  await dialog.getByRole("button", { name: "Upload and analyze" }).click();
  const result = dialog.locator("[data-qa=import-result]");
  await expect(result).toBeVisible({ timeout: 90_000 });
  await expect(result).toContainText("Python");
  await expect(result).toContainText("pytest");
  await dialog.getByRole("button", { name: "Generate tests for untested code" }).click();
  await expect(page.locator("[data-qa=unit]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Generate tests for these \d+/ })).toBeVisible();
  const overview = await call<{ untested_units: number }>(admin, "GET", `/api/v1/projects/${project.id}/overview`);
  expect(overview.untested_units).toBeGreaterThan(0);
  expect(errors).toEqual([]);
  await admin.dispose();
});
