import type {
  CaseOutcome,
  GenerationStatus,
  ImportStatus,
  LimitName,
  RunKind,
  RunStatus,
  TestKind,
  TestStatus,
  UnitKind,
} from "./api/types";

/** The tone a state is drawn in. Always shown with an icon and a word, never by color alone. */
export type Tone = "success" | "warning" | "danger" | "info" | "primary" | "neutral";

const RUN_LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  passed: "Passed",
  failed: "Failed",
  error: "Error",
  limit_exceeded: "Limit crossed",
};

const RUN_TONE: Record<RunStatus, Tone> = {
  queued: "neutral",
  running: "primary",
  passed: "success",
  failed: "danger",
  error: "danger",
  limit_exceeded: "warning",
};

export function runLabel(status: string | null | undefined): string {
  return (status && RUN_LABEL[status as RunStatus]) || "No runs yet";
}

export function runTone(status: string | null | undefined): Tone {
  return (status && RUN_TONE[status as RunStatus]) || "neutral";
}

/** A run, generation or import that has not finished yet (poll it). */
export function inFlight(status: string | null | undefined): boolean {
  return status === "queued" || status === "running" || status === "pending" || status === "analyzing";
}

const LIMIT_LABEL: Record<LimitName, string> = {
  cpu: "CPU time",
  memory: "Memory",
  wall_clock: "Wall clock",
  output: "Output size",
  processes: "Process count",
};

const LIMIT_EXPLAIN: Record<LimitName, string> = {
  cpu: "The tests used more CPU time than the run allows, so the sandbox stopped them.",
  memory: "The tests asked for more memory than the run allows, so the sandbox stopped them.",
  wall_clock: "The run was still going when its time ran out (a test that sleeps, waits or loops forever), so the sandbox stopped it.",
  output: "The tests printed more output than the run allows, so the sandbox stopped them instead of keeping a truncated log.",
  processes: "The tests started more processes than the run allows, so the sandbox stopped them.",
};

export function limitLabel(limit: string | null | undefined): string {
  return (limit && LIMIT_LABEL[limit as LimitName]) || "A limit";
}

export function limitExplanation(limit: string | null | undefined): string {
  return (limit && LIMIT_EXPLAIN[limit as LimitName]) || "The run crossed one of its limits and the sandbox stopped it.";
}

/** "Limit crossed: Wall clock" for a run stopped at a limit, the plain label otherwise. */
export function runStatusText(status: string | null | undefined, limit?: string | null): string {
  if (status === "limit_exceeded") return limit ? `Limit crossed: ${limitLabel(limit)}` : "Limit crossed";
  return runLabel(status);
}

export const RUN_KIND_LABEL: Record<RunKind, string> = {
  generated: "Generated tests",
  project: "Project's own tests",
  all: "Everything",
};

export const RUN_KIND_DESCRIPTION: Record<RunKind, string> = {
  generated: "The accepted tests TestForge wrote.",
  project: "The tests already in the imported code.",
  all: "Both together, for one coverage number.",
};

export function runKindLabel(kind: string): string {
  return RUN_KIND_LABEL[kind as RunKind] ?? kind;
}

const TEST_LABEL: Record<TestStatus, string> = { proposed: "Proposed", accepted: "Accepted", discarded: "Discarded" };
const TEST_TONE: Record<TestStatus, Tone> = { proposed: "info", accepted: "success", discarded: "neutral" };

export function testStatusLabel(status: string): string {
  return TEST_LABEL[status as TestStatus] ?? status;
}

export function testStatusTone(status: string): Tone {
  return TEST_TONE[status as TestStatus] ?? "neutral";
}

export const TEST_KIND_LABEL: Record<TestKind, string> = {
  unit: "Unit",
  edge: "Edge case",
  negative: "Negative",
  api: "API",
};

export const TEST_KIND_DESCRIPTION: Record<TestKind, string> = {
  unit: "The documented behaviour of each function, with exact values.",
  edge: "Boundaries: empty input, zero, the largest and smallest values.",
  negative: "Bad input the code must refuse, checked to raise the right error.",
  api: "Every operation of an imported OpenAPI document: status code and response shape.",
};

