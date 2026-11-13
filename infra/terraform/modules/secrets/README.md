# `secrets` module

Secrets Manager entries for Euron Open TestForge, each injected by ECS only into the containers that need it:

- `<name_prefix>/app`: `SESSION_SECRET`, `API_KEY_PEPPER` (api, worker, scheduler, migrate).
- `<name_prefix>/sandbox`: `SANDBOX_SECRET`, the HMAC key that signs every request from the worker to the sandbox. Separate so the sandbox's execution role reads it and nothing else. The control plane gets it too: the worker signs with it, and every role's production guard refuses to boot without a strong one.
- `<name_prefix>/connections` (with `include_connection_urls`): `DATABASE_URL`, `REDIS_URL`. Never given to the sandbox.

Values are 64 random alphanumerics, generated once, so they satisfy the production guard in `apps/api/src/testforge/core/config.py` (at least 32 characters, all three different). They are rotated out of band; Terraform never rolls them back (`ignore_changes`). On AWS stored user secrets are sealed with KMS (`KEY_MODE=kms`), so no `LOCAL_MASTER_KEY` exists.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `kms_key_arn` | CMK that encrypts the secrets. Null uses the AWS-managed key. | `string` | `null` |
| `recovery_window_in_days` | Days a deleted secret stays recoverable. 0 deletes immediately (local and throwaway environments). | `number` | `30` |
| `include_connection_urls` | Create the connections secret from database_url and redis_url. false where Compose supplies them (local-floci). | `bool` | `false` |
| `database_url` | DATABASE_URL (database module connection_url), with include_connection_urls. | `string` | `null` |
| `redis_url` | REDIS_URL (cache module connection_url), with include_connection_urls. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `secret_arn` | ARN of the JSON secret holding SESSION_SECRET and API_KEY_PEPPER. |
| `sandbox_secret_arn` | ARN of the JSON secret holding SANDBOX_SECRET. |
| `connections_secret_arn` | ARN of the JSON secret holding DATABASE_URL and REDIS_URL (null without include_connection_urls). |
| `keys` | Every environment variable the secrets provide. |
| `ecs_secrets` | ECS `secrets` entries for the control plane (api, worker, scheduler, migrate): [{ name, valueFrom = "<arn>:<key>::" }]. |
| `sandbox_secrets` | ECS `secrets` entries for the sandbox (SANDBOX_SECRET only). |
