/**
 * Query keys in one place, so invalidation after a mutation names exactly what it
 * touched. Everything inside a project starts with ["p", projectId], so leaving or
 * deleting a project drops all of it at once.
 */
export const qk = {
  me: ["auth", "me"] as const,
  publicSettings: ["settings", "public"] as const,
  adminSettings: ["settings", "admin"] as const,
  system: ["system"] as const,
  users: ["users"] as const,
  audit: (action?: string) => ["audit", { action }] as const,

  orgs: ["orgs"] as const,
  org: (oid: string) => ["org", oid] as const,
  orgMembers: (oid: string) => ["org", oid, "members"] as const,
  orgAudit: (oid: string, action?: string) => ["org", oid, "audit", { action }] as const,

  projects: ["projects"] as const,
  project: (pid: string) => ["p", pid] as const,
  members: (pid: string) => ["p", pid, "members"] as const,
  apiKeys: (pid: string) => ["p", pid, "api-keys"] as const,
  providers: (pid: string) => ["p", pid, "providers"] as const,

  overview: (pid: string) => ["p", pid, "overview"] as const,
  usage: (pid: string, days: number) => ["p", pid, "usage", days] as const,

  imports: (pid: string) => ["p", pid, "imports"] as const,
  import: (pid: string, iid: string) => ["p", pid, "import", iid] as const,
  analysis: (pid: string) => ["p", pid, "analysis"] as const,
  files: (pid: string, iid: string) => ["p", pid, "files", iid] as const,
  file: (pid: string, iid: string, path: string) => ["p", pid, "file", iid, path] as const,
  units: (pid: string, iid: string, filters: object = {}) => ["p", pid, "units", iid, filters] as const,
  unit: (pid: string, iid: string, uid: string) => ["p", pid, "unit", iid, uid] as const,

  tests: (pid: string, filters: object = {}) => ["p", pid, "tests", filters] as const,
  testsAll: (pid: string) => ["p", pid, "tests"] as const,
  test: (pid: string, tid: string) => ["p", pid, "test", tid] as const,
  generations: (pid: string) => ["p", pid, "generations"] as const,
  generation: (pid: string, gid: string) => ["p", pid, "generation", gid] as const,

  runs: (pid: string, filters: object = {}) => ["p", pid, "runs", filters] as const,
  runsAll: (pid: string) => ["p", pid, "runs"] as const,
  run: (pid: string, rid: string) => ["p", pid, "run", rid] as const,
  runCoverage: (pid: string, rid: string) => ["p", pid, "run-coverage", rid] as const,
  coverage: (pid: string) => ["p", pid, "coverage"] as const,

  pulls: (pid: string) => ["p", pid, "pulls"] as const,
  pull: (pid: string, prid: string) => ["p", pid, "pull", prid] as const,
  specs: (pid: string) => ["p", pid, "specs"] as const,
  spec: (pid: string, sid: string) => ["p", pid, "spec", sid] as const,
  reports: (pid: string) => ["p", pid, "reports"] as const,
  webhooks: (pid: string) => ["p", pid, "webhooks"] as const,
  deliveries: (pid: string, wid: string) => ["p", pid, "deliveries", wid] as const,
  projectAudit: (pid: string, filters: object = {}) => ["p", pid, "audit", filters] as const,
};

/** How long data stays fresh before a background refetch, by kind. */
export const STALE = {
  /** Something in motion (an import, a generation or a run). */
  live: 2_000,
  /** Lists that change when someone acts: refetched on focus and after mutations. */
  list: 15_000,
  /** One record being looked at. */
  detail: 10_000,
  /** Settings and catalogs that rarely change. */
  config: 60_000,
  /** A finished run, an import's files: they never change. */
  static: 300_000,
} as const;
