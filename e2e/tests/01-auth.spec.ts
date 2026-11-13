import { expect, test } from "@playwright/test";

import { ADMIN, watchConsole } from "../helpers";

test.use({ storageState: { cookies: [], origins: [] } });

test("signing in, a wrong password, and signing out", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /Tests for your code/ })).toBeVisible();
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password", { exact: true }).fill("Wrong-Pass-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(/incorrect/i)).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/projects/);
  await expect(page.getByText("Shop API").first()).toBeVisible();
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: /Sign out/ }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(errors.filter((e) => !e.includes("401"))).toEqual([]);
});
