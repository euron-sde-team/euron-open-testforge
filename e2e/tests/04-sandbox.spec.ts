import { expect, test } from "@playwright/test";

import { ADMIN, apiAs, call, demoProject, watchConsole } from "../helpers";

interface Run {
  id: string;
  status: string;
  limit_exceeded: string | null;
}

/**
 * A3, A4 and A5 in the UI: the Sandbox checks project's own tests tried to reach the network
 * and read host files and credentials, and every attempt was refused; another run was
 * stopped at its wall clock limit and says so.
 */
test("network and file access refused, and a run stopped at its limit", async ({ page }) => {
  const admin = await apiAs(ADMIN.email);
  const project = await demoProject(admin, "sandbox-checks");
  const runs = await call<Run[]>(admin, "GET", `/api/v1/projects/${project.id}/runs`);
  const escape = runs.find((r) => r.status === "failed");
  const limited = runs.find((r) => r.status === "limit_exceeded");
  expect(escape && limited, "the demo has both Sandbox checks runs").toBeTruthy();
  const errors = watchConsole(page);

  await page.goto(`/projects/${project.id}/runs/${escape?.id}`);
  const refusals = page.locator("[data-qa=refusal]");
  await expect(refusals.filter({ hasText: "Network access refused" })).toHaveCount(2);
  await expect(refusals.filter({ hasText: "Host file access refused" })).toHaveCount(1);
  await expect(refusals.filter({ hasText: "Credentials not available" })).toHaveCount(1);
  await expect(page.locator("[data-qa=refusal-summary]")).toContainText("The sandbox refused 4 attempts to leave this run");
  await expect(page.getByText(/no network interface/i).first()).toBeVisible();

  await page.goto(`/projects/${project.id}/runs`);
  await expect(page.locator("[data-qa=run-status]").filter({ hasText: "Limit crossed: Wall clock" })).toBeVisible();
  await page.goto(`/projects/${project.id}/runs/${limited?.id}`);
  const banner = page.locator("[data-qa=limit-banner]");
  await expect(banner).toContainText("Limit crossed: Wall clock");
  await expect(banner).toContainText("8 s wall clock limit");
  await expect(page.locator("[data-qa=measurements]")).toContainText("of 8 s");
  expect(errors).toEqual([]);
  await admin.dispose();
});
