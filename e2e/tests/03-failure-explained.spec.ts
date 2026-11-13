import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, demoProject, watchConsole } from "../helpers";

interface Run {
  id: string;
  status: string;
}

/**
 * A8: the Shop API run that failed on the split_bill bug explains the failed assertion with
 * the value the code returned and the value the test expected, from that same run.
 */
test("a failing test is explained with actual and expected", async ({ page }) => {
  const admin = await apiAs(ADMIN.email);
  const shop = await demoProject(admin, "shop-api");
  const runs = await call<Run[]>(admin, "GET", `/api/v1/projects/${shop.id}/runs`);
  const failed = runs.find((r) => r.status === "failed");
  expect(failed, "the demo has a failing Shop API run").toBeTruthy();
  const errors = watchConsole(page);

  await page.goto(`/projects/${shop.id}/runs/${failed?.id}`);
  await expect(page.locator("[data-qa=sandbox-note]")).toContainText("no credentials");
  const failure = page.locator("[data-qa=failure]").filter({ hasText: "test_split_bill" }).first();
  await expect(failure).toBeVisible();
  await expect(failure.locator("[data-qa=actual]")).toHaveText("[33.33, 33.33, 33.33]");
  await expect(failure.locator("[data-qa=expected]")).toHaveText("[33.34, 33.33, 33.33]");
  await expect(failure.locator("[data-qa=expression]")).toContainText("split_bill(100.0, 3)");
  await expect(failure.locator("[data-qa=explanation]")).toContainText("expected the value to equal");

  // The model can add a narrative from the captured values, without a second run.
  await failure.getByRole("button", { name: "Explain with the model" }).click();
  await expect(failure.locator("[data-qa=model-explanation]")).toBeVisible({ timeout: 60_000 });

  // From the failure to the test that failed, with the code it tests.
  await failure.getByRole("button", { name: "Open the test" }).click();
  await expect(page.getByText("The code it tests")).toBeVisible();
  await expect(page.locator("[data-qa=assertions]")).toContainText("split_bill(100.0, 3)");
  expect(errors).toEqual([]);
  await admin.dispose();
});
