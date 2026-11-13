import type { OrgRole, ProjectRole, Role } from "./api/types";

export const ROLES: readonly Role[] = ["admin", "user"] as const;

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", user: "User" };
const ROLE_DESCRIPTION: Record<Role, string> = {
  admin: "Runs this TestForge instance: users, system status, instance settings and the instance audit log.",
  user: "Works in the organizations and projects they are a member of, with the role each one gives them.",
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

export function roleLabel(role: string | null | undefined): string {
  return isRole(role) ? ROLE_LABEL[role] : "Unknown";
}

export function roleDescription(role: string | null | undefined): string {
  return isRole(role) ? ROLE_DESCRIPTION[role] : "";
}

export function isAdmin(role: string | null | undefined): boolean {
  return role === "admin";
}

export const PROJECT_ROLES: readonly ProjectRole[] = ["viewer", "editor", "admin"] as const;
const RANK: Record<ProjectRole, number> = { viewer: 0, editor: 1, admin: 2 };

export const PROJECT_ROLE_LABEL: Record<ProjectRole, string> = { viewer: "Viewer", editor: "Editor", admin: "Admin" };

export const PROJECT_ROLE_DESCRIPTION: Record<ProjectRole, string> = {
  viewer: "Reads imports, source analysis, generated tests, runs, coverage, reports and the audit log. Changes nothing.",
  editor: "Also imports code and pull requests, generates and reviews tests, and starts runs in the sandbox.",
  admin: "Also manages members, API keys, model providers, GitHub, webhooks and run limits.",
};

/** Whether a project role is at least ``needed``. */
export function can(role: string | null | undefined, needed: ProjectRole): boolean {
  const have = role && role in RANK ? RANK[role as ProjectRole] : -1;
  return have >= RANK[needed];
}

export const ORG_ROLES: readonly OrgRole[] = ["member", "admin", "owner"] as const;
const ORG_RANK: Record<OrgRole, number> = { member: 0, admin: 1, owner: 2 };

export const ORG_ROLE_LABEL: Record<OrgRole, string> = { member: "Member", admin: "Admin", owner: "Owner" };

export const ORG_ROLE_DESCRIPTION: Record<OrgRole, string> = {
  member: "Sees the projects they are added to, with the project role they are given.",
  admin: "Administers every project in the organization, and manages its members.",
  owner: "Everything an admin can do, plus renaming the organization and managing its owners.",
};

/** Whether an organization role is at least ``needed``. */
export function canOrg(role: string | null | undefined, needed: OrgRole): boolean {
  const have = role && role in ORG_RANK ? ORG_RANK[role as OrgRole] : -1;
  return have >= ORG_RANK[needed];
}

/** What a project role may do, as flags for the UI (viewers see no write-adjacent controls). */
export interface ProjectPermissions {
  canView: boolean;
  /** Import code, pull requests and OpenAPI documents. */
  canImport: boolean;
  /** Generate tests and ask the model to explain a failure. */
  canGenerate: boolean;
  /** Accept, discard or regenerate tests. */
  canReview: boolean;
  /** Start runs in the sandbox. */
  canRun: boolean;
  canAdmin: boolean;
}

export function projectPermissions(role: string | null | undefined): ProjectPermissions {
  const edit = can(role, "editor");
  return { canView: can(role, "viewer"), canImport: edit, canGenerate: edit, canReview: edit, canRun: edit, canAdmin: can(role, "admin") };
}
