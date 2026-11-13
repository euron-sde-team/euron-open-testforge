import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, projectWithShop, signedInContext, until, VIEWER, watchConsole } from "../helpers";

/** A10: every run and who triggered it is in the project's audit log, which every member may read. */
test("the audit log shows each run and who triggered it", async ({ browser, page }) => {
  const admin = await apiAs(ADMIN.email);
  const shop = await projectWithShop(admin, "Audit trail");
  await call(admin, "POST", `/api/v1/projects/${shop.id}/members`, { email: VIEWER, role: "viewer" });
  const run = await call<{ id: string }>(admin, "POST", `/api/v1/projects/${shop.id}/runs?wait=30`, { kind: "project" });
  await until(admin, `/api/v1/projects/${shop.id}/runs/${run.id}`, (r: { status: string }) => !["queued", "running"].includes(r.status));
  const errors = watchConsole(page);

  await page.goto(`/projects/${shop.id}/audit`);
  await page.getByRole("combobox", { name: "What happened" }).click();
  await page.getByRole("option", { name: "Runs started" }).click();
  const rows = page.locator("tbody tr");
  await expect(rows.first()).toContainText("run.requested");
  await expect(rows.first()).toContainText(ADMIN.email);
  await expect(page.locator("tbody")).toContainText(run.id.slice(0, 8));

  // A viewer reads the same log.
  const { context, page: viewer } = await signedInContext(browser, VIEWER);
  await viewer.goto(`/projects/${shop.id}/audit`);
  await expect(viewer.locator("tbody tr").first()).toBeVisible();
  await expect(viewer.getByRole("heading", { name: "Audit log" })).toBeVisible();
  await context.close();
  expect(errors).toEqual([]);
  await admin.dispose();
});
