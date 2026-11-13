import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, demoProject, signedInContext, VIEWER, watchConsole } from "../helpers";

/** A viewer reads everything and sees no control that imports, generates, accepts or runs. */
test("a viewer has no generate, accept, run or import controls", async ({ browser }) => {
  const admin = await apiAs(ADMIN.email);
  const shop = await demoProject(admin, "shop-api");
  const tests = await call<{ id: string; status: string }[]>(admin, "GET", `/api/v1/projects/${shop.id}/tests`);
  const runs = await call<{ id: string; status: string }[]>(admin, "GET", `/api/v1/projects/${shop.id}/runs`);
  const pulls = await call<{ id: string }[]>(admin, "GET", `/api/v1/projects/${shop.id}/pulls`);
  const specs = await call<{ id: string }[]>(admin, "GET", `/api/v1/projects/${shop.id}/specs`);
  const { context, page } = await signedInContext(browser, VIEWER);
  const errors = watchConsole(page);
  const none = async (name: RegExp) => expect(page.getByRole("button", { name })).toHaveCount(0);
  const P = `/projects/${shop.id}`;

  await page.goto(P);
  await expect(page.getByRole("note")).toContainText("You can read everything");
  await none(/Import code|Run tests/);

  await page.goto(`${P}/source?tab=units`);
  await expect(page.locator("[data-qa=unit]").first()).toBeVisible();
  await none(/Generate tests/);

  await page.goto(`${P}/tests`);
  await expect(page.locator("[data-qa=test-row]").first()).toBeVisible();
  await none(/Generate tests|Accept|Discard/);
  await expect(page.getByRole("checkbox")).toHaveCount(0);

  await page.goto(`${P}/tests/${tests.find((t) => t.status === "proposed")?.id ?? tests[0]?.id}`);
  await expect(page.locator("[data-qa=assertions]")).toBeVisible();
  await none(/Accept|Discard|Regenerate|Run this test/);

  await page.goto(`${P}/runs`);
  await expect(page.locator("[data-qa=run-row]").first()).toBeVisible();
  await none(/Start a run/);
  await page.goto(`${P}/runs/${runs.find((r) => r.status === "failed")?.id}`);
  await expect(page.locator("[data-qa=failure]").first()).toBeVisible();
  await none(/Explain with the model/);

  await page.goto(`${P}/pulls/${pulls[0]?.id}`);
  await expect(page.locator("[data-qa=changed-files]")).toBeVisible();
  await none(/Generate tests for this change|Import a pull request/);
  await page.goto(`${P}/specs/${specs[0]?.id}`);
  await expect(page.locator("[data-qa=operation]").first()).toBeVisible();
  await none(/Generate API tests/);
  await page.goto(`${P}/settings?tab=providers`);
  await expect(page.locator("[data-qa=provider]").first()).toBeVisible();
  await none(/Add provider/);
  await expect(page.getByRole("tab", { name: /API keys/ })).toHaveCount(0);

  // The API agrees.
  const viewerApi = await apiAs(VIEWER);
  expect((await viewerApi.post(`/api/v1/projects/${shop.id}/runs`, { data: { kind: "generated" } })).status()).toBe(403);
  expect((await viewerApi.post(`/api/v1/projects/${shop.id}/tests/generate`, { data: { kinds: ["unit"] } })).status()).toBe(403);
  await viewerApi.dispose();
  expect(errors).toEqual([]);
  await context.close();
  await admin.dispose();
});
