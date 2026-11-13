# Security Policy

TestForge executes code it did not write: tests written by a model, uploaded projects and
their own test suites. Its promise is that none of that code can reach the network, the
platform's credentials or another project's files. We take reports seriously and respond
quickly.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.x (latest minor) | Yes |
| Older minors | No |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include:

- the affected component (`apps/api`, the sandbox service or its image, `apps/web`,
  `sdk/python`, `infra/terraform/...`) and version or commit,
- a description of the issue and its impact,
- steps to reproduce, or a proof of concept (for a sandbox escape, the test file or
  project ZIP, and whether it ran through an upload, a GitHub import or a generated test),
- any suggested mitigation.

What to expect:

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical and high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Scope

In scope: the code in this repository and the infrastructure it provisions with its
default settings. **Sandbox escapes are the reports we want most.** We are especially
interested in:

- **any way out of the sandbox**: a run that reaches the network (including DNS or the
  cloud metadata service), reads or writes files outside its workspace, sees the toolchain
  as writable, another run's workspace or the service's code, reads `SANDBOX_SECRET` or any
  other credential, keeps running after its run ended or its limit was crossed, affects
  another run's results, or makes the sandbox service hand back a file it should not,
- a run that crosses a CPU, memory, output, process or wall clock limit without being
  stopped, or is reported with the wrong limit,
- project code executed anywhere but the sandbox: during an import, archive unpacking,
  static analysis, the assertion check or report generation,
- a generated test with no real assertion that passes the assertion check,
- a crafted ZIP or repository archive that writes outside memory, escapes its caps, or
  smuggles a link or device into a workspace,
- reading or changing another organization's projects, imports, tests, runs or reports;
  an API key acting outside its project or scopes,
- recovering a secret (`SESSION_SECRET`, `API_KEY_PEPPER`, `SANDBOX_SECRET`, the master
  key, a provider key, a GitHub token, a webhook secret) from the API, the sandbox, logs,
  reports or the database,
- authentication or authorization bypasses, CSRF, forged GitHub webhooks or sandbox
  requests, and requests from the platform reaching an address they should not
  (instance metadata) through provider, GitHub or webhook URLs,
- a change to the append-only audit log through the application.

Out of scope:

- **Known limits of namespace sandboxes.** A kernel vulnerability reached through user
  namespaces is in scope if you can show it against the default hardening, but the general
  observation that namespaces are kernel attack surface is documented in
  [docs/architecture/sandbox.md](docs/architecture/sandbox.md).
- **The demo seed.** `make demo` creates well-known demo accounts with the password from
  your local `.env`, on purpose, and its "Sandbox checks" project contains escape attempts
  by design.
- **The mock services** (`apps/api/src/mockai`), a test fixture never deployed to AWS.
- Source sent to a model provider an admin configured: that is the feature.
- Project admins pointing model providers at private addresses when
  `PROVIDER_ALLOW_PRIVATE` is on (the default, for local models).
- Findings that require a compromised host, compromised AWS account, or leaked deployment
  secrets.
- Denial of service through resource exhaustion of a deployment you operate yourself.

## Hardening checklist for operators

See [docs/architecture/security.md](docs/architecture/security.md#operator-checklist).
