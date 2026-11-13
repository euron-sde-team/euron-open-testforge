# Quickstart (local)

Everything runs in Docker on one machine. No AWS account and no model API key: the demo
uses a deterministic mock model and a mock GitHub.

## Prerequisites

- Docker with Compose v2 (Docker Desktop, or Docker Engine on Linux with unprivileged user
  namespaces enabled, which is the default on current distributions)
- `make`, `bash`, `openssl`
- A few GB of disk for the images (the sandbox image carries nsjail, Python with pytest and
  coverage, and Node with Vitest)

## Start

```bash
git clone https://github.com/euron-sde-team/euron-open-testforge.git
cd euron-open-testforge
make up      # Postgres, Redis, Mailpit, Floci (provisioned by Terraform), mock services,
             # sandbox, api, worker, scheduler, web
make demo    # people, three projects imported, tests generated and run in the sandbox
```

`make up` generates `deploy/compose/.env` with random local secrets the first time, builds
the images and waits until everything is healthy. The first build of the sandbox image
compiles nsjail and installs both test toolchains; on a slow route to Debian's mirrors set
`TESTFORGE_APT_MIRROR` ([troubleshooting](troubleshooting.md)).

`make demo` really imports, analyzes, generates and runs everything through the API, so it
takes a few minutes. It prints the sign-in details. Open http://localhost:5610.

| Who | Email | Role |
| --- | --- | --- |
| Maya Chen | `maya.chen@example.com` | Owner of the Acme Retail organization: admin of every project |
| Arjun Mehta | `arjun.mehta@example.com` | Editor of Shop API: imports, generates, reviews and runs |
| Sofia Lopez | `sofia.lopez@example.com` | Viewer of Shop API: reads everything, changes nothing |

All demo accounts share the printed password (`TESTFORGE_DEMO_PASSWORD` in
`deploy/compose/.env`). Mail goes to Mailpit at http://localhost:5625; the API's
interactive docs are at http://localhost:5630/docs.

## Five minutes

1. Sign in as Maya and open **Shop API**. The overview shows accepted tests, refused tests,
   the latest runs and the coverage trend.
2. Open **Runs** and the failing run: `split_bill` fails, and the failure explains which
   assertion failed, what the code returned and what the test expected, from that one run.
3. Open **Tests**: every generated test with its code, the assertions TestForge found in
   it and a plain description. Generate more for the untested units listed under
   **Source**, then accept or discard them.
4. Open **Pull requests**: pull request #12 lists its changed files and the functions
   they touch, and tests generated only for those.
5. Open the **Sandbox checks** project: its uploaded tests try to reach the network, read
   files outside their workspace and run forever. The runs show every attempt refused and
   the hanging suite stopped at its wall clock limit.

[walkthrough.md](walkthrough.md) goes through the demo screen by screen.

## Your own code

- **A ZIP**: on a project's overview, **Import code**, then upload a ZIP of a Python or
  JavaScript and TypeScript project.
- **A GitHub repository**: set `TESTFORGE_GITHUB_API_URL=https://api.github.com` in
  `deploy/compose/.env` and `make up` again; for a private repository add a token in the
  project's settings.
- **A real model**: add a provider in the project's settings (OpenAI, Anthropic, Gemini,
  Ollama or any OpenAI-compatible endpoint) and make it the default. Keys are sealed.

## From a script or CI

```bash
pip install ./sdk/python
export TESTFORGE_URL=http://localhost:5630 TESTFORGE_API_KEY=tfk_...   # a project API key
testforge-cli import-github owner/repo
testforge-cli generate
testforge-cli accept --all
testforge-cli run            # exits 1 unless every test passed
```

## Stop

```bash
make down    # stops the stack and deletes its data
```

## Next

- [Configuration](configuration.md)
- [Testing](testing.md)
- [Architecture](../architecture/HLD.md)