export function testKindLabel(kind: string): string {
  return TEST_KIND_LABEL[kind as TestKind] ?? kind;
}

const OUTCOME_LABEL: Record<CaseOutcome, string> = { passed: "Passed", failed: "Failed", error: "Error", skipped: "Skipped" };
const OUTCOME_TONE: Record<CaseOutcome, Tone> = { passed: "success", failed: "danger", error: "danger", skipped: "neutral" };

export function outcomeLabel(outcome: string | null | undefined): string {
  return (outcome && OUTCOME_LABEL[outcome as CaseOutcome]) || "Not run yet";
}

export function outcomeTone(outcome: string | null | undefined): Tone {
  return (outcome && OUTCOME_TONE[outcome as CaseOutcome]) || "neutral";
}

const IMPORT_LABEL: Record<ImportStatus, string> = { pending: "Downloading", analyzing: "Analyzing", ready: "Ready", failed: "Failed" };
const IMPORT_TONE: Record<ImportStatus, Tone> = { pending: "neutral", analyzing: "primary", ready: "success", failed: "danger" };

export function importLabel(status: string): string {
  return IMPORT_LABEL[status as ImportStatus] ?? status;
}

export function importTone(status: string): Tone {
  return IMPORT_TONE[status as ImportStatus] ?? "neutral";
}

/** How far an import has come, for its progress steps: 0 received, 1 analyzing, 2 done. */
export function importStep(status: string): number {
  if (status === "ready" || status === "failed") return 2;
  if (status === "analyzing") return 1;
  return 0;
}

const GEN_LABEL: Record<GenerationStatus, string> = { queued: "Queued", running: "Writing tests", done: "Done", failed: "Failed" };
const GEN_TONE: Record<GenerationStatus, Tone> = { queued: "neutral", running: "primary", done: "success", failed: "danger" };

export function generationLabel(status: string): string {
  return GEN_LABEL[status as GenerationStatus] ?? status;
}

export function generationTone(status: string): Tone {
  return GEN_TONE[status as GenerationStatus] ?? "neutral";
}

export const UNIT_KIND_LABEL: Record<UnitKind, string> = { function: "Function", method: "Method", class: "Class", route: "Route" };

export function unitKindLabel(kind: string): string {
  return UNIT_KIND_LABEL[kind as UnitKind] ?? kind;
}

const LANGUAGE_LABEL: Record<string, string> = { python: "Python", javascript: "JavaScript", typescript: "TypeScript" };
const FRAMEWORK_LABEL: Record<string, string> = {
  pytest: "pytest",
  vitest: "Vitest",
  fastapi: "FastAPI",
  flask: "Flask",
  express: "Express",
  jest: "Jest",
  django: "Django",
};

export function languageLabel(lang: string | null | undefined): string {
  if (!lang) return "Unknown";
  return LANGUAGE_LABEL[lang] ?? lang.charAt(0).toUpperCase() + lang.slice(1);
}

export function frameworkLabel(fw: string | null | undefined): string {
  if (!fw) return "Unknown";
  return FRAMEWORK_LABEL[fw] ?? fw;
}

/** A coverage percentage's tone: 80% and up is good, under 50% needs work. */
export function coverageTone(percent: number | null | undefined): Tone {
  if (percent == null || !Number.isFinite(percent)) return "neutral";
  if (percent >= 80) return "success";
  if (percent >= 50) return "warning";
  return "danger";
}

export type UnitTestState = "untested" | "generated-only" | "referenced";

/**
 * How a unit is tested. `referenced_by_tests` is what static analysis of the repository's
 * own tests found; a unit no test refers to may still be covered by TestForge's generated
 * tests, which is a different (and better) state than not tested at all.
 */
export function unitTestState(u: { referenced_by_tests: boolean; covered_percent: number | null }): UnitTestState {
  if (u.referenced_by_tests) return "referenced";
  return u.covered_percent != null && u.covered_percent > 0 ? "generated-only" : "untested";
}
