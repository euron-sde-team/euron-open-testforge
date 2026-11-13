/** Plain-words explanations for TestForge vocabulary, shown as inline hints. */
export const GLOSSARY = {
  sandbox:
    "Every run, of a generated test or of the project's own tests, executes in a fresh sandbox: no network interface, no credentials, only this run's files, and fixed CPU, memory, output and time limits.",
  refused:
    "A generated test that had no meaningful assertion (nothing that could ever fail) is refused before anyone sees it or runs it. A test that cannot fail proves nothing.",
  assertion: "The line in a test that checks a value. TestForge shows each assertion it found, so you can see what a test really proves.",
  coverage:
    "The share of the code's statement lines that ran during the tests, measured by coverage.py or Istanbul inside the sandbox. Real numbers from a real run, not an estimate.",
  untested: "A function, method, class or route that no test refers to. These are the first places to generate tests for.",
  limit:
    "The most a run may use: CPU seconds, wall clock seconds, memory and output. A run that crosses one is stopped and reported with the limit it crossed.",
  passRate: "The share of finished runs that passed, across every run of this project.",
  provider:
    "The model that writes tests from the analyzed source. Bring your own key for OpenAI, Anthropic, Gemini, Ollama or any OpenAI-compatible endpoint; the built-in mock needs none.",
  apiKey:
    "For other applications, the SDK and testforge-cli in CI. A key belongs to one project; its scopes say what it may do (read, generate, execute, manage).",
  pullScope:
    "TestForge diffs the pull request's head against its base and keeps the functions and routes whose lines changed, so generation covers only what the change touches.",
  apiTests: "Tests generated from an OpenAPI document: each documented operation is called at least once and its status code and response shape are checked.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
