# TestForge's secrets, in Secrets Manager. ECS injects each JSON key into the containers
# that need it as an environment variable; the values never appear in a task definition,
# a plan diff or a log. Each consumer gets only its own keys (see the outputs).
#
# Three secrets with different lifecycles and readers:
#
#   <name_prefix>/app          SESSION_SECRET, API_KEY_PEPPER. Read by the api, the worker,
#                              the scheduler and the migrate task.
#   <name_prefix>/sandbox      SANDBOX_SECRET, the HMAC key that signs every worker to
#                              sandbox request. On its own so the sandbox's execution role
#                              reads it and nothing else. The control plane reads it too:
#                              the worker signs with it, and every role's production guard
#                              refuses to boot without a strong one.
#   <name_prefix>/connections  DATABASE_URL, REDIS_URL. Derived from the database and
#                              cache modules and kept in step with them on every apply.
#                              Never given to the sandbox.
#
# Generated once (64 random alphanumerics each, so they are long and distinct as the
# production guard in core/config.py demands), then rotated out of band; Terraform never
# rolls them back. Locally (Compose) the same names come from deploy/compose/.env; on AWS
# no LOCAL_MASTER_KEY exists because stored secrets are sealed with KMS (KEY_MODE=kms).
locals {
  app_keys        = ["API_KEY_PEPPER", "SESSION_SECRET"]
  connection_keys = var.include_connection_urls ? ["DATABASE_URL", "REDIS_URL"] : []
}

resource "random_password" "this" {
  for_each = toset(concat(local.app_keys, ["SANDBOX_SECRET"]))
  length   = 64
  special  = false
}

resource "aws_secretsmanager_secret" "app" {
  #checkov:skip=CKV2_AWS_57:These are HMAC keys; rotation is an operator procedure (put a new version, redeploy), not a Lambda.
  name                    = "${var.name_prefix}/app"
  description             = "TestForge signing secrets (sessions, API key pepper)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({ for k in local.app_keys : k => random_password.this[k].result })

  # Rotation happens out of band (put a new version by hand or by pipeline). Without
  # this, the next `terraform apply` would quietly roll every secret back.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "sandbox" {
  #checkov:skip=CKV2_AWS_57:A shared HMAC key between the worker and the sandbox; rotation is an operator procedure (put a new version, redeploy both).
  name                    = "${var.name_prefix}/sandbox"
  description             = "TestForge sandbox request signing key (worker to sandbox)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "sandbox" {
  secret_id     = aws_secretsmanager_secret.sandbox.id
  secret_string = jsonencode({ SANDBOX_SECRET = random_password.this["SANDBOX_SECRET"].result })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "connections" {
  #checkov:skip=CKV2_AWS_57:Derived values; they change when the database or cache module rotates its credential.
  count                   = var.include_connection_urls ? 1 : 0
  name                    = "${var.name_prefix}/connections"
  description             = "TestForge connection URLs (PostgreSQL, Redis/Valkey)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "connections" {
  count     = var.include_connection_urls ? 1 : 0
  secret_id = aws_secretsmanager_secret.connections[0].id
  secret_string = jsonencode({
    DATABASE_URL = var.database_url
    REDIS_URL    = var.redis_url
  })
}

locals {
  app_ref     = { for k in local.app_keys : k => "${aws_secretsmanager_secret.app.arn}:${k}::" }
  sandbox_ref = "${aws_secretsmanager_secret.sandbox.arn}:SANDBOX_SECRET::"

  # Control plane (api, worker, scheduler, migrate).
  ecs_secrets = concat(
    [for k in local.app_keys : { name = k, valueFrom = local.app_ref[k] }],
    [{ name = "SANDBOX_SECRET", valueFrom = local.sandbox_ref }],
    [for k in local.connection_keys : { name = k, valueFrom = "${aws_secretsmanager_secret.connections[0].arn}:${k}::" }],
  )
  # The sandbox: its signing key and nothing else. No database, cache, storage, session
  # or provider credential.
  sandbox_secrets = [{ name = "SANDBOX_SECRET", valueFrom = local.sandbox_ref }]
}
