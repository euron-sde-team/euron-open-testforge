import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, projectWithShop, watchConsole } from "../helpers";

/**
 * A9: importing pull request #12 lists the files it changed, with their changed lines, and
 * offers to generate tests only for the units those lines touch.
 */
test("import pull request #12 and generate tests scoped to it", async ({ page }) => {
  const admin = await apiAs(ADMIN.email);
  const project = await projectWithShop(admin, "Pull scope");
  const errors = watchConsole(page);

  await page.goto(`/projects/${project.id}/pulls`);
  await expect(page.getByText("No pull requests imported")).toBeVisible();
  await page.getByRole("button", { name: "Import a pull request" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Repository")).toHaveValue("euron-demo/python-shop");
  await dialog.getByLabel("Number").fill("12");
  await dialog.getByRole("button", { name: "Import pull request" }).click();

  await expect(page.getByRole("heading", { name: /#12 Plan restocks and split bills/ })).toBeVisible();
  const files = page.locator("[data-qa=changed-files]");
  await expect(files).toContainText("app/pricing.py", { timeout: 60_000 });
  await expect(files).toContainText("app/inventory.py");
  await expect(files).toContainText("Changed lines: 28 to 38");
  const scoped = page.locator("[data-qa=unit]");
  await expect(scoped.first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("split_bill").first()).toBeVisible();

  await page.getByRole("button", { name: "Generate tests for this change" }).click();
  const gen = page.getByRole("dialog");
  await expect(gen).toContainText("pull request #12");
  await gen.getByRole("button", { name: "Generate tests" }).click();
  await expect(gen.locator("[data-qa=generation-result]")).toBeVisible({ timeout: 120_000 });
  expect(Number(await gen.locator("[data-qa=proposed-count]").textContent())).toBeGreaterThan(0);
  await gen.getByRole("button", { name: /Review \d+ tests?/ }).click();
  await expect(page.locator("[data-qa=test-row]").first()).toBeVisible();
  for (const row of await page.locator("[data-qa=test-row]").all()) {
    await expect(row).toContainText(/split_bill|restock|inventory|pricing/i);
  }
  expect(errors).toEqual([]);
  await admin.dispose();
});
