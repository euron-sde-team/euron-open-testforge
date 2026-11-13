variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the app log groups."
  type        = number
  default     = 30
}

variable "logs_kms_key_arn" {
  description = "CMK for the log groups (its key policy must allow CloudWatch Logs, as the kms module's does). Null uses CloudWatch's default encryption."
  type        = string
  default     = null
}

variable "alarm_email" {
  description = "Address subscribed to alarm notifications (confirm the e-mail AWS sends). Null: subscribe something else to the topic."
  type        = string
  default     = null
}

variable "alb_arn_suffix" {
  description = "Load balancer ARN suffix."
  type        = string
}

variable "ecs_cluster_name" {
  description = "ECS cluster name."
  type        = string
}

variable "lb_services" {
  description = "Load-balanced services (service module `services`): { api = { service_name, target_group_arn_suffix }, web = { ... } }. Must contain api."
  type = map(object({
    service_name            = string
    target_group_arn_suffix = string
  }))
  validation {
    condition     = contains(keys(var.lb_services), "api")
    error_message = "lb_services must contain api."
  }
}

variable "ecs_services" {
  description = "Every Fargate ECS service to watch for CPU and memory (service module `service_names`): { api = \"api\", worker = \"worker\", scheduler = \"scheduler\", web = \"web\" }."
  type        = map(string)
}

variable "db_instance_identifier" {
  description = "RDS instance identifier."
  type        = string
}

variable "db_max_connections" {
  description = "Connection ceiling the alarm measures against."
  type        = number
  default     = 200
}

variable "cache_replication_group_id" {
  description = "ElastiCache replication group id; nodes are <id>-001, <id>-002, ..."
  type        = string
}

variable "cache_node_count" {
  description = "Nodes in the replication group (cache module num_cache_clusters)."
  type        = number
  default     = 1
}

variable "target_5xx_threshold" {
  description = "5xx responses per 5 minutes (per app, and at the load balancer) that raise an alarm."
  type        = number
  default     = 25
}

variable "api_p95_latency_seconds" {
  description = "api p95 time to first byte that raises an alarm. Imports, generation and runs are queued jobs, never on a request path."
  type        = number
  default     = 3
}

variable "queue_log_pattern" {
  description = "CloudWatch Logs JSON filter matching the scheduler's periodic job queue line (its `queued` field becomes the JobQueueQueued metric)."
  type        = string
  default     = "{ $.msg = \"job queue\" }"
}

variable "sandbox_failure_log_pattern" {
  description = "CloudWatch Logs JSON filter matching the worker's line for a sandbox execution that failed for a reason other than the tests (SandboxFailures)."
  type        = string
  default     = "{ $.msg = \"sandbox failure\" }"
}

variable "sandbox_error_log_pattern" {
  description = "CloudWatch Logs JSON filter matching an error line of the sandbox service (SandboxErrors)."
  type        = string
  default     = "{ $.level = \"error\" || $.level = \"critical\" }"
}

variable "queue_queued_threshold" {
  description = "Jobs waiting to be claimed, sustained for 15 minutes, that raise an alarm."
  type        = number
  default     = 50
}

variable "sandbox_failure_threshold" {
  description = "Sandbox failures seen by the worker per 5 minutes that raise an alarm."
  type        = number
  default     = 5
}

variable "sandbox_error_threshold" {
  description = "Sandbox service error lines per 5 minutes that raise an alarm."
  type        = number
  default     = 0
}

variable "sandbox_cluster_name" {
  description = "The sandbox's ECS cluster (sandbox module cluster_name): CPU and memory alarms for the sandbox service."
  type        = string
}

variable "sandbox_service_name" {
  description = "The sandbox ECS service name (sandbox module service_name)."
  type        = string
}
