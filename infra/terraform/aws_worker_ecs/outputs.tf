output "ecr_repository_url" {
  value = aws_ecr_repository.worker.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.worker.name
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.worker.arn
}

output "worker_security_group_id" {
  value = aws_security_group.worker.id
}

output "gmail_schedule_rule_name" {
  value = try(aws_cloudwatch_event_rule.gmail[0].name, "")
}

output "drift_schedule_rule_name" {
  value = try(aws_cloudwatch_event_rule.drift[0].name, "")
}
