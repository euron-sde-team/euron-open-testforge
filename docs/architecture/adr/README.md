# Architecture decision records

Decisions a newcomer would question, with the context and the alternatives.

| ADR | Decision |
| --- | --- |
| [0001](0001-unprivileged-nsjail-sandbox-service.md) | Execute every test in nsjail inside an unprivileged sandbox service the worker calls over signed HTTP |
| [0002](0002-rlimits-not-cgroups.md) | Enforce run limits with rlimits and one run per sandbox process, not cgroups |
| [0003](0003-assertion-check-before-a-test-is-shown.md) | Refuse a generated test with no real, reachable, grounded assertion before anyone sees it |
| [0004](0004-static-analysis-never-executes-code.md) | Analyze source statically: `ast` for Python, a masking lexer for JavaScript and TypeScript |
| [0005](0005-postgres-job-queue.md) | A PostgreSQL job queue with leases, not Celery or a Redis queue |
| [0006](0006-github-archives-not-git-clone.md) | Import GitHub repositories as the tarball of one commit, never a git clone |
| [0007](0007-mit-licence.md) | MIT licence, although the brief suggested Apache 2.0 |
| [0008](0008-one-package-two-images.md) | One Python package for every role, two images |
| [0009](0009-no-proc-in-the-sandbox.md) | No `/proc` inside the sandbox, and a Node shim for the one call that needs it |
