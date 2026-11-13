// Runs inside the sandbox and crosses a limit.
import { expect, it } from "vitest";

it("grows the heap without end", () => {
  const keep: number[][] = [];
  for (;;) keep.push(new Array(1_000_000).fill(1));
  expect(keep.length).toBeGreaterThan(0);
});
