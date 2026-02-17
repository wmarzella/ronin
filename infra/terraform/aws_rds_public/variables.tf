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

variable "db_name" {
  type        = string
  description = "Initial database name"
  default     = "ronin"
}

variable "db_username" {
  type        = string
  description = "Master username (password is managed by AWS Secrets Manager)"
  default     = "ronin"
}

variable "instance_class" {
  type        = string
  description = "RDS instance class"
  default     = "db.t3.micro"
}

variable "allocated_storage_gb" {
  type        = number
  description = "Initial allocated storage (GB)"
  default     = 20
}

variable "backup_retention_days" {
  type        = number
  description = "Backup retention period (days)"
  default     = 1
}

variable "additional_allowed_cidrs" {
  type        = list(string)
  description = "Additional IPv4 CIDR blocks allowed to connect to Postgres"
  default     = []
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR for the dedicated Ronin VPC"
  default     = "10.77.0.0/16"
}
