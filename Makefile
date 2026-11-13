# Euron Open TestForge: developer entry points. `make` lists every target.
SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

COMPOSE_DIR := deploy/compose
FLOCI       := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.floci.yaml
AWS_LOCAL   := docker compose --env-file $(COMPOSE_DIR)/.env -f $(COMPOSE_DIR)/compose.yaml -f $(COMPOSE_DIR)/compose.aws.yaml
API         := cd apps/api &&
WEB         := cd apps/web &&
TF_IMAGE    := hashicorp/terraform:1.16.6
TF_ENVS     := local-floci aws-dev aws-prod
# Use a local terraform when installed, otherwise the pinned container. The container
# mounts all of infra/: the sandbox module reads infra/docker/sandbox-seccomp.json.
TF          := $(shell command -v terraform >/dev/null 2>&1 && echo terraform || echo docker run --rm -v $(CURDIR)/infra:/infra -w /infra/terraform $(TF_IMAGE))
TF_ROOT     := $(shell command -v terraform >/dev/null 2>&1 && echo infra/terraform || echo /infra/terraform)
ENV         ?= aws-dev
# The demo password make env generated; e2e, qa and the seed use it.
DEMO_PW      = $(shell grep -s '^TESTFORGE_DEMO_PASSWORD=' $(COMPOSE_DIR)/.env | cut -d= -f2)
# Optional faster Debian mirror for building the sandbox image (see .env.example).
APT_MIRROR  ?= $(shell grep -s '^TESTFORGE_APT_MIRROR=' $(COMPOSE_DIR)/.env | cut -d= -f2)
SANDBOX_TEST_IMAGE := testforge-sandbox-test:local
# The sandbox suite runs with exactly the hardening the sandbox service gets in Compose
# and on ECS. apps/api is mounted whole: the suite reads the demo projects from src/.
SANDBOX_HARDENING := --cap-drop ALL --security-opt no-new-privileges \
  --security-opt seccomp=$(CURDIR)/infra/docker/sandbox-seccomp.json --read-only \
  --tmpfs /tmp:exec,size=1g,uid=10001,gid=10001 --pids-limit 1024 --memory 3g --cpus 2 \
  --network none

.PHONY: screenshots bench help env up up-aws down logs ps demo admin test test-integration \
        test-sandbox test-matrix e2e qa lint typecheck build openapi sanitize tf-fmt tf-validate \
        tf-lint tf-security tf-aws-on-floci aws-plan clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─── Local ───────────────────────────────────────────────────────────────────

env: ## Generate deploy/compose/.env with random local-only secrets
	@scripts/gen-local-env.sh

up: env ## Start everything on emulated AWS (Floci), provisioned by the same Terraform as production
	TESTFORGE_APT_MIRROR='$(APT_MIRROR)' $(FLOCI) up -d --build --wait
	@echo ""
	@echo "  app        http://localhost:$${TESTFORGE_WEB_PORT:-5610}"
	@echo "  api        http://localhost:$${TESTFORGE_API_PORT:-5630}/docs"
	@echo "  mail       http://localhost:$${TESTFORGE_MAILPIT_PORT:-5625}"
	@echo ""
	@echo "  Next: make demo   (demo projects imported, tests generated and run in the sandbox)"

up-aws: env ## Start the stack against real AWS resources (needs deploy/compose/.env.aws)
	@test -f $(COMPOSE_DIR)/.env.aws || { echo "copy $(COMPOSE_DIR)/.env.aws.example to .env.aws first"; exit 1; }
	$(AWS_LOCAL) up -d --build --wait

demo: ## Seed the demo: people, three projects imported, tests generated and run in the sandbox
	$(FLOCI) exec -T -e TESTFORGE_DEMO_API_URL=http://api:8080 worker testforge seed-demo
	@echo "  Sign in at http://localhost:$${TESTFORGE_WEB_PORT:-5610} with a demo account above, password $(DEMO_PW)"

down: ## Stop the stack and delete its data
	-$(FLOCI) --profile test down -v --remove-orphans
	-$(AWS_LOCAL) down -v --remove-orphans 2>/dev/null

admin: ## Create or reset an admin on the local stack (EMAIL=you@example.com; prompts for the password)
	@test -n "$(EMAIL)" || { echo "usage: make admin EMAIL=you@example.com"; exit 1; }
	$(FLOCI) exec api testforge create-admin --email "$(EMAIL)"

logs: ## Tail logs (SERVICE=api|worker|scheduler|sandbox|web|floci|mockai|...)
	$(FLOCI) logs -f --tail 100 $(SERVICE)

ps: ## Show stack status
	$(FLOCI) ps

# ─── Quality ─────────────────────────────────────────────────────────────────

lint: ## Lint the API, the SDK (ruff) and the web app (eslint)
	$(API) uv run ruff check src tests && uv run ruff format --check src tests
	$(API) uv run ruff check ../../sdk/python/src && uv run ruff format --check ../../sdk/python/src
	@if [ -d apps/web ]; then $(WEB) pnpm lint; fi

