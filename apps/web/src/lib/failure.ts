/**
 * Readers for the parts of API responses the OpenAPI document types as a free-form
 * object (a test case's `failure`, a run's `limits`). The API writes them from one place
 * (bugs/explain.py, runs/service.py); these turn them into a shape the UI can rely on,
 * tolerating missing fields instead of crashing on them.
 */

export type FailureKind = "assertion" | "error" | "no_exception" | "limit" | "refused";

export interface FailureView {
  kind: FailureKind;
  actual: string | null;
  expected: string | null;
  operator: string | null;
  expression: string | null;
  explanation: string;
  message: string;
  line: number | null;
  limit: string | null;
}

const KINDS: readonly FailureKind[] = ["assertion", "error", "no_exception", "limit", "refused"];

function str(v: unknown): string | null {
  if (v == null) return null;
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function obj(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

/** A failure object as the API stores it, or null when the case did not fail. */
export function readFailure(raw: unknown): FailureView | null {
  if (raw == null) return null;
  const f = obj(raw);
  if (!Object.keys(f).length) return null;
  const kind = KINDS.includes(f.kind as FailureKind) ? (f.kind as FailureKind) : "error";
  const line = typeof f.line === "number" && Number.isFinite(f.line) ? f.line : null;
  return {
    kind,
    actual: str(f.actual),
    expected: str(f.expected),
    operator: str(f.operator),
    expression: str(f.expression),
    explanation: str(f.explanation) ?? str(f.message) ?? "The test failed without a message.",
    message: str(f.message) ?? "",
    line,
    limit: str(f.limit),
  };
}

const KIND_TITLE: Record<FailureKind, string> = {
  assertion: "An assertion failed",
  error: "The test stopped with an error",
  no_exception: "The expected error was not raised",
  limit: "The run hit a sandbox limit",
  refused: "The sandbox refused access",
};

export function failureTitle(f: FailureView): string {
  return KIND_TITLE[f.kind];
}

/** Whether actual and expected can be shown side by side. */
export function hasComparison(f: FailureView | null): f is FailureView & { actual: string; expected: string } {
  return !!f && f.actual != null && f.expected != null;
}

const OPERATOR_WORDS: Record<string, string> = {
  "==": "equal",
  "!=": "differ from",
  "<": "be less than",
  "<=": "be at most",
  ">": "be greater than",
  ">=": "be at least",
  in: "be in",
  "not in": "not be in",
  is: "be",
  "is not": "not be",
  toBe: "be",
  toEqual: "equal",
  toStrictEqual: "equal",
};

/** "expected to equal", for the label over the expected value. */
export function operatorWords(op: string | null | undefined): string {
  if (!op) return "expected";
  const w = OPERATOR_WORDS[op];
  return w ? `expected to ${w}` : `expected (${op})`;
}

export type Refusal = "network" | "file" | "credentials" | null;

/**
 * Whether a failure is the sandbox refusing something rather than a bug in the code: a
 * network call that found no network, or a read of a file outside the run's workspace.
 * The run itself is fine; this is the isolation working.
 */
export function sandboxRefusal(f: FailureView | null): Refusal {
  if (!f) return null;
  const text = `${f.message}\n${f.expression ?? ""}`;
  // Node's error codes are upper case words; matching them without case would find
  // "ENOTFOUND" inside "FileNotFoundError".
  if (/gaierror|name resolution|network is unreachable|connection refused|getaddrinfo|no route to host/i.test(text) || /\b(ENETUNREACH|ENOTFOUND|EAI_AGAIN|ECONNREFUSED)\b/.test(text)) {
    return "network";
  }
  if (/\.aws|credentials|\.ssh|id_rsa|\.netrc|\.docker\/config|AWS_SECRET|GITHUB_TOKEN/i.test(text) && /FileNotFound|ENOENT|No such file|EACCES|Permission denied|KeyError|undefined/i.test(text)) {
    return "credentials";
  }
  if (/(FileNotFoundError|PermissionError|ENOENT|EACCES|No such file or directory|Permission denied)/i.test(f.message) && /['"]\/(etc|root|home|var|proc|sys|usr|tmp|run)\b/.test(f.message)) {
    return "file";
  }
  return null;
}

const REFUSAL_TEXT: Record<Exclude<Refusal, null>, { title: string; body: string }> = {
  network: {
    title: "Network access refused",
    body: "The test tried to reach a host. The sandbox has no network interface, so the lookup failed before any packet left the run.",
  },
  file: {
    title: "Host file access refused",
    body: "The test tried to read a file outside its own workspace. The sandbox sees only this run's files, so the host file does not exist there.",
  },
  credentials: {
    title: "Credentials not available",
    body: "The test looked for credentials. The sandbox runs with no credentials and no home directory from the host, so there was nothing to read.",
  },
};

export function refusalText(r: Exclude<Refusal, null>): { title: string; body: string } {
  return REFUSAL_TEXT[r];
}

export interface RunLimits {
  cpu_s: number | null;
  wall_s: number | null;
  memory_mb: number | null;
  output_bytes: number | null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** The limits a run had, as stored on the run. */
export function readLimits(raw: unknown): RunLimits {
  const l = obj(raw);
  return { cpu_s: num(l.cpu_s), wall_s: num(l.wall_s), memory_mb: num(l.memory_mb), output_bytes: num(l.output_bytes) };
}

/** A count map such as `{"accepted": 22, "proposed": 6}`; anything that is not a number is dropped. */
export function readCounts(raw: unknown): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(obj(raw))) {
    const n = num(v);
    if (n != null) out[k] = n;
  }
  return out;
}
