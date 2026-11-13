import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, needsSignIn } from "@/middleware";

describe("needsSignIn", () => {
  it("never requires a session on the public auth pages", () => {
    expect(needsSignIn("/login")).toBe(false);
    expect(needsSignIn("/login/")).toBe(false);
    expect(needsSignIn("/signup")).toBe(false);
  });
  it("requires a session on every other page", () => {
    expect(needsSignIn("/")).toBe(true);
    expect(needsSignIn("/projects")).toBe(true);
    expect(needsSignIn("/admin/audit")).toBe(true);
  });
  it("does not treat a page that merely starts with the word login as public", () => {
    expect(needsSignIn("/loginx")).toBe(true);
  });
});

describe("contentSecurityPolicy", () => {
  it("allows only this origin and no framing", () => {
    const csp = contentSecurityPolicy(true);
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).not.toContain("unsafe-eval");
    expect(contentSecurityPolicy(false)).toContain("unsafe-eval");
  });
});
