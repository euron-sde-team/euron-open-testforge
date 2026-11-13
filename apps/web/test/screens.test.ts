import { describe, expect, it } from "vitest";

import { coverageRows } from "@/components/charts/coverage-chart";
import { filesByNeed } from "@/features/coverage/components/coverage-screen";
import { parseLimit } from "@/features/projects/components/project-settings-screen";
import { diffStat } from "@/features/pulls/components/pulls-screen";
import { runCounts } from "@/features/runs/components/run-row";
import { coveredOperations } from "@/features/specs/components/specs-screen";
import { allowedKinds } from "@/features/tests/components/generate-dialog";
import { readUnit } from "@/features/tests/components/test-detail-screen";
import type { Coverage } from "@/lib/api/types";

describe("screen helpers", () => {
  it("summarizes a run's counts without the zeros", () => {
    expect(runCounts({ passed: 28, failed: 1, errors: 0, skipped: 0 })).toBe("28 passed, 1 failed");
    expect(runCounts({ passed: 0, failed: 0, errors: 1, skipped: 0 })).toBe("1 error");
    expect(runCounts({ passed: 0, failed: 0, errors: 0, skipped: 0 })).toBe("No test results");
  });
  it("only offers API tests for an OpenAPI document, and code tests otherwise", () => {
    expect(allowedKinds("spec-1")).toEqual(["api"]);
    expect(allowedKinds(null)).toEqual(["unit", "edge", "negative"]);
  });
  it("counts an operation as covered only by a kept API test", () => {
    const covered = coveredOperations([
      { kind: "api", status: "accepted", operation: "GET /health" },
      { kind: "api", status: "discarded", operation: "POST /cart/quote" },
      { kind: "api", status: "proposed", operation: "GET /products" },
      { kind: "unit", status: "accepted", operation: null },
    ]);
    expect([...covered].sort()).toEqual(["GET /health", "GET /products"]);
  });
  it("sums a pull request's diff", () => {
    const s = diffStat({
      changed_files: [
        { path: "app/inventory.py", additions: 11, deletions: 0, changed_lines: [[28, 38]] },
        { path: "app/pricing.py", additions: 7, deletions: 2, changed_lines: [] },
      ],
    });
    expect(s).toEqual({ files: 2, additions: 18, deletions: 2 });
  });
  it("sorts coverage files least covered first and skips empty files", () => {
    const cov = {
      files: [
        { path: "app/__init__.py", missing: [], percent: 100, lines_total: 0, lines_covered: 0 },
        { path: "app/main.py", missing: [], percent: 100, lines_total: 20, lines_covered: 20 },
        { path: "app/cart.py", missing: [[31, 33]], percent: 85.71, lines_total: 21, lines_covered: 18 },
      ],
    } as unknown as Coverage;
    expect(filesByNeed(cov).map((f) => f.path)).toEqual(["app/cart.py", "app/main.py"]);
    expect(filesByNeed(null)).toEqual([]);
  });
  it("orders coverage points by time and rounds them", () => {
    const rows = coverageRows([
      { at: "2026-11-13T07:37:48Z", percent: 92.314, runId: "c" },
      { at: "2026-11-13T07:37:46Z", percent: 9.89, runId: "a" },
    ]);
    expect(rows.map((r) => r.percent)).toEqual([9.89, 92.31]);
  });
  it("validates a run limit field", () => {
    expect(parseLimit("", 1, 3600)).toBeNull();
    expect(parseLimit("120", 1, 3600)).toBe(120);
    expect(parseLimit("0", 1, 3600)).toBeUndefined();
    expect(parseLimit("1.5", 1, 3600)).toBeUndefined();
    expect(parseLimit("abc", 1, 3600)).toBeUndefined();
  });
  it("reads the unit a test is for, or nothing", () => {
    expect(readUnit({ qualname: "app.pricing.split_bill", kind: "function", file: "app/pricing.py", start_line: 34, end_line: 45, signature: "def split_bill()", source: "x" })).toMatchObject({
      qualname: "app.pricing.split_bill",
      start_line: 34,
    });
    expect(readUnit(null)).toBeNull();
    expect(readUnit({ kind: "function" })).toBeNull();
  });
});
