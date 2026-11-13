# `ecr` module

One ECR repository per Euron Open TestForge image:

- `api`: the server image (`infra/docker/server.Dockerfile`, entrypoint `testforge`). It runs the api (`serve`), the worker (`worker`), the scheduler (`scheduler`) and the one-off `migrate` task.
- `sandbox`: the sandbox image (`infra/docker/sandbox.Dockerfile`): nsjail, the Python and JavaScript test toolchains, `testforge sandbox`.
- `web`: the Next.js dashboard.

Immutable tags, scan on push, KMS encryption, untagged layers expire after 7 days, the most recent `keep_images` tagged images kept.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Repositories are named <name_prefix>/<image>. | `string` | required |
| `repositories` | Images to create repositories for. api also runs the worker, scheduler and migrate; sandbox runs tests in nsjail; web is the dashboard. | `list(string)` | `["api", "sandbox", "web"]` |
| `kms_key_arn` | CMK for repository encryption. Null uses AES256. | `string` | `null` |
| `keep_images` | Tagged images kept per repository. | `number` | `30` |
| `force_delete` | Allow destroying a repository that still holds images. | `bool` | `false` |

## Outputs

| Name | Description |
|---|---|
| `repository_urls` | Map of image name to repository URL. |
| `repository_arns` | Map of image name to repository ARN. |
