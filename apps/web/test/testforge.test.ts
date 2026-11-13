import { describe, expect, it } from "vitest";

import { buildTree, formatRanges, highlightCode, highlightLine, inRanges, languageOf, readChangedFiles, readCoverageFiles, readRanges, toRanges } from "@/lib/code";
import {
  failureTitle,
  hasComparison,
  operatorWords,
  readCounts,
  readFailure,
  readLimits,
  refusalText,
  sandboxRefusal,
} from "@/lib/failure";
import { formatMemoryKb, formatSeconds, shortSha } from "@/lib/format";
import { nextStep, type StepInput } from "@/lib/next-step";
import {
  coverageTone,
  importStep,
  inFlight,
  limitExplanation,
  limitLabel,
  outcomeLabel,
  runLabel,
  runStatusText,
  runTone,
  testKindLabel,
  testStatusTone,
  unitTestState,
} from "@/lib/status";

/** The split_bill failure exactly as the API stores it for the Shop API demo run. */
const SPLIT_BILL = {
  kind: "assertion",
  line: 11,
  actual: "[33.33, 33.33, 33.33]",
  expected: "[33.34, 33.33, 33.33]",
  operator: "==",
  expression: "assert split_bill(100.0, 3) == [33.34, 33.33, 33.33]",
  message: "assert [33.33, 33.33, 33.33] == [33.34, 33.33, 33.33]",
  explanation: "test_split_bill_example_2 failed: the code returned [33.33, 33.33, 33.33].",
};

describe("run status and limit labels", () => {
  it("names every run status in words", () => {
    expect(runLabel("passed")).toBe("Passed");
    expect(runLabel("limit_exceeded")).toBe("Limit crossed");
    expect(runLabel(null)).toBe("No runs yet");
  });
  it("names the limit a run crossed", () => {
    expect(runStatusText("limit_exceeded", "wall_clock")).toBe("Limit crossed: Wall clock");
    expect(runStatusText("limit_exceeded", "memory")).toBe("Limit crossed: Memory");
    expect(runStatusText("failed", null)).toBe("Failed");
  });
  it("labels and explains each limit, with a fallback for an unknown one", () => {
    expect(limitLabel("cpu")).toBe("CPU time");
    expect(limitLabel("output")).toBe("Output size");
    expect(limitLabel("nope")).toBe("A limit");
    expect(limitExplanation("wall_clock")).toMatch(/time ran out/);
    expect(limitExplanation(undefined)).toMatch(/crossed one of its limits/);
  });
  it("tones a run so a crossed limit is a warning, not a pass", () => {
    expect(runTone("passed")).toBe("success");
    expect(runTone("failed")).toBe("danger");
    expect(runTone("limit_exceeded")).toBe("warning");
    expect(runTone("whatever")).toBe("neutral");
  });
  it("treats queued, running, pending and analyzing as in flight", () => {
    for (const s of ["queued", "running", "pending", "analyzing"]) expect(inFlight(s)).toBe(true);
    for (const s of ["passed", "failed", "ready", "done", null]) expect(inFlight(s)).toBe(false);
  });
  it("labels tests, outcomes and kinds", () => {
    expect(testStatusTone("accepted")).toBe("success");
    expect(testStatusTone("proposed")).toBe("info");
    expect(outcomeLabel(null)).toBe("Not run yet");
    expect(testKindLabel("edge")).toBe("Edge case");
    expect(testKindLabel("custom")).toBe("custom");
  });
  it("tells an untested unit from one only generated tests cover", () => {
    expect(unitTestState({ referenced_by_tests: false, covered_percent: null })).toBe("untested");
    expect(unitTestState({ referenced_by_tests: false, covered_percent: 0 })).toBe("untested");
    expect(unitTestState({ referenced_by_tests: false, covered_percent: 75 })).toBe("generated-only");
    expect(unitTestState({ referenced_by_tests: true, covered_percent: 0 })).toBe("referenced");
  });
  it("tracks an import's progress in three steps", () => {
    expect(importStep("pending")).toBe(0);
    expect(importStep("analyzing")).toBe(1);
    expect(importStep("ready")).toBe(2);
    expect(importStep("failed")).toBe(2);
  });
  it("tones coverage: 80% good, under 50% bad, missing neutral", () => {
    expect(coverageTone(92.31)).toBe("success");
    expect(coverageTone(74.36)).toBe("warning");
    expect(coverageTone(9.89)).toBe("danger");
    expect(coverageTone(null)).toBe("neutral");
  });
});

