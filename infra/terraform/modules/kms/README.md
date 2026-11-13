# `kms` module

One customer-managed KMS key (annual rotation) plus alias for Euron Open TestForge.

- **Sealing** (`KEY_MODE=kms`, `KMS_KEY_ID`): model provider API keys, GitHub tokens and webhook signing secrets are sealed with KMS `Encrypt` before they reach Postgres, with the encryption context `testforge:record=<row>`, so a sealed value copied to another row fails to open. The api, worker and scheduler task roles may use the key directly only with that context key.
- **At rest**: the objects bucket (SSE-KMS), RDS, ElastiCache, Secrets Manager, ECR, the sandbox hosts' EBS volumes and the CloudWatch log groups (the key policy lets CloudWatch Logs use it for this account's log groups only).

Applied in `local-floci`: the alias `alias/testforge-local` is what the local stack uses as `KMS_KEY_ID`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The alias is alias/<name_prefix>. | `string` | required |
| `deletion_window_in_days` | Waiting period before a scheduled key deletion completes. | `number` | `30` |
| `admin_principal_arns` | IAM principals allowed to administer (not use) the key. Empty = account root only, which delegates to IAM policies. | `list(string)` | `[]` |

## Outputs

| Name | Description |
|---|---|
| `key_arn` | KMS key ARN. |
| `key_id` | KMS key id. |
| `alias_name` | Alias, usable as KMS_KEY_ID. |
