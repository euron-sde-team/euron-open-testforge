output "log_group_names" {
  description = "Log group per app: { api, worker, scheduler, web, migrate, sandbox } (service and sandbox modules)."
  value       = { for k, g in aws_cloudwatch_log_group.app : k => g.name }
}

output "alarm_topic_arn" {
  description = "SNS topic receiving every alarm."
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = aws_cloudwatch_dashboard.this.dashboard_name
}

output "metrics_namespace" {
  description = "Namespace of the metrics extracted from the scheduler, worker and sandbox logs."
  value       = local.namespace
}
