// Runs inside the sandbox. Both tests must FAIL: a run has no network.
import { connect } from "node:net";
import { expect, it } from "vitest";

it("fetches from the internet", async () => {
  const res = await fetch("http://1.1.1.1/", { signal: AbortSignal.timeout(3000) });
  expect(res.status).toBeGreaterThan(0);
});

it("opens a socket to the platform database", async () => {
  await new Promise<void>((resolve, reject) => {
    const socket = connect({ host: "postgres", port: 5432 }, () => {
      socket.end();
      resolve();
    });
    socket.on("error", reject);
  });
});
