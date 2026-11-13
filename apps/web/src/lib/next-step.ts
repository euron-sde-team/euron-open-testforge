/**
 * The one thing a project most needs next, for the overview's call to action. Pure, so it
 * is unit tested: given the overview counts, it names the step and where it lives.
 */

export type StepId = "import" | "analyzing" | "generate" | "review" | "run" | "fix" | "cover" | "done";

export interface NextStep {
  id: StepId;
  title: string;
  body: string;
  /** Path under /projects/<id>. */
  href: string;
  action: string;
}

export interface StepInput {
  importStatus: string | null | undefined;
  untested: number;
  proposed: number;
  accepted: number;
  runsTotal: number;
  latestStatus: string | null | undefined;
  coverage: number | null | undefined;
}

export function nextStep(o: StepInput): NextStep {
  if (!o.importStatus || o.importStatus === "failed") {
    return {
      id: "import",
      title: "Import your code",
      body: "Bring in a GitHub repository or a ZIP. TestForge finds its functions, classes and routes, and which of them no test touches.",
      href: "?import=1",
      action: "Import code",
    };
  }
  if (o.importStatus === "pending" || o.importStatus === "analyzing") {
    return { id: "analyzing", title: "Analyzing your code", body: "This takes seconds. The units and coverage gaps appear here when it is done.", href: "/source", action: "Open the source" };
  }
  if (o.proposed > 0) {
    return {
      id: "review",
      title: `Review ${o.proposed} proposed ${o.proposed === 1 ? "test" : "tests"}`,
      body: "Read what each one checks, then accept the ones you trust. Only accepted tests run.",
      href: "/tests?status=proposed",
      action: "Review tests",
    };
  }
  if (o.accepted === 0) {
    return {
      id: "generate",
      title: "Generate your first tests",
      body: "Pick the untested units and TestForge writes tests with real assertions. Tests that could never fail are refused.",
      href: "/source?tab=units&untested=1",
      action: "Generate tests",
    };
  }
  if (o.runsTotal === 0) {
    return { id: "run", title: "Run the accepted tests", body: "They run in the sandbox with no network and no credentials, and you get real coverage.", href: "/runs?start=1", action: "Run tests" };
  }
  if (o.latestStatus === "failed" || o.latestStatus === "error" || o.latestStatus === "limit_exceeded") {
    return {
      id: "fix",
      title: "The latest run did not pass",
      body: "Each failure is explained with the value the code returned and the value the test expected.",
      href: "/runs",
      action: "See the failures",
    };
  }
  if (o.untested > 0) {
    return {
      id: "cover",
      title: `${o.untested} ${o.untested === 1 ? "unit is" : "units are"} still untested`,
      body: "Generate tests for them to close the gaps in coverage.",
      href: "/source?tab=units&untested=1",
      action: "Generate tests",
    };
  }
  return { id: "done", title: "Everything is tested", body: "Every unit has a test and the latest run passed. Import a pull request to test the next change.", href: "/pulls", action: "Pull requests" };
}
