// Runs inside the sandbox and crosses a limit.
import { it } from "vitest";

it("spins forever", () => {
  let n = 0;
  for (;;) n++;
});
