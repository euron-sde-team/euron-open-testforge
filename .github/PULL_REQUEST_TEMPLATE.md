## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint typecheck test`
- [ ] `make test-integration` (if the API, the worker, analysis, generation or runs changed)
- [ ] `make test-sandbox` (if the sandbox, its image, the runners or the toolchain changed)
- [ ] `make e2e` (if a user flow or infrastructure changed)
- [ ] `make tf-validate tf-lint tf-security tf-aws-on-floci` (if Terraform changed)

## Checklist

- [ ] Docs updated (README, `docs/`, configuration reference) for any behavior or config change
- [ ] New Alembic revision instead of editing an applied one
- [ ] Code from a project still runs only in the sandbox: no new path executes, imports or evaluates imported or generated code anywhere else (analysis stays static)
- [ ] A sandbox change keeps runs without network and credentials and keeps every limit named; it comes with a hostile test in `tests/sandbox` that tries to break it
- [ ] Every generated test still passes the assertion check before it is stored or shown; a change to the check comes with tests for the new refusals and acceptances
- [ ] Provider keys, GitHub tokens and webhook secrets stay sealed (never logged, never returned by the API)
- [ ] The mock provider still writes the demo and test suites deterministically
- [ ] `make openapi` run if the API changed
- [ ] No secrets, account ids, real hostnames or em/en dashes (`make sanitize` is clean)
- [ ] Security-relevant change? Described the threat and mitigation above