describe("failure display", () => {
  it("reads the split_bill failure with actual and expected side by side", () => {
    const f = readFailure(SPLIT_BILL);
    expect(f).not.toBeNull();
    expect(hasComparison(f)).toBe(true);
    expect(f?.actual).toBe("[33.33, 33.33, 33.33]");
    expect(f?.expected).toBe("[33.34, 33.33, 33.33]");
    expect(f?.expression).toContain("split_bill(100.0, 3)");
    expect(f?.line).toBe(11);
    expect(failureTitle(f!)).toBe("An assertion failed");
  });
  it("returns null for a case that did not fail", () => {
    expect(readFailure(null)).toBeNull();
    expect(readFailure({})).toBeNull();
  });
  it("tolerates missing and odd fields instead of crashing", () => {
    const f = readFailure({ kind: "strange", actual: 5, expected: { a: 1 }, line: "x" });
    expect(f?.kind).toBe("error");
    expect(f?.actual).toBe("5");
    expect(f?.expected).toBe('{"a":1}');
    expect(f?.line).toBeNull();
    expect(f?.explanation).toBe("The test failed without a message.");
  });
  it("puts an operator into words for the expected value", () => {
    expect(operatorWords("==")).toBe("expected to equal");
    expect(operatorWords(">=")).toBe("expected to be at least");
    expect(operatorWords("~=")).toBe("expected (~=)");
    expect(operatorWords(null)).toBe("expected");
  });
  it("recognizes a network call the sandbox refused", () => {
    const f = readFailure({ kind: "error", message: "socket.gaierror: [Errno -3] Temporary failure in name resolution" });
    expect(sandboxRefusal(f)).toBe("network");
    expect(sandboxRefusal(readFailure({ kind: "error", message: "Error: getaddrinfo ENOTFOUND payments.internal" }))).toBe("network");
    expect(refusalText("network").title).toBe("Network access refused");
  });
  it("recognizes a host file and credentials read the sandbox refused", () => {
    const passwd = readFailure({ kind: "error", message: "FileNotFoundError: [Errno 2] No such file or directory: '/etc/passwd'" });
    expect(sandboxRefusal(passwd)).toBe("file");
    const creds = readFailure({ kind: "error", message: "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/.aws/credentials'" });
    expect(sandboxRefusal(creds)).toBe("credentials");
  });
  it("does not call a real bug a sandbox refusal", () => {
    expect(sandboxRefusal(readFailure(SPLIT_BILL))).toBeNull();
    expect(sandboxRefusal(readFailure({ kind: "error", message: "ValueError: people must be at least 1" }))).toBeNull();
    expect(sandboxRefusal(null)).toBeNull();
  });
  it("reads a run's limits and count maps", () => {
    expect(readLimits({ cpu_s: 60, wall_s: 8, memory_mb: 1024, output_bytes: 4000000 })).toEqual({ cpu_s: 60, wall_s: 8, memory_mb: 1024, output_bytes: 4000000 });
    expect(readLimits(null)).toEqual({ cpu_s: null, wall_s: null, memory_mb: null, output_bytes: null });
    expect(readCounts({ accepted: 22, proposed: 6, bad: "x" })).toEqual({ accepted: 22, proposed: 6 });
  });
});

