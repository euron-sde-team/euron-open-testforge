import { describe, expect, it } from "vitest";

import {
  can,
  canOrg,
  isAdmin,
  ORG_ROLE_DESCRIPTION,
  ORG_ROLES,
  projectPermissions,
  PROJECT_ROLE_DESCRIPTION,
  PROJECT_ROLES,
  roleDescription,
  roleLabel,
} from "@/lib/roles";

describe("can (project roles)", () => {
  it("ranks viewer below editor below admin", () => {
    expect(can("admin", "admin")).toBe(true);
    expect(can("admin", "editor")).toBe(true);
    expect(can("admin", "viewer")).toBe(true);
    expect(can("editor", "editor")).toBe(true);
    expect(can("editor", "admin")).toBe(false);
    expect(can("viewer", "viewer")).toBe(true);
    expect(can("viewer", "editor")).toBe(false);
  });
  it("denies unknown or missing roles", () => {
    expect(can(undefined, "viewer")).toBe(false);
    expect(can(null, "viewer")).toBe(false);
    expect(can("owner", "viewer")).toBe(false);
    expect(can("", "viewer")).toBe(false);
  });
});

describe("canOrg (organization roles)", () => {
  it("ranks member below admin below owner", () => {
    expect(canOrg("owner", "owner")).toBe(true);
    expect(canOrg("owner", "admin")).toBe(true);
    expect(canOrg("admin", "admin")).toBe(true);
    expect(canOrg("admin", "owner")).toBe(false);
    expect(canOrg("member", "admin")).toBe(false);
  });
  it("denies unknown or missing roles", () => {
    expect(canOrg(undefined, "member")).toBe(false);
    expect(canOrg(null, "member")).toBe(false);
    expect(canOrg("", "member")).toBe(false);
  });
});

describe("instance roles", () => {
  it("labels and describes admin and user", () => {
    expect(roleLabel("admin")).toBe("Admin");
    expect(roleLabel("user")).toBe("User");
    expect(roleLabel("student")).toBe("Unknown");
    expect(roleDescription("admin")).toMatch(/instance/);
    expect(roleDescription("nobody")).toBe("");
    expect(isAdmin("admin")).toBe(true);
    expect(isAdmin("user")).toBe(false);
  });
  it("describes every project role", () => {
    for (const r of PROJECT_ROLES) expect(PROJECT_ROLE_DESCRIPTION[r].length).toBeGreaterThan(10);
  });
  it("describes every organization role", () => {
    for (const r of ORG_ROLES) expect(ORG_ROLE_DESCRIPTION[r].length).toBeGreaterThan(10);
  });
});

/**
 * projectPermissions is what every screen reads to decide whether to render a control at
 * all (never merely disable one): a viewer generates, accepts, runs and imports nothing.
 */
const NONE = { canView: false, canImport: false, canGenerate: false, canReview: false, canRun: false, canAdmin: false };
describe("projectPermissions", () => {
  it("gives a viewer read access and nothing else", () => {
    expect(projectPermissions("viewer")).toEqual({ ...NONE, canView: true });
  });
  it("lets an editor import, generate, review and run, but not administer", () => {
    expect(projectPermissions("editor")).toEqual({ canView: true, canImport: true, canGenerate: true, canReview: true, canRun: true, canAdmin: false });
  });
  it("gives an admin every permission", () => {
    expect(Object.values(projectPermissions("admin")).every(Boolean)).toBe(true);
  });
  it("gives a missing or unknown role nothing, not even view", () => {
    for (const role of [null, undefined, "", "member", "owner"]) {
      expect(projectPermissions(role)).toEqual(NONE);
    }
  });
});
