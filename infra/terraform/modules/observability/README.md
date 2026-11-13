# `observability` module

Logs, alarms and a dashboard for Euron Open TestForge:

- A KMS-encrypted log group per app: `api`, `worker`, `scheduler`, `web`, `migrate`, `sandbox` (`/testforge/<name_prefix>/<app>`).
- Metrics extracted from the structured JSON logs (one object per line, `msg` and `level` plus extra fields at the top level, as `core/logs.py` writes them):
  - `JobQueueQueued`: the `queued` field of the scheduler's periodic `{"msg": "job queue", "queued": N, ...}` line.
  - `SandboxFailures`: the worker's `{"msg": "sandbox failure", "reason": ...}` line, one per sandbox execution that failed for a reason other than the tests (unreachable, busy, refused, launch).
  - `SandboxErrors`: error or critical lines logged by the sandbox service itself (for example nsjail could not start a run).
- Alarms to an SNS topic (optionally e-mailed): target 5xx and unhealthy targets per load-balanced app (api, web), load balancer 5xx, api p95 latency, CPU and memory per Fargate service and for the sandbox service, database CPU, storage and connections, cache memory and CPU, the job queue backing up for 15 minutes, sandbox failures and sandbox errors.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name. | `string` | required |
| `log_retention_days` | CloudWatch log retention for the app log groups. | `number` | `30` |
| `logs_kms_key_arn` | CMK for the log groups (its key policy must allow CloudWatch Logs, as the kms module's does). Null uses CloudWatch's default encryption. | `string` | `null` |
| `alarm_email` | Address subscribed to alarm notifications (confirm the e-mail AWS sends). Null: subscribe something else to the topic. | `string` | `null` |
| `alb_arn_suffix` | Load balancer ARN suffix. | `string` | required |
| `ecs_cluster_name` | ECS cluster name. | `string` | required |
| `lb_services` | Load-balanced services (service module `services`): { api = { service_name, target_group_arn_suffix }, web = { ... } }. Must contain api. | `map(object)` | required |
| `ecs_services` | Every Fargate ECS service to watch for CPU and memory (service module `service_names`): { api = "api", worker = "worker", scheduler = "scheduler", web = "web" }. | `map(string)` | required |
| `db_instance_identifier` | RDS instance identifier. | `string` | required |
| `db_max_connections` | Connection ceiling the alarm measures against. | `number` | `200` |
| `cache_replication_group_id` | ElastiCache replication group id; nodes are <id>-001, <id>-002, ... | `string` | required |
| `cache_node_count` | Nodes in the replication group (cache module num_cache_clusters). | `number` | `1` |
| `target_5xx_threshold` | 5xx responses per 5 minutes (per app, and at the load balancer) that raise an alarm. | `number` | `25` |
| `api_p95_latency_seconds` | api p95 time to first byte that raises an alarm. Imports, generation and runs are queued jobs, never on a request path. | `number` | `3` |
| `queue_log_pattern` | CloudWatch Logs JSON filter matching the scheduler's periodic job queue line (its `queued` field becomes the JobQueueQueued metric). | `string` | `"{ $.msg = \"job queue\" }"` |
| `sandbox_failure_log_pattern` | CloudWatch Logs JSON filter matching the worker's line for a sandbox execution that failed for a reason other than the tests (SandboxFailures). | `string` | `"{ $.msg = \"sandbox failure\" }"` |
| `sandbox_error_log_pattern` | CloudWatch Logs JSON filter matching an error line of the sandbox service (SandboxErrors). | `string` | `"{ $.level = \"error\" || $.level = \"critical\" }"` |
| `queue_queued_threshold` | Jobs waiting to be claimed, sustained for 15 minutes, that raise an alarm. | `number` | `50` |
| `sandbox_failure_threshold` | Sandbox failures seen by the worker per 5 minutes that raise an alarm. | `number` | `5` |
| `sandbox_error_threshold` | Sandbox service error lines per 5 minutes that raise an alarm. | `number` | `0` |
| `sandbox_cluster_name` | The sandbox's ECS cluster (sandbox module cluster_name): CPU and memory alarms for the sandbox service. | `string` | required |
| `sandbox_service_name` | The sandbox ECS service name (sandbox module service_name). | `string` | required |

## Outputs

| Name | Description |
|---|---|
| `log_group_names` | Log group per app: { api, worker, scheduler, web, migrate, sandbox } (service and sandbox modules). |
| `alarm_topic_arn` | SNS topic receiving every alarm. |
| `dashboard_name` | CloudWatch dashboard. |
| `metrics_namespace` | Namespace of the metrics extracted from the scheduler, worker and sandbox logs. |
