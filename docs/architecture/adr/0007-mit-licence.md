# ADR-0007: MIT licence

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

The project brief suggested Apache 2.0. Every project in the Euron open-source programme
is MIT licensed, so that companies, teams and individuals can adopt and adapt it with the
fewest conditions. Comparable tools hold back isolation, bring-your-own-model or air-gapped
use for a paid tier; TestForge's position is that nothing is held back.

## Decision

MIT, copyright ENGAGESPHERE TECHNOLOGY PRIVATE LIMITED and the Euron Open TestForge
contributors. Third-party components keep their own licences: nsjail (Apache 2.0) is built
into the sandbox image as a separate program, and the test toolchains (pytest, coverage.py,
Vitest, Istanbul and the libraries in the toolchain virtualenv) are installed in the image,
not linked into TestForge's code.

## Consequences

**Good**
- The simplest terms to adopt, the same as the rest of the programme; the sandbox, every
  provider adapter and the GitHub integration are in the open core.

**Bad / caveats**
- Someone can run a modified TestForge as a service without sharing the changes. That is
  accepted.
