import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, DEMO_SOURCES, projectWithShop, watchConsole } from "../helpers";

/** A7: an imported OpenAPI document gets API tests for every operation, and the UI shows them covered. */
test("import an OpenAPI document and generate API tests for every operation", async ({ page }) => {
  const admin = await apiAs(ADMIN.email);
  const project = await projectWithShop(admin, "API tests");
  const document = readFileSync(join(DEMO_SOURCES, "python-shop-openapi.json"), "utf8");
  const errors = watchConsole(page);

  await page.goto(`/projects/${project.id}/specs`);
  await expect(page.getByText("No OpenAPI document yet")).toBeVisible();
  await page.getByRole("button", { name: "Import an OpenAPI document" }).click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Document" }).fill(document);
  await page.getByRole("dialog").getByRole("button", { name: "Import document" }).click();

  const ops = page.locator("[data-qa=operation]");
  await expect(ops.first()).toBeVisible();
  const count = await ops.count();
  expect(count).toBeGreaterThanOrEqual(4);
  await expect(ops.filter({ hasText: "Not tested" })).toHaveCount(count);

  await page.getByRole("button", { name: "Generate API tests" }).click();
  const gen = page.getByRole("dialog");
  await expect(gen.getByRole("checkbox", { name: /^API/ })).toHaveAttribute("aria-checked", "true");
  await gen.getByRole("button", { name: "Generate tests" }).click();
  await expect(gen.locator("[data-qa=generation-result]")).toContainText(/Covers \d+ operations/, { timeout: 120_000 });
  await gen.getByRole("button", { name: "Close", exact: true }).last().click();
  await expect(ops.filter({ hasText: "Covered" })).toHaveCount(count);
  expect(errors).toEqual([]);
  await admin.dispose();
});
