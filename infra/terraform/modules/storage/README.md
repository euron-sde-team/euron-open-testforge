# `storage` module

One private S3 bucket, `<name_prefix>-objects` (`OBJECTS_BUCKET`, `STORAGE=s3`), for everything Euron Open TestForge keeps outside Postgres:

- `uploads/<project>/<import>.zip`: a project as uploaded. The worker deletes it once the snapshot exists; anything a failed import left behind expires after `upload_expiration_days`.
- `snapshots/<project>/<import>.zip`: the normalized source snapshot that analysis, test generation and runs read. Kept as long as the project.
- `reports/<project>/<report>.<fmt>`: exported reports, purged by the scheduler's retention task after `RETENTION_DAYS`.

Versioning is on, and replaced or deleted versions stay recoverable for `noncurrent_retention_days`. Public access blocked, bucket-owner-enforced ownership, TLS-only bucket policy, SSE-KMS with the CMK (bucket key on). Only the api, worker and scheduler task roles may use it; the sandbox gets a run's workspace from the worker over HTTP and holds no S3 permission.

Applied in `local-floci` as `testforge-local-objects` with `enforce_tls = false` (the emulator speaks plain HTTP) and `force_destroy = true`.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. The bucket is <name_prefix>-objects. | `string` | required |
| `kms_key_arn` | CMK for SSE-KMS. Null falls back to SSE-S3. | `string` | `null` |
| `enforce_tls` | Deny any request not made over TLS. Disable only for an emulator that speaks plain HTTP. | `bool` | `true` |
| `noncurrent_retention_days` | Days a replaced or deleted object version stays recoverable. | `number` | `30` |
| `upload_expiration_days` | Days an uploaded project ZIP (uploads/) is kept. The worker deletes it once its snapshot exists; this only removes what a failed import left behind. | `number` | `7` |
| `cors_origins` | Browser origins allowed to GET objects with JavaScript (the dashboard URL). Empty = no CORS configuration. | `list(string)` | `[]` |
| `force_destroy` | Allow `terraform destroy` to delete a non-empty bucket. Never in production. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Objects bucket name (OBJECTS_BUCKET). |
| `bucket_arn` | Objects bucket ARN, for IAM policies. |
