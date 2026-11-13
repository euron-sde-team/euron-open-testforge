// TestForge's Vitest reporter. It runs inside the sandbox, under the jail's own Node.
//
// It records, from the one execution that ran the tests: every test's outcome, duration
// and location, and for a failed expectation the actual and expected values exactly as
// Vitest captured them (TestError.actual / TestError.expected), so the failure explanation
// needs no second run. A line per event goes to events.jsonl as it happens, so when the
// sandbox stops the run at a limit the worker still knows which tests finished and which
// one was running. It writes only under $TESTFORGE_OUT (/box/.testforge).
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const OUT = process.env.TESTFORGE_OUT || "/box/.testforge";
const ROOT = process.env.TESTFORGE_ROOT || "/box";
const MAX_TEXT = 4000;
const MAX_REPR = 600;
const started = Date.now();

function clip(text, max) {
  const s = String(text ?? "");
  return s.length <= max ? s : s.slice(0, max - 3) + "...";
}

function event(kind, data) {
  const line = JSON.stringify({ event: kind, t: (Date.now() - started) / 1000, ...data });
  appendFileSync(join(OUT, "events.jsonl"), line + "\n");
}

function nodeid(testCase) {
  return `${relative(ROOT, testCase.module.moduleId)}::${testCase.fullName}`;
}

function failureOf(errors, file) {
  const err = (errors && errors[0]) || {};
  const failure = {
    message: clip(err.message, MAX_TEXT),
    name: err.name || "",
    path: file,
    line: null,
    text: clip(err.stack || err.message, MAX_TEXT),
  };
  const match = /:(\d+):\d+\)?\s*$/m.exec(
    String(err.stack || "")
      .split("\n")
      .find((l) => l.includes(file)) || ""
  );
  if (match) failure.line = Number(match[1]);
  if ("actual" in err || "expected" in err) {
    failure.compare = {
      operator: err.operator || "",
      left: clip(err.actual, MAX_REPR),
      right: clip(err.expected, MAX_REPR),
      left_type: "",
      right_type: "",
    };
  }
  return failure;
}

export default class TestForgeReporter {
  constructor() {
    this.tests = [];
    this.collectErrors = [];
    mkdirSync(OUT, { recursive: true });
  }

  onTestCaseReady(testCase) {
    event("start", { nodeid: nodeid(testCase) });
  }

  onTestCaseResult(testCase) {
    const result = testCase.result();
    const file = relative(ROOT, testCase.module.moduleId);
    const state = result.state;
    const outcome = state === "passed" ? "passed" : state === "failed" ? "failed" : "skipped";
    const entry = {
      nodeid: nodeid(testCase),
      file,
      line: (testCase.location && testCase.location.line) || 0,
      name: testCase.fullName,
      outcome,
      duration_ms: Math.round(((testCase.diagnostic() || {}).duration || 0) * 1000) / 1000,
    };
    if (outcome === "failed") entry.failure = failureOf(result.errors, file);
    this.tests.push(entry);
    event("result", entry);
  }

  onTestModuleEnd(testModule) {
    // A file that fails to load (syntax error, missing import) has no test cases.
    const errors = testModule.errors();
    if (errors && errors.length) {
      const error = {
        nodeid: relative(ROOT, testModule.moduleId),
        text: clip(errors.map((e) => e.stack || e.message).join("\n"), MAX_TEXT),
      };
      this.collectErrors.push(error);
      event("collect_error", error);
    }
  }

  onTestRunEnd(_modules, unhandledErrors, reason) {
    for (const e of unhandledErrors || []) {
      this.collectErrors.push({ nodeid: "", text: clip(e.stack || e.message, MAX_TEXT) });
    }
    const failed = this.tests.some((t) => t.outcome === "failed") || this.collectErrors.length;
    writeFileSync(
      join(OUT, "report.json"),
      JSON.stringify({
        framework: "vitest",
        exitstatus: failed ? 1 : 0,
        reason: reason || "",
        tests: this.tests,
        collect_errors: this.collectErrors,
        duration_s: (Date.now() - started) / 1000,
      })
    );
  }
}
