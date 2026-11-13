#!/usr/bin/env bash
# Make sure Postgres, Redis, the mock services and the integration sandbox are reachable
# for the integration suite. Reuses them when they are up; otherwise starts just those
# (the sandbox image is built first if it is missing).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Port overrides in deploy/compose/.env apply here too.
if [[ -f "$ROOT/deploy/compose/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/deploy/compose/.env"
  set +a
fi
PORTS=("${TESTFORGE_PG_PORT:-5642}" "${TESTFORGE_REDIS_PORT:-5679}" "${TESTFORGE_MOCKAI_PORT:-5650}" "${TESTFORGE_SANDBOX_PORT:-5635}")
SERVICES=(postgres redis mockai sandbox-test)

ready() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

all=1
for p in "${PORTS[@]}"; do ready "$p" || all=0; done
[[ $all == 1 ]] && exit 0
"$ROOT/scripts/gen-local-env.sh" >/dev/null
COMPOSE=(docker compose --env-file "$ROOT/deploy/compose/.env" -f "$ROOT/deploy/compose/compose.yaml" --profile test)
"${COMPOSE[@]}" build mockai sandbox
"${COMPOSE[@]}" up -d --wait "${SERVICES[@]}"
