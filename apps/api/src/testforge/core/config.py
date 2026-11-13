"""Runtime configuration, validated once at boot.

Every setting comes from the environment and is read here only. The API, the worker, the
scheduler and the sandbox service share one ``Settings`` class, but each role reads only
what it needs: the sandbox service, for one, is given no database, storage or provider
setting at all in Compose or on ECS. Security-relevant settings are checked by ``guard()``
so a misconfigured production deployment refuses to start instead of running with demo
secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_SECRETS = {"", "change-me", "replace-with-output-of-make-env", "dev", "secret"}


def _split(v: object) -> object:
    if isinstance(v, str):
        return [item.strip() for item in v.split(",") if item.strip()]
    return v


def _insecure(value: str) -> bool:
    return value in INSECURE_SECRETS or "not-for-production" in value or len(value) < 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cloud: Literal["local", "floci", "aws"] = Field("local", alias="TESTFORGE_CLOUD")

    database_url: str = "postgresql+asyncpg://testforge:testforge@localhost:5642/testforge"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Rate limits and the analysis cache. Optional: without it they live in process.
    redis_url: str = ""
    memory_cache_max_bytes: int = Field(64_000_000, ge=1_000_000)

    session_secret: str = "dev-session-secret-not-for-production"  # noqa: S105 dev default, refused in production by guard()
    api_key_pepper: str = "dev-api-key-pepper-not-for-production"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5610"]
    )
    # Where people open the app; used in links (mail, webhook payloads, HTML reports).
    public_url: str = "http://localhost:5610"

    # Provider keys, GitHub tokens and webhook secrets are sealed before storage.
    key_mode: Literal["local", "kms"] = "local"
    local_master_key: str = "dev-local-master-key-not-for-production"
    kms_key_id: str = "alias/testforge-local"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_force_path_style: bool = False
    # Uploaded ZIPs, source snapshots and exported reports. Rows keep only the key.
    objects_bucket: str = "testforge-local-objects"
    storage: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./.data/objects"

    # Mail for member notices: "log" (development), "smtp" (Mailpit locally), "ses" (AWS).
    mail_backend: Literal["log", "smtp", "ses"] = "log"
    mail_from: str = "TestForge <testforge@testforge.local>"
    smtp_host: str = "localhost"
    smtp_port: int = Field(1025, ge=1, le=65535)

    # Model providers on private networks (a local Ollama or vLLM) are normal.
    provider_allow_private: bool = True
    # GitHub (or GitHub Enterprise) REST API. Repository archives, pull requests and their
    # changed files are read through it; nothing is ever cloned or executed while importing.
    github_api_url: str = "https://api.github.com"
    # A GitHub Enterprise server, or the mock GitHub used by tests and the demo, may live on
    # a private network; public github.com never does.
    github_allow_private: bool = False
    github_timeout_s: float = Field(60.0, gt=0, le=600)

    # Imports. An archive larger than this is refused before it is unpacked; unpacking
    # stops at the file count and the uncompressed byte budget (zip bombs).
    max_upload_bytes: int = Field(25_000_000, ge=100_000)
    max_snapshot_bytes: int = Field(50_000_000, ge=100_000)
    max_snapshot_files: int = Field(5_000, ge=10)
    max_file_bytes: int = Field(1_000_000, ge=1_000)
    # OpenAPI documents imported for API test generation.
    max_spec_bytes: int = Field(2_000_000, ge=10_000)
    work_dir: str = "./.data/work"

    # The sandbox service. Requests are HMAC signed with SANDBOX_SECRET; the service holds
    # nothing else.
    sandbox_url: str = "http://localhost:5635"
    sandbox_secret: str = "dev-sandbox-secret-not-for-production"  # noqa: S105 dev default, refused in production by guard()
    # Default budget of one test run. A project may lower these, never raise them past
    # the ceilings below.
    run_cpu_s: int = Field(60, ge=1, le=3600)
    run_wall_s: int = Field(120, ge=1, le=3600)
    run_memory_mb: int = Field(1024, ge=64, le=16384)
    run_output_bytes: int = Field(4_000_000, ge=10_000, le=100_000_000)
    run_cpu_ceiling_s: int = Field(600, ge=1, le=7200)
    run_wall_ceiling_s: int = Field(900, ge=1, le=7200)
    run_memory_ceiling_mb: int = Field(4096, ge=64, le=65536)
    run_output_ceiling_bytes: int = Field(32_000_000, ge=10_000, le=500_000_000)
    # Bytes of a workspace sent to the sandbox for one run.
    max_workspace_bytes: int = Field(40_000_000, ge=100_000)

    # Test generation.
    max_units_per_generation: int = Field(25, ge=1, le=500)
    # The source part of one prompt stays under this many characters.
    prompt_source_chars: int = Field(24_000, ge=2_000, le=400_000)
    model_timeout_s: float = Field(120.0, gt=0, le=1800)

    # The worker (imports, analysis, generation, runs) and the scheduler.
    worker_concurrency: int = Field(4, ge=1, le=256)
    lease_s: float = Field(120.0, ge=10, le=7200)
    max_attempts: int = Field(3, ge=1, le=20)
    worker_poll_interval_s: float = Field(2.0, gt=0, le=60)
    task_interval_s: float = Field(10.0, gt=0, le=600)
    worker_metrics_port: int = Field(9464, ge=0, le=65535)
    # Outbound webhook deliveries are retried this many times with backoff.
    webhook_max_attempts: int = Field(6, ge=1, le=50)
    webhook_timeout_s: float = Field(10.0, gt=0, le=120)
    # Outbound webhooks to private networks (a CI server inside the VPC). Metadata and
    # link-local addresses are refused either way.
    webhook_allow_private: bool = False

    # Generations and runs per minute per project.
    generate_rpm: int = Field(30, ge=1)
    run_rpm: int = Field(60, ge=1)
    max_body_bytes: int = 2_000_000
    otel_enabled: bool = False
    # Runs, their results and exported reports older than this are purged. The audit
    # log is append-only and never purged.
    retention_days: int = Field(90, ge=1)

    # Sandbox service only (the `testforge sandbox` role).
    nsjail_path: str = "/usr/local/bin/nsjail"
    sandbox_work_dir: str = "/tmp/testforge-sandbox"  # noqa: S108 a tmpfs owned by the service user
    # The read-only toolchain every run sees (pytest, coverage, vitest and their plugins).
    toolchain_dir: str = "/opt/toolchain"
    # One run at a time per sandbox process: RLIMIT_NPROC counts per real uid and every
    # jail maps to the same uid, so two concurrent jails would share one process budget.
    # Throughput comes from more sandbox replicas, not more jails per replica.
    sandbox_concurrency: int = Field(1, ge=1, le=64)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        return _split(v)

    @property
    def cache_backend(self) -> Literal["redis", "memory"]:
        return "redis" if self.redis_url else "memory"

    def guard(self) -> None:
        """Refuse to boot in production with demo secrets or unsafe options."""
        if self.environment != "production":
            return
        names = ("session_secret", "api_key_pepper", "sandbox_secret")
        problems: list[str] = [
            f"{name.upper()} must be a random value of at least 32 chars"
            for name in names
            if _insecure(getattr(self, name))
        ]
        if self.key_mode == "local" and _insecure(self.local_master_key):
            problems.append("LOCAL_MASTER_KEY must be set (or use KEY_MODE=kms)")
        secrets = [getattr(self, n) for n in names]
        if len(set(secrets)) != len(secrets):
            problems.append("SESSION_SECRET, API_KEY_PEPPER and SANDBOX_SECRET must differ")
        if self.cloud == "aws" and self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL must be unset when TESTFORGE_CLOUD=aws")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.mail_backend == "log":
            problems.append("MAIL_BACKEND must be smtp or ses in production")
        if self.storage == "local":
            problems.append("STORAGE must be s3 in production (several replicas share snapshots)")
        if problems:
            raise RuntimeError("unsafe production configuration: " + "; ".join(problems))

    def clamp_limits(
        self, cpu_s: int | None, wall_s: int | None, memory_mb: int | None, output_bytes: int | None
    ) -> tuple[int, int, int, int]:
        """A run's budget: the requested values (or the defaults) under the ceilings."""
        return (
            min(cpu_s or self.run_cpu_s, self.run_cpu_ceiling_s),
            min(wall_s or self.run_wall_s, self.run_wall_ceiling_s),
            min(memory_mb or self.run_memory_mb, self.run_memory_ceiling_mb),
            min(output_bytes or self.run_output_bytes, self.run_output_ceiling_bytes),
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.guard()
    return settings
