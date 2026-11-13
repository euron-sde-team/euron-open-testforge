variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "vpc_id" {
  description = "VPC the sandbox hosts run in."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the instances and task interfaces (no public IP)."
  type        = list(string)
}

variable "image" {
  description = "Full sandbox image reference, e.g. <registry>/testforge-prod/sandbox:<tag>."
  type        = string
}

variable "port" {
  description = "Port the sandbox service listens on (PORT)."
  type        = number
  default     = 8080
}

variable "namespace_id" {
  description = "Cloud Map private DNS namespace to register sandbox.<namespace> in (service module namespace_id)."
  type        = string
}

variable "namespace_name" {
  description = "Name of that namespace (service module namespace_name), used to build the url output."
  type        = string
}

variable "worker_security_group_id" {
  description = "The worker tasks' security group (service module security_group_ids.worker): the only source allowed in, and it gets the matching egress rule."
  type        = string
}

variable "secrets" {
  description = "ECS secrets for the sandbox (secrets module sandbox_secrets: SANDBOX_SECRET only)."
  type = list(object({
    name      = string
    valueFrom = string
  }))
}

variable "environment" {
  description = "Extra sandbox environment, e.g. LOG_LEVEL. Never secrets, and never a database, storage or provider setting."
  type        = map(string)
  default     = {}
}

variable "kms_key_arn" {
  description = "CMK for the root volumes and for decrypting the injected secret."
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group for the sandbox (observability module log_group_names.sandbox)."
  type        = string
}

variable "seccomp_profile_json" {
  description = "The sandbox seccomp profile (infra/docker/sandbox-seccomp.json): the Docker daemon default on the sandbox hosts."
  type        = string
  validation {
    condition     = can(jsondecode(var.seccomp_profile_json).syscalls)
    error_message = "seccomp_profile_json must be a Docker seccomp profile (JSON with a syscalls list)."
  }
}

variable "ami_id" {
  description = "Sandbox host AMI. Null: the latest ECS-optimized Amazon Linux 2023 ARM64 AMI."
  type        = string
  default     = null
}

variable "instance_type" {
  description = "ARM64 instance type for sandbox hosts (one sandbox task each). Compute optimized (c7g) suits test runs."
  type        = string
  default     = "c7g.large"
}

variable "root_volume_gib" {
  description = "Root volume size of a sandbox host (images and logs; run scratch space is tmpfs)."
  type        = number
  default     = 30
}

variable "min_instances" {
  description = "Sandbox hosts kept running."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Most sandbox hosts the capacity provider may run. At least max_count (one task per host) plus one for rolling deploys."
  type        = number
  default     = 4
}

variable "desired_count" {
  description = "Sandbox tasks kept running (each runs one test run at a time, one task per host)."
  type        = number
  default     = 2
}

variable "max_count" {
  description = "Most sandbox tasks CPU autoscaling may run. Equal to desired_count disables autoscaling."
  type        = number
  default     = 2
  validation {
    condition     = var.max_count >= 1
    error_message = "max_count must be at least 1."
  }
}

variable "task_cpu" {
  description = "CPU units per sandbox task (1024 = one vCPU); compose gives the sandbox 2 CPUs."
  type        = number
  default     = 2048
}

variable "task_memory" {
  description = "Memory per sandbox task in MiB (compose mem_limit 3g), including the /tmp tmpfs."
  type        = number
  default     = 3072
}

variable "tmp_mib" {
  description = "tmpfs size for /tmp (each run's workspace and jail) in MiB (compose: 1g)."
  type        = number
  default     = 1024
}

variable "max_processes" {
  description = "nproc ulimit for the sandbox user (compose pids_limit 1024)."
  type        = number
  default     = 1024
}

variable "cpu_target_percent" {
  description = "Average sandbox CPU the autoscaler aims for (with max_count > desired_count)."
  type        = number
  default     = 60
}

variable "container_insights" {
  description = "ECS Container Insights on the sandbox cluster (enabled, enhanced or disabled)."
  type        = string
  default     = "enabled"
}
