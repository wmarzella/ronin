variable "aws_region" {
  type        = string
  description = "AWS region to deploy into"
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for naming AWS resources"
  default     = "ronin"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID to run ECS tasks in (should match RDS VPC)"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for ECS tasks (use public subnets for outbound internet)"
}

variable "rds_security_group_id" {
  type        = string
  description = "Security group ID attached to the RDS instance"
}

variable "rds_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for the RDS master user secret (injected as RONIN_RDS_SECRET_JSON)"
}

variable "db_host" {
  type        = string
  description = "Postgres host (RDS endpoint)"
}

variable "db_port" {
  type        = number
  description = "Postgres port"
  default     = 5432
}

variable "db_name" {
  type        = string
  description = "Database name"
  default     = "ronin"
}

variable "worker_image_tag" {
  type        = string
  description = "ECR image tag to run"
  default     = "latest"
}

variable "worker_cpu" {
  type        = number
  description = "Fargate CPU units (e.g. 256, 512, 1024)"
  default     = 512
}

variable "worker_memory" {
  type        = number
  description = "Fargate memory (MiB) (e.g. 512, 1024, 2048)"
  default     = 2048
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch logs retention"
  default     = 14
}

variable "gmail_enabled" {
  type        = bool
  description = "If true, set RONIN_GMAIL_ENABLED=1 inside the task"
  default     = false
}

variable "gmail_query" {
  type        = string
  description = "Gmail search query"
  default     = "newer_than:1d"
}

variable "gmail_credentials_secret_arn" {
  type        = string
  description = "Optional Secrets Manager ARN that returns credentials.json content"
  default     = ""
}

variable "gmail_token_secret_arn" {
  type        = string
  description = "Optional Secrets Manager ARN that returns gmail_token.json content"
  default     = ""
}

variable "enable_gmail_schedule" {
  type        = bool
  description = "Create EventBridge schedule for `ronin worker gmail`"
  default     = false
}

variable "enable_drift_schedule" {
  type        = bool
  description = "Create EventBridge schedule for `ronin worker drift`"
  default     = false
}
