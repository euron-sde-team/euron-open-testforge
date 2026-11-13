# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# The sandbox service: the only place TestForge executes code (generated tests, uploaded
# projects and their own test suites).
#   docker build -f infra/docker/sandbox.Dockerfile --target sandbox -t testforge-sandbox apps/api
#
# `testforge sandbox` (FastAPI on 0.0.0.0:8080) starts one nsjail per run, built from user
# namespaces so the container itself needs no privilege: Euron Open CodeJudge's judge
# design. Compose and the ECS task drop every capability, set no-new-privileges, a
# read-only root filesystem and infra/docker/sandbox-seccomp.json
# (docs/architecture/sandbox.md). The container holds no credential but the request
# signing secret, and its network reaches nothing but the worker.
#
# What runs see, read-only: /usr, /lib and /bin, and the test toolchain in /opt/toolchain
# (pytest, pytest-cov and common service libraries in a virtualenv; Vitest with Istanbul
# coverage). The service's own virtualenv lives in /opt/venv, which no jail mounts.
# ─────────────────────────────────────────────────────────────────────────────
ARG DEBIAN_IMAGE=debian:trixie-slim
ARG NSJAIL_VERSION=3.6
# Optional Debian mirror for slow routes to deb.debian.org: an http URL ending in /debian
# that also serves <url>-security (e.g. http://ftp.de.debian.org/debian). Empty keeps the
# default.
ARG APT_MIRROR=

FROM ghcr.io/astral-sh/uv:0.9.17 AS uv

# ── nsjail, built from a pinned release tag ───────────────────────────────────
FROM ${DEBIAN_IMAGE} AS nsjail
ARG NSJAIL_VERSION
ARG APT_MIRROR
RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i -e "s#^URIs: http://deb.debian.org/debian\$#URIs: ${APT_MIRROR}#" \
             -e "s#^URIs: http://deb.debian.org/debian-security\$#URIs: ${APT_MIRROR}-security#" \
             /etc/apt/sources.list.d/debian.sources; fi
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git make g++ pkg-config bison flex protobuf-compiler \
      libprotobuf-dev libnl-route-3-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${NSJAIL_VERSION}" https://github.com/google/nsjail.git /src \
 && make -C /src -j"$(nproc)" \
 && install -m 0755 /src/nsjail /nsjail

# ── What runs execute with ────────────────────────────────────────────────────
FROM ${DEBIAN_IMAGE} AS runtimes
ARG APT_MIRROR
RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i -e "s#^URIs: http://deb.debian.org/debian\$#URIs: ${APT_MIRROR}#" \
             -e "s#^URIs: http://deb.debian.org/debian-security\$#URIs: ${APT_MIRROR}-security#" \
             /etc/apt/sources.list.d/debian.sources; fi
RUN apt-get update && apt-get install -y --no-install-recommends \
      tini ca-certificates libprotobuf32t64 libnl-route-3-200 \
      python3 python3-venv nodejs \
 && rm -rf /var/lib/apt/lists/*

# ── The Python test toolchain (pinned in toolchain/python/requirements.txt) ────
FROM runtimes AS toolchain-python
COPY src/testforge/sandbox/toolchain/python/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv /opt/toolchain/python \
 && /opt/toolchain/python/bin/pip install --no-compile -r /tmp/requirements.txt \
 && /opt/toolchain/python/bin/python -m compileall -q /opt/toolchain/python/lib \
 && rm -rf /opt/toolchain/python/lib/python3*/site-packages/pip

# ── The JavaScript and TypeScript test toolchain (pinned in package-lock.json) ─
FROM runtimes AS toolchain-js
ARG APT_MIRROR
RUN apt-get update && apt-get install -y --no-install-recommends npm \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/toolchain/js
COPY src/testforge/sandbox/toolchain/js/package.json src/testforge/sandbox/toolchain/js/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund --fetch-retries=8 --fetch-retry-mintimeout=5000 --fetch-retry-maxtimeout=120000 \
 && node -e "require.resolve('vitest/package.json'); require.resolve('@vitest/coverage-istanbul/package.json')"

# ── The service's own virtualenv, on the same system Python ──────────────────
FROM runtimes AS build
COPY --from=uv /uv /bin/
ARG UV_CONCURRENT_DOWNLOADS=8
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3 UV_PROJECT_ENVIRONMENT=/opt/venv UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=${UV_CONCURRENT_DOWNLOADS}
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM runtimes AS sandbox
COPY --from=nsjail /nsjail /usr/local/bin/nsjail
COPY --from=build /opt/venv /opt/venv
COPY --from=toolchain-python /opt/toolchain/python /opt/toolchain/python
COPY --from=toolchain-js /opt/toolchain/js/node_modules /opt/toolchain/js/node_modules
COPY src/testforge/sandbox/toolchain/js/testforge-reporter.mjs src/testforge/sandbox/toolchain/js/no-proc.cjs /opt/toolchain/js/
COPY src/testforge/sandbox/toolchain/plugins/testforge_pytest.py /opt/toolchain/plugins/
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC HOME=/tmp PORT=8080 \
    NSJAIL_PATH=/usr/local/bin/nsjail SANDBOX_WORK_DIR=/tmp/testforge-sandbox \
    TOOLCHAIN_DIR=/opt/toolchain
RUN groupadd --system --gid 10001 sandbox \
 && useradd --system --uid 10001 --gid sandbox --home-dir /tmp --no-create-home \
      --shell /usr/sbin/nologin sandbox \
 && chmod -R a+rX,go-w /opt/toolchain \
 && ! ldd /usr/local/bin/nsjail | grep -q "not found" \
 && /opt/toolchain/python/bin/python -c "import pytest, pytest_cov, coverage, fastapi, httpx, flask" \
 && node /opt/toolchain/js/node_modules/vitest/vitest.mjs --version \
 && /opt/venv/bin/python -c "import testforge.sandbox.server"
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["testforge", "sandbox"]

# ── Test target: the same image plus pytest (make test-sandbox mounts the tests) ─
FROM build AS build-test
# Only the test runner: the rest of the dev group (the SDK) is not part of this image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python "pytest>=8.3" "pytest-asyncio>=0.24"

FROM sandbox AS sandbox-test
COPY --from=build-test /opt/venv /opt/venv
WORKDIR /src
CMD ["pytest", "-q", "tests/sandbox"]
