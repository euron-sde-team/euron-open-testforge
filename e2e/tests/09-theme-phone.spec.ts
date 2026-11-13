import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, demoProject, expectNoOverflow, watchConsole } from "../helpers";

test("the theme toggle switches between light and dark", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/projects");
  const html = page.locator("html");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  // Click until the app has hydrated and the toggle answers.
  await expect(async () => {
    await page.getByRole("button", { name: "Switch to dark theme" }).click({ timeout: 2_000 });
    await expect(html).toHaveClass(/dark/, { timeout: 1_000 });
  }).toPass({ timeout: 30_000 });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(html).not.toHaveClass(/dark/);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(html).toHaveClass(/dark/);
  await page.reload();
  await expect(html).toHaveClass(/dark/);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  expect(errors).toEqual([]);
});

test.describe("phone layout", () => {
  test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });

  test("pages fit a 375 px screen and the menu opens the navigation", async ({ page }) => {
    const admin = await apiAs(ADMIN.email);
    const shop = await demoProject(admin, "shop-api");
    const runs = await call<{ id: string; status: string }[]>(admin, "GET", `/api/v1/projects/${shop.id}/runs`);
    const errors = watchConsole(page);
    for (const path of ["", "/source", "/tests", `/runs/${runs.find((r) => r.status === "failed")?.id}`, "/coverage", "/settings"]) {
      await page.goto(`/projects/${shop.id}${path}`);
      await expect(page.locator("main h1")).toBeVisible();
      await expectNoOverflow(page);
    }
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Pull requests" }).click();
    await expect(page.getByRole("heading", { name: "Pull requests" })).toBeVisible();
    await expectNoOverflow(page);
    expect(errors).toEqual([]);
    await admin.dispose();
  });
});
