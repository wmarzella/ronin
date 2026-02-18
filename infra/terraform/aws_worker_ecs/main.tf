locals {
  tags = {
    Project = "ronin"
    Managed = "terraform"
  }

  container_name = "ronin-worker"

  container_environment = [
    {
      name  = "RONIN_DB_BACKEND"
      value = "postgres"
    },
    {
      name  = "RONIN_GMAIL_ENABLED"
      value = var.gmail_enabled ? "1" : "0"
    },
    {
      name  = "RONIN_GMAIL_QUERY"
      value = var.gmail_query
    },
  ]

  container_secrets = concat(
    [
      {
        name      = "RONIN_RDS_SECRET_JSON"
        valueFrom = var.rds_secret_arn
      }
    ],
    var.gmail_credentials_secret_arn != "" ? [
      {
        name      = "RONIN_GMAIL_CREDENTIALS_JSON"
        valueFrom = var.gmail_credentials_secret_arn
      }
    ] : [],
    var.gmail_token_secret_arn != "" ? [
      {
        name      = "RONIN_GMAIL_TOKEN_JSON"
        valueFrom = var.gmail_token_secret_arn
      }
    ] : []
  )
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.name_prefix}-worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_ecs_cluster" "worker" {
  name = "${var.name_prefix}-worker"
  tags = local.tags
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name_prefix        = "${var.name_prefix}-worker-exec-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_default" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      var.rds_secret_arn,
      var.gmail_credentials_secret_arn,
      var.gmail_token_secret_arn,
    ])
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "${var.name_prefix}-worker-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

resource "aws_iam_role" "task" {
  name_prefix        = "${var.name_prefix}-worker-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.tags
}

resource "aws_security_group" "worker" {
  name_prefix = "${var.name_prefix}-worker-"
  description = "Ronin worker ECS tasks"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_egress_rule" "worker_all_egress" {
  security_group_id = aws_security_group.worker.id
  description       = "Allow all outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_worker" {
  security_group_id            = var.rds_security_group_id
  description                  = "Postgres from Ronin worker"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.worker.id
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.worker_cpu)
  memory                   = tostring(var.worker_memory)

  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn      = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"
      essential = true

      environment = local.container_environment
      secrets     = local.container_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = local.tags
}

data "aws_iam_policy_document" "events_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events" {
  name_prefix        = "${var.name_prefix}-worker-events-"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "events_policy" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.worker.arn]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.worker.arn]
    }
  }

  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.task_execution.arn, aws_iam_role.task.arn]
  }
}

resource "aws_iam_role_policy" "events_policy" {
  name   = "${var.name_prefix}-worker-events"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events_policy.json
}

resource "aws_cloudwatch_event_rule" "gmail" {
  count               = var.enable_gmail_schedule ? 1 : 0
  name                = "${var.name_prefix}-worker-gmail"
  description         = "Run Ronin Gmail worker"
  schedule_expression = "rate(15 minutes)"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "gmail" {
  count     = var.enable_gmail_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.gmail[0].name
  target_id = "ecs"
  arn       = aws_ecs_cluster.worker.arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    task_count          = 1
    platform_version    = "LATEST"

    network_configuration {
      subnets          = var.subnet_ids
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = true
    }
  }

  input = jsonencode({
    containerOverrides = [
      {
        name    = local.container_name
        command = ["worker", "gmail"]
      }
    ]
  })
}

resource "aws_cloudwatch_event_rule" "drift" {
  count               = var.enable_drift_schedule ? 1 : 0
  name                = "${var.name_prefix}-worker-drift"
  description         = "Run Ronin drift worker"
  schedule_expression = "cron(0 0 ? * SUN *)"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "drift" {
  count     = var.enable_drift_schedule ? 1 : 0
  rule      = aws_cloudwatch_event_rule.drift[0].name
  target_id = "ecs"
  arn       = aws_ecs_cluster.worker.arn
  role_arn  = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.worker.arn
    launch_type         = "FARGATE"
    task_count          = 1
    platform_version    = "LATEST"

    network_configuration {
      subnets          = var.subnet_ids
      security_groups  = [aws_security_group.worker.id]
      assign_public_ip = true
    }
  }

  input = jsonencode({
    containerOverrides = [
      {
        name    = local.container_name
        command = ["worker", "drift"]
      }
    ]
  })
}
