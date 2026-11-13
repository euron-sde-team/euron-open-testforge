# `sandbox` module

The sandbox service: the only place Euron Open TestForge executes code (generated tests, uploaded projects and their own test suites). It runs the `sandbox` image (`infra/docker/sandbox.Dockerfile`, command `testforge sandbox`, port 8080, health `/healthz`) as ECS tasks on EC2 capacity in a cluster of its own: an Auto Scaling group behind an ECS capacity provider with managed scaling and draining, one sandbox task per instance (`distinctInstance`).

## How the worker reaches it (SANDBOX_URL)

Unlike a pull-based executor, TestForge's worker calls the sandbox over HTTP, each request HMAC signed with `SANDBOX_SECRET`. The sandbox service registers its tasks in the Cloud Map private DNS namespace the `service` module already runs (A records, `MULTIVALUE`, TTL 10 s, health reported by ECS), so the worker's `SANDBOX_URL` is the `url` output:

```
http://sandbox.<name_prefix>.internal:8080
```

Cloud Map was chosen over an internal load balancer because it is the smallest thing that works: no extra load balancer, listener, target group or TLS policy to run and pay for; a task that is unhealthy or draining leaves DNS; several tasks are spread by multivalue answers; and the security group story stays one rule. The worker resolves the name through the VPC resolver, which security groups do not filter.

## Security groups

- Sandbox task group: ingress TCP 8080 from the worker task security group only, and **no egress rule at all** (Terraform removes AWS's default allow-all; replies to the worker need none because security groups are stateful). The sandbox cannot open a connection to the database, Redis, the api, S3 or the internet.
- Worker task group: one egress rule, TCP 8080 to the sandbox task group (added here).
- Instance group: HTTPS egress only, for the ECS agent, image pulls from ECR, CloudWatch Logs, Secrets Manager (the agent injects `SANDBOX_SECRET`) and Session Manager, through the NAT or the interface endpoints. No ingress, no SSH.

## Hardening

Mirrors the `sandbox` service in `deploy/compose/compose.yaml`:

- Seccomp: the user data writes `infra/docker/sandbox-seccomp.json` to `/etc/docker/sandbox-seccomp.json` and makes it the Docker daemon's default (with `no-new-privileges`) on these hosts, which run nothing but sandbox tasks. nsjail then builds each run's jail from user namespaces without any privilege.
- Task: every capability dropped, `no-new-privileges`, privileged containers disabled on the host (`ECS_DISABLE_PRIVILEGED`), read-only root, tmpfs `/tmp` (exec, owned by uid 10001, `tmp_mib`), nproc ulimit `max_processes` (compose `pids_limit`), memory `task_memory` (compose `mem_limit`), 2 vCPU, no core dumps, non-root user 10001, `SANDBOX_CONCURRENCY=1`.
- Metadata: IMDSv2 required with a hop limit of 1, and `ECS_AWSVPC_BLOCK_IMDS` so a task cannot borrow the instance role.
- IAM: the task role has **no policy**; the execution role injects only `SANDBOX_SECRET`. The sandbox holds no database, cache, storage, model provider or GitHub credential.

Scaling: `desired_count` tasks (one per host); with `max_count` above it, target tracking on sandbox CPU adds tasks and the capacity provider adds hosts to fit. A run cut short by a deploy or a scale-in is retried by the worker.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `vpc_id` | VPC the sandbox hosts run in. | `string` | required |
| `private_subnet_ids` | Private subnets for the instances and task interfaces (no public IP). | `list(string)` | required |
| `image` | Full sandbox image reference, e.g. <registry>/testforge-prod/sandbox:<tag>. | `string` | required |
| `port` | Port the sandbox service listens on (PORT). | `number` | `8080` |
| `namespace_id` | Cloud Map private DNS namespace to register sandbox.<namespace> in (service module namespace_id). | `string` | required |
| `namespace_name` | Name of that namespace (service module namespace_name), used to build the url output. | `string` | required |
| `worker_security_group_id` | The worker tasks' security group (service module security_group_ids.worker): the only source allowed in, and it gets the matching egress rule. | `string` | required |
| `secrets` | ECS secrets for the sandbox (secrets module sandbox_secrets: SANDBOX_SECRET only). | `list` | required |
| `environment` | Extra sandbox environment, e.g. LOG_LEVEL. Never secrets, and never a database, storage or provider setting. | `map(string)` | `{}` |
| `kms_key_arn` | CMK for the root volumes and for decrypting the injected secret. | `string` | required |
| `log_group_name` | CloudWatch log group for the sandbox (observability module log_group_names.sandbox). | `string` | required |
| `seccomp_profile_json` | The sandbox seccomp profile (infra/docker/sandbox-seccomp.json): the Docker daemon default on the sandbox hosts. | `string` | required |
| `ami_id` | Sandbox host AMI. Null: the latest ECS-optimized Amazon Linux 2023 ARM64 AMI. | `string` | `null` |
| `instance_type` | ARM64 instance type for sandbox hosts (one sandbox task each). Compute optimized (c7g) suits test runs. | `string` | `"c7g.large"` |
| `root_volume_gib` | Root volume size of a sandbox host (images and logs; run scratch space is tmpfs). | `number` | `30` |
| `min_instances` | Sandbox hosts kept running. | `number` | `1` |
| `max_instances` | Most sandbox hosts the capacity provider may run. At least max_count (one task per host) plus one for rolling deploys. | `number` | `4` |
| `desired_count` | Sandbox tasks kept running (each runs one test run at a time, one task per host). | `number` | `2` |
| `max_count` | Most sandbox tasks CPU autoscaling may run. Equal to desired_count disables autoscaling. | `number` | `2` |
| `task_cpu` | CPU units per sandbox task (1024 = one vCPU); compose gives the sandbox 2 CPUs. | `number` | `2048` |
| `task_memory` | Memory per sandbox task in MiB (compose mem_limit 3g), including the /tmp tmpfs. | `number` | `3072` |
| `tmp_mib` | tmpfs size for /tmp (each run's workspace and jail) in MiB (compose: 1g). | `number` | `1024` |
| `max_processes` | nproc ulimit for the sandbox user (compose pids_limit 1024). | `number` | `1024` |
| `cpu_target_percent` | Average sandbox CPU the autoscaler aims for (with max_count > desired_count). | `number` | `60` |
| `container_insights` | ECS Container Insights on the sandbox cluster (enabled, enhanced or disabled). | `string` | `"enabled"` |

## Outputs

| Name | Description |
|---|---|
| `url` | SANDBOX_URL for the worker: http://sandbox.<namespace>:<port> through Cloud Map. |
| `cluster_name` | Sandbox ECS cluster name. |
| `service_name` | Sandbox ECS service name. |
| `security_group_id` | Sandbox task security group. |
| `autoscaling_group_name` | Sandbox hosts' Auto Scaling group. |
