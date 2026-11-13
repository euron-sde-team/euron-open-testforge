# ─────────────────────────────────────────────────────────────────────────────
# Local environment on the Floci AWS emulator.
#
# The modules that build production run here unchanged; only the provider endpoints
# differ. `make up` applies this automatically (the compose `terraform` one-shot in
# deploy/compose/compose.floci.yaml) before migrate, api, worker and scheduler start, so
# local development uses S3 and KMS exactly as AWS does. By hand, against a running
# emulator:
#
#   terraform -chdir=infra/terraform/envs/local-floci init
#   terraform -chdir=infra/terraform/envs/local-floci apply -var endpoint=http://localhost:5666
#
# What it creates:
#
#   objects bucket  testforge-local-objects, SSE-KMS (OBJECTS_BUCKET, STORAGE=s3):
#                   uploaded ZIPs, source snapshots, reports
#   KMS key         alias/testforge-local (KMS_KEY_ID, KEY_MODE=kms): seals provider keys,
#                   GitHub tokens and webhook secrets
#   secrets         testforge-local/app and testforge-local/sandbox, so the module is
#                   exercised (the local stack itself reads deploy/compose/.env)
#
# Postgres and Redis are plain Compose containers locally (the emulator does not back RDS
# or ElastiCache), mail goes to Mailpit, and the sandbox runs in Compose with the same
# hardening. The database, cache, email, ecr, service, sandbox and observability modules
# are exercised by aws-dev and aws-prod (make tf-validate, make tf-aws-on-floci).
# ─────────────────────────────────────────────────────────────────────────────

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
}

module "storage" {
  source        = "../../modules/storage"
  name_prefix   = var.name_prefix
  kms_key_arn   = module.kms.key_arn
  enforce_tls   = false # the emulator speaks plain HTTP
  force_destroy = true
  cors_origins  = var.cors_origins
}

# Generated secrets are an AWS-deployment concern; locally compose reads
# deploy/compose/.env (make env). Created here anyway so the module is exercised.
module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = 0
}
