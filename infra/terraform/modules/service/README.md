# `service` module

The Euron Open TestForge application plane on ECS Fargate behind one Application Load Balancer:

| App | Command (server image, entrypoint `testforge`) | Role | Exposure |
|---|---|---|---|
| `api` | `serve --host 0.0.0.0 --port 8080` | the API, probes, docs | ALB: `/api`, `/api/*`, `/healthz`, `/readyz`, `/docs`, `/docs/*`, `/openapi.json`; Cloud Map `api.<name_prefix>.internal` for the web tasks |
| `worker` | `worker` | imports and analysis, test generation (model calls), test runs through the sandbox (`SANDBOX_URL`) | none (optional Prometheus scrape on 9464) |
| `scheduler` | `scheduler` | lease reaper, queue gauges (the `job queue` log line), webhook deliveries, retention | none; one task, replaced rather than doubled on deploy |
| `web` | image default | the Next.js dashboard, every other path | ALB (default action) |
| `migrate` | `migrate` | one-off task definition for `migrate`, and `create-admin` or `seed-demo` as command overrides | none |

The job queue is in PostgreSQL, so the worker and scheduler need nothing else to share work. The sandbox is not here: it needs a custom seccomp profile, which Fargate cannot take, so it runs on EC2 capacity in the `sandbox` module; the worker calls it at `sandbox_url` (the sandbox module's `url`), and that module adds the worker to sandbox security group rules. This module exports its Cloud Map namespace (`namespace_id`, `namespace_name`) for that.

Every app: its own security group (ingress only from the ALB or named callers; egress HTTPS, plus PostgreSQL and Redis where needed, plus `extra_egress` ports for the api, worker and scheduler), its own execution role (pull, log, inject exactly its secrets) and task role (the api, worker, scheduler and migrate may use the objects bucket and the KMS key with the `testforge:record` encryption context; only the api may send mail through SES, with `send_mail`; web has no policy), read-only root filesystem with `/tmp` and `/data/work` (`WORK_DIR`) mounted writable, ARM64, no public IP, deployment circuit breaker with rollback. `/metrics` answers 404 at the edge unless the caller is in `metrics_allowed_cidrs`. WAF with AWS managed rules; the body rules that mistake source code and ZIP uploads for attacks only count, and the authorization, cookie, `x-api-key` and `x-tf-csrf` headers and query strings are redacted from WAF logs.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Deployment prefix, e.g. "testforge-prod". At most 24 characters, so target group names stay unique within AWS's 32-character limit. | `string` | required |
| `vpc_id` | VPC of the load balancer and the tasks. | `string` | required |
| `public_subnet_ids` | Public subnets for the load balancer. | `list(string)` | required |
| `private_subnet_ids` | Private subnets the tasks run in. | `list(string)` | required |
| `hostname` | Public host name of the dashboard and API, e.g. testforge.example.com. The certificate must cover it. | `string` | required |
| `certificate_arn` | ACM certificate (same region) for the HTTPS listener, covering hostname. | `string` | required |
| `route53_zone_id` | Hosted zone to create the hostname alias record in. Null: point DNS at alb_dns_name yourself. | `string` | `null` |
| `api_image` | Full server image reference (also runs the worker, the scheduler and migrate), e.g. <registry>/testforge-prod/api:<tag>. | `string` | required |
| `web_image` | Full web image reference, e.g. <registry>/testforge-prod/web:<tag>. | `string` | required |
| `container_port` | Port every container listens on (PORT). | `number` | `8080` |
| `environment` | Plain environment for api, worker, scheduler and migrate (PORT, PUBLIC_URL, OBJECTS_BUCKET and WORK_DIR are set by the module; SANDBOX_URL and WORKER_CONCURRENCY for the worker). Never secrets. | `map(string)` | `{}` |
| `web_environment` | Plain environment for web (PORT, HOSTNAME and API_INTERNAL_URL are set by the module). Never secrets. | `map(string)` | `{}` |
| `secrets` | Secrets injected into api, worker, scheduler and migrate: [{ name, valueFrom = "<secret arn>:<json key>::" }] (secrets module ecs_secrets). | `list(object)` | `[]` |
| `kms_key_arn` | CMK that seals provider keys, GitHub tokens and webhook secrets, encrypts the objects bucket and the injected secrets. | `string` | required |
| `objects_bucket_arn` | Objects bucket (storage module bucket_arn). | `string` | required |
| `objects_bucket_name` | Objects bucket name (storage module bucket_name), passed as OBJECTS_BUCKET. | `string` | required |
| `db_security_group_id` | Database security group; api, worker, scheduler and migrate get ingress on it. | `string` | required |
| `db_port` | Database port. | `number` | `5432` |
| `cache_security_group_id` | Cache security group; api, worker, scheduler and migrate get ingress on it. | `string` | required |
| `cache_port` | Cache port. | `number` | `6379` |
| `log_group_names` | CloudWatch log group per app: { api, worker, scheduler, web, migrate } (observability module log_group_names). | `map(string)` | required |
| `logs_kms_key_arn` | CMK for the WAF log group. Null uses CloudWatch's default encryption. | `string` | `null` |
| `cpu_architecture` | ARM64 (Graviton, cheaper) or X86_64. Images must be built for it. | `string` | `"ARM64"` |
| `container_insights` | ECS Container Insights: enabled, enhanced or disabled. | `string` | `"enabled"` |
| `api_cpu` | Fargate CPU units per api task. | `number` | `1024` |
| `api_memory` | Fargate memory (MiB) per api task. | `number` | `2048` |
| `api_min_count` | Minimum (and initial) api task count. | `number` | `2` |
| `api_max_count` | Maximum api task count under autoscaling. Equal to api_min_count disables scaling. | `number` | `6` |
| `worker_cpu` | Fargate CPU units for the worker. | `number` | `512` |
| `worker_memory` | Fargate memory (MiB) for the worker. | `number` | `1024` |
| `worker_count` | Worker task count. Not autoscaled; each task runs WORKER_CONCURRENCY jobs at once, claimed from the PostgreSQL queue. | `number` | `1` |
| `web_cpu` | Fargate CPU units per web task. | `number` | `512` |
| `web_memory` | Fargate memory (MiB) per web task. | `number` | `1024` |
| `web_min_count` | Minimum (and initial) web task count. | `number` | `1` |
| `web_max_count` | Maximum web task count under autoscaling. | `number` | `3` |
| `cpu_target_percent` | Average CPU the autoscaler aims for (api and web). | `number` | `60` |
| `idle_timeout` | Load balancer idle timeout in seconds. Long enough for a project ZIP upload or a generation request that waits for its result; it only reaps abandoned connections. | `number` | `120` |
| `deletion_protection` | Block accidental deletion of the load balancer. | `bool` | `true` |
| `access_logs_bucket` | Existing bucket for load balancer access logs (needs the ELB log-delivery bucket policy). Null disables. | `string` | `null` |
| `metrics_allowed_cidrs` | Source CIDRs allowed to read /metrics through the load balancer. Empty: /metrics answers 404 at the edge. | `list(string)` | `[]` |
| `enable_waf` | Attach a WAF web ACL (managed rule sets plus a per-IP flood guard) to the load balancer. | `bool` | `true` |
| `waf_rate_limit_per_5min` | Requests per source IP per 5 minutes before WAF blocks. Keep it high: CI runners using the SDK often sit behind one NAT address. | `number` | `20000` |
| `waf_log_retention_days` | WAF log retention. | `number` | `30` |
| `worker_metrics_cidrs` | Source CIDRs (an in-VPC Prometheus) allowed to scrape the worker's /metrics. Empty: the worker has no ingress at all. | `list(string)` | `[]` |
| `worker_metrics_port` | Port the worker serves /metrics on; must match WORKER_METRICS_PORT (default 9464). | `number` | `9464` |
| `extra_egress` | Extra egress from the api, worker and scheduler tasks beyond HTTPS 443, as { cidr, port } pairs: a self-hosted model provider (Ollama, vLLM), a GitHub Enterprise server or a webhook receiver inside the VPC. Empty: HTTPS only. | `list` | `[]` |
| `sandbox_url` | SANDBOX_URL for the worker: the sandbox service on the private network (sandbox module url). | `string` | required |
| `worker_concurrency` | Jobs one worker task runs at once (WORKER_CONCURRENCY). | `number` | `4` |
| `scheduler_cpu` | Fargate CPU units for the scheduler (one task, never doubled). | `number` | `256` |
| `scheduler_memory` | Fargate memory (MiB) for the scheduler. | `number` | `512` |
| `send_mail` | Attach mail_policy_json to the api task role (member notices through SES). | `bool` | `false` |
| `mail_policy_json` | IAM policy for sending member notices (email module send_policy_json), with send_mail. | `string` | `null` |

## Outputs

| Name | Description |
|---|---|
| `cluster_name` | ECS cluster name. |
| `cluster_arn` | ECS cluster ARN. |
| `url` | Public URL of the dashboard and API. |
| `internal_urls` | Private service URLs through Cloud Map: { api }. The web tasks use it as API_INTERNAL_URL. |
| `alb_dns_name` | Load balancer DNS name (CNAME target for the host name when the zone is not in Route53). |
| `alb_arn_suffix` | Load balancer ARN suffix, for CloudWatch metrics. |
| `services` | Load-balanced services: { api, web } => { service_name, target_group_arn_suffix }. |
| `service_names` | Every ECS service name (api, worker, scheduler, web). |
| `security_group_ids` | Task security group per app. |
| `task_role_arns` | Task role per app. |
| `run_task` | Parameters for one-off tasks: `testforge migrate` (task_definition, the default), or `create-admin` and `seed-demo` as command overrides on the same definition. |
| `namespace_id` | Cloud Map private DNS namespace id (the sandbox module registers sandbox.<name_prefix>.internal in it). |
| `namespace_name` | Cloud Map private DNS namespace name (<name_prefix>.internal). |