describe("code helpers", () => {
  it("reads and words line ranges", () => {
    expect(readRanges([[28, 38], [40, 40], 7, "x"])).toEqual([[28, 38], [40, 40], [7, 7]]);
    expect(formatRanges([[28, 38], [40, 40]])).toBe("28 to 38, 40");
    expect(formatRanges([])).toBe("none");
    expect(formatRanges([[1, 1], [3, 3], [5, 5]], 2)).toBe("1, 3 and 1 more");
  });
  it("folds lines into ranges and checks membership", () => {
    expect(toRanges([7, 1, 2, 3, 3])).toEqual([[1, 3], [7, 7]]);
    expect(inRanges(35, [[34, 45]])).toBe(true);
    expect(inRanges(46, [[34, 45]])).toBe(false);
  });
  it("reads coverage files and a pull request's changed files", () => {
    const files = readCoverageFiles([{ path: "app/cart.py", missing: [[31, 33]], percent: 85.71, lines_total: 21, lines_covered: 18 }, { nope: 1 }]);
    expect(files).toEqual([{ path: "app/cart.py", percent: 85.71, linesTotal: 21, linesCovered: 18, missing: [[31, 33]] }]);
    const changed = readChangedFiles([{ path: "app/pricing.py", status: "modified", additions: 7, deletions: 2, changed_lines: [[35, 35], [39, 40]] }]);
    expect(changed[0]).toMatchObject({ path: "app/pricing.py", additions: 7, deletions: 2, changed: [[35, 35], [39, 40]], previousPath: null });
    expect(readChangedFiles("bad")).toEqual([]);
  });
  it("builds a file tree with folders first", () => {
    const tree = buildTree(["README.md", "app/main.py", "app/pricing.py", "tests/test_pricing.py"]);
    expect(tree.map((n) => n.name)).toEqual(["app", "tests", "README.md"]);
    expect(tree[0]?.children.map((n) => n.path)).toEqual(["app/main.py", "app/pricing.py"]);
  });
  it("detects the language of a path", () => {
    expect(languageOf("app/x.py")).toBe("python");
    expect(languageOf("src/a.test.ts")).toBe("javascript");
    expect(languageOf("README.md")).toBeNull();
  });
  it("highlights Python keywords, strings, numbers, calls and comments", () => {
    const t = highlightLine('def f(x): return split_bill(100.0, "a")  # note', "python");
    const types = (type: string) => t.filter((x) => x.type === type).map((x) => x.text);
    expect(types("keyword")).toEqual(["def", "return"]);
    expect(types("function")).toEqual(["f", "split_bill"]);
    expect(types("number")).toEqual(["100.0"]);
    expect(types("string")).toEqual(['"a"']);
    expect(types("comment")).toEqual(["# note"]);
    expect(t.map((x) => x.text).join("")).toBe('def f(x): return split_bill(100.0, "a")  # note');
  });
  it("carries a docstring across lines and closes it", () => {
    const lines = highlightCode('def f():\n    """Split a bill.\n\n    >>> f()\n    """\n    return 1', "python");
    expect(lines[1]?.at(-1)?.type).toBe("string");
    expect(lines[3]).toEqual([{ type: "string", text: "    >>> f()" }]);
    expect(lines[4]).toEqual([{ type: "string", text: '    """' }]);
    expect(lines[5]?.find((t) => t.type === "keyword")?.text).toBe("return");
    expect(highlightCode('x = """one line"""\ny = 2', "python")[1]?.find((t) => t.type === "number")?.text).toBe("2");
  });
  it("highlights TypeScript and leaves unknown languages plain", () => {
    const t = highlightLine("expect(slugify('A b')).toBe('a-b'); // ok", "typescript");
    expect(t.find((x) => x.type === "keyword")?.text).toBe("expect");
    expect(t.some((x) => x.type === "comment" && x.text === "// ok")).toBe(true);
    expect(highlightLine("<b>hi</b>", null)).toEqual([{ type: "plain", text: "<b>hi</b>" }]);
  });
});

describe("next step on the overview", () => {
  const base: StepInput = { importStatus: "ready", untested: 0, proposed: 0, accepted: 5, runsTotal: 3, latestStatus: "passed", coverage: 90 };
  it("asks for code first", () => {
    expect(nextStep({ ...base, importStatus: null }).id).toBe("import");
    expect(nextStep({ ...base, importStatus: "failed" }).id).toBe("import");
    expect(nextStep({ ...base, importStatus: "analyzing" }).id).toBe("analyzing");
  });
  it("then review, generate and run, in that order", () => {
    expect(nextStep({ ...base, proposed: 6 }).title).toBe("Review 6 proposed tests");
    expect(nextStep({ ...base, proposed: 1 }).title).toBe("Review 1 proposed test");
    expect(nextStep({ ...base, accepted: 0 }).id).toBe("generate");
    expect(nextStep({ ...base, runsTotal: 0 }).id).toBe("run");
  });
  it("points at a failing run, then untested code, then says done", () => {
    expect(nextStep({ ...base, latestStatus: "limit_exceeded" }).id).toBe("fix");
    expect(nextStep({ ...base, untested: 2 }).title).toBe("2 units are still untested");
    expect(nextStep(base).id).toBe("done");
  });
});

describe("measurement formatting", () => {
  it("formats memory, seconds and commit hashes", () => {
    expect(formatMemoryKb(64744)).toBe("63.2 MB");
    expect(formatMemoryKb(null)).toBe("n/a");
    expect(formatSeconds(8)).toBe("8 s");
    expect(formatSeconds(120)).toBe("120 s");
    expect(formatSeconds(3600)).toBe("60m 0s");
    expect(shortSha("887ba8d9cf5e75edeeb69f01897ddda424a00af0")).toBe("887ba8d");
  });
});
