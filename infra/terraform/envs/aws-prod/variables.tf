variable "region" {
  description = "AWS region."
  type        = string
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "prod"
}

variable "extra_tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}

variable "name_prefix" {
  description = "Prefix for every resource name (at most 24 characters); the objects bucket name derives from it, so make it globally unique (e.g. \"acme-testforge-prod\")."
  type        = string
}

variable "hostname" {
  description = "Public host name of the app and API, e.g. testforge.example.com."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate in the same region covering hostname."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the alias record and the DKIM records. Null: create them yourself (load_balancer_dns_name and dkim_records outputs)."
  type        = string
  default     = null
}

variable "mail_domain" {
  description = "Domain member notices are sent from (an SES domain identity), e.g. testforge.example.com."
  type        = string
}

variable "mail_from_address" {
  description = "From address of member notices (MAIL_FROM), on mail_domain, e.g. no-reply@testforge.example.com."
  type        = string
}

variable "image_tag" {
  description = "Image tag to deploy (the git commit or a release)."
  type        = string
}

variable "alarm_email" {
  description = "Alarm notification address."
  type        = string
  default     = null
}

variable "api_extra_environment" {
  description = "Extra environment for the api, worker, scheduler and migrate (any setting of core/config.py, e.g. RUN_WALL_S). Never secrets."
  type        = map(string)
  default     = {}
}

variable "sandbox_extra_environment" {
  description = "Extra sandbox environment (e.g. LOG_LEVEL). Never secrets."
  type        = map(string)
  default     = {}
}

variable "github_api_url" {
  description = "GITHUB_API_URL: GitHub's REST API, or a GitHub Enterprise server's."
  type        = string
  default     = "https://api.github.com"
}

variable "worker_concurrency" {
  description = "WORKER_CONCURRENCY: jobs one worker task runs at once."
  type        = number
  default     = 4
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "sandbox_instance_type" {
  description = "ARM64 instance type for sandbox hosts (one sandbox task each)."
  type        = string
  default     = "c7g.large"
}

variable "sandbox_ami_id" {
  description = "AMI for sandbox hosts. Null: the latest ECS-optimized Amazon Linux 2023 ARM64 AMI."
  type        = string
  default     = null
}

variable "sandbox_desired_count" {
  description = "Sandbox tasks (and hosts) kept running; each runs one test run at a time. CPU autoscaling may add up to 12."
  type        = number
  default     = 3
}

variable "queue_queued_threshold" {
  description = "Jobs waiting to be claimed, sustained 15 minutes, that raise an alarm."
  type        = number
  default     = 50
}

variable "metrics_allowed_cidrs" {
  description = "Source CIDRs allowed to scrape the api's /metrics through the load balancer."
  type        = list(string)
  default     = []
}

variable "worker_metrics_cidrs" {
  description = "In-VPC Prometheus CIDRs allowed to scrape the worker's /metrics on port 9464. Empty: no worker ingress."
  type        = list(string)
  default     = []
}

variable "extra_egress" {
  description = "Extra egress for the api, worker and scheduler beyond HTTPS 443 (a self-hosted model provider, a GitHub Enterprise server or a webhook receiver), as { cidr, port } pairs."
  type = list(object({
    cidr = string
    port = number
  }))
  default = []
}