typecheck: ## Typecheck the API, the SDK (mypy --strict) and the web app (tsc)
	$(API) uv run mypy --strict src
	$(API) uv run mypy --strict ../../sdk/python/src
	@if [ -d apps/web ]; then $(WEB) pnpm typecheck; fi

test: ## Unit tests: API (pytest) and web (vitest). No database, no network
	$(API) uv run pytest tests/unit -q
	@if [ -d apps/web ]; then $(WEB) pnpm test; fi

test-integration: ## API integration tests against real Postgres, Redis, the mock services and the sandbox (started if needed)
	@scripts/test-db.sh
	$(API) uv run pytest tests/unit tests/integration -q --cov=testforge --cov-report=term-missing:skip-covered --cov-fail-under=85

test-sandbox: ## The sandbox suite (isolation, limits, real pytest and Vitest runs) inside the hardened sandbox image
	docker build -f infra/docker/sandbox.Dockerfile --target sandbox-test --build-arg APT_MIRROR=$(APT_MIRROR) -t $(SANDBOX_TEST_IMAGE) apps/api
	docker run --rm $(SANDBOX_HARDENING) -e PYTHONDONTWRITEBYTECODE=1 \
	  -v $(CURDIR)/apps/api:/src:ro -w /src $(SANDBOX_TEST_IMAGE) pytest -q -p no:cacheprovider tests/sandbox

test-matrix: ## Integration tests under every key and storage backend (local and Floci KMS, local and Floci S3)
	@scripts/test-matrix.sh

bench: ## Benchmarks: analysis time, the assertion check, sandbox cold start and per-run overhead
	@scripts/test-db.sh
	$(API) uv run python -m tests.bench.bench_testforge

e2e: ## Browser end-to-end tests (Playwright) against the running stack (make up && make demo)
	cd e2e && pnpm install --frozen-lockfile && pnpm exec playwright install chromium && E2E_PASSWORD='$(DEMO_PW)' pnpm test

qa: ## Browser QA sweep (Puppeteer): every page, light and dark, desktop and phone
	cd scripts/qa && pnpm install --frozen-lockfile && QA_PASSWORD='$(DEMO_PW)' node qa.mjs

screenshots: ## Curated screenshots (docs/assets/screenshots) and the tour GIF, from the seeded stack
	cd scripts/qa && pnpm install --frozen-lockfile && QA_PASSWORD='$(DEMO_PW)' node screenshots.mjs && ./make-tour.sh

build: ## Build the container images (TESTFORGE_APT_MIRROR speeds up the sandbox image on slow routes)
	TESTFORGE_APT_MIRROR='$(APT_MIRROR)' $(FLOCI) build

openapi: ## Regenerate docs/api/openapi.yaml from the FastAPI app
	@mkdir -p docs/api
	$(API) uv run testforge openapi > ../../docs/api/openapi.yaml

sanitize: ## Scan committable files for credentials, cloud identifiers and em/en dashes
	@scripts/check-sanitization.sh

# ─── Terraform ───────────────────────────────────────────────────────────────

tf-fmt: ## Format all Terraform
	$(TF) fmt -recursive $(TF_ROOT)

tf-validate: ## terraform validate every environment (no backend, no credentials)
	@for env in $(TF_ENVS); do \
	  echo "== $$env"; \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env init -backend=false -input=false -no-color >/dev/null && \
	  $(TF) -chdir=$(TF_ROOT)/envs/$$env validate -no-color || exit 1; \
	done

tf-lint: ## tflint every module and environment (plugins cached in a docker volume)
	docker run --rm -v $(CURDIR)/infra:/data -v testforge-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data/terraform ghcr.io/terraform-linters/tflint:v0.64.0 --init
	docker run --rm -v $(CURDIR)/infra:/data -v testforge-tflint:/plugins -e TFLINT_PLUGIN_DIR=/plugins -w /data/terraform ghcr.io/terraform-linters/tflint:v0.64.0 --recursive --format compact

tf-security: ## checkov policy scan of the Terraform
	docker run --rm -v $(CURDIR)/infra:/infra -w /infra/terraform bridgecrew/checkov:3.3.30 -d . --framework terraform --quiet --compact --config-file .checkov.yaml

tf-aws-on-floci: ## Plan, apply, re-plan and destroy the full aws-dev environment against a throwaway Floci
	@scripts/tf-aws-on-floci.sh

aws-plan: ## terraform plan for ENV (aws-dev | aws-prod); needs terraform.tfvars and AWS credentials
	cd infra/terraform/envs/$(ENV) && terraform init -input=false && terraform plan

clean: ## Remove build output and caches
	rm -rf apps/web/.next apps/api/.pytest_cache apps/api/.mypy_cache apps/api/.ruff_cache apps/api/.coverage e2e/test-results e2e/playwright-report scripts/qa/output
