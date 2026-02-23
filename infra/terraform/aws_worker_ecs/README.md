# AWS ECS Worker for Ronin

This Terraform stack provisions an AWS-hosted "remote worker" that can run:
- `ronin worker gmail` on a 15-minute schedule (EventBridge)
- `ronin worker drift` weekly (EventBridge)

It is designed to connect to the existing RDS instance created by
`infra/terraform/aws_rds_public/`.

## Prerequisites

- An existing Ronin RDS stack applied (you need: VPC ID, subnet IDs, RDS SG ID, RDS secret ARN, and the RDS endpoint hostname).
- A worker container image pushed to ECR.
- Gmail OAuth files available as Secrets Manager secrets (optional until you enable Gmail).

## Usage

```bash
cd infra/terraform/aws_worker_ecs
terraform init
terraform plan \
  -var 'vpc_id=...' \
  -var 'subnet_ids=["subnet-...","subnet-..."]' \
  -var 'rds_security_group_id=sg-...' \
  -var 'rds_secret_arn=arn:aws:secretsmanager:...' \
  -var 'db_host=<rds_endpoint_hostname>'
terraform apply \
  -var 'vpc_id=...' \
  -var 'subnet_ids=["subnet-...","subnet-..."]' \
  -var 'rds_security_group_id=sg-...' \
  -var 'rds_secret_arn=arn:aws:secretsmanager:...' \
  -var 'db_host=<rds_endpoint_hostname>'
```

## Image Build + Push

After `terraform apply`, use the output `ecr_repository_url`:

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <ecr_repository_url>

# On Apple Silicon, ECS Fargate typically expects linux/amd64 unless you
# configure ARM64 runtime. Build an amd64 image explicitly.
docker buildx build --platform linux/amd64 \
  -t <ecr_repository_url>:latest \
  --push .
```

## Secrets

The task injects:
- `RONIN_RDS_SECRET_JSON` from the RDS master secret ARN (required)

Optional (only set these vars if you provide the secret ARNs):
- `RONIN_GMAIL_CREDENTIALS_JSON`
- `RONIN_GMAIL_TOKEN_JSON`

To enable Gmail polling, set:
- `gmail_enabled=true`
- `enable_gmail_schedule=true`
- `gmail_credentials_secret_arn` + `gmail_token_secret_arn`

## GitHub Action: Telegram Bot Deploy

This repo includes `.github/workflows/deploy_telegram_bot.yml` which deploys
an always-on ECS service running:

```bash
ronin telegram bot
```

The workflow uses AWS CLI to resolve Telegram secrets from SSM Parameter Store
or Secrets Manager before registering the task definition.

### 1) Store Telegram secrets in AWS

```bash
aws ssm put-parameter \
  --name /ronin/telegram/bot_token \
  --type SecureString \
  --value "<telegram_bot_token>" \
  --overwrite

aws ssm put-parameter \
  --name /ronin/telegram/chat_id \
  --type SecureString \
  --value "<telegram_chat_id>" \
  --overwrite
```

### 2) Configure GitHub

- Repository secret: `AWS_DEPLOY_ROLE_ARN`
  - IAM role trusted by GitHub OIDC
  - Needs permissions for ECR push, ECS task/service updates, EventBridge read,
    and reading SSM/SecretsManager refs.
- Optional repository variables:
  - `AWS_REGION` (default `us-east-1`)
  - `RONIN_NAME_PREFIX` (default `ronin`)
  - `RONIN_ECR_REPOSITORY` (defaults to `<prefix>-worker`)
  - `RONIN_ECS_CLUSTER` (defaults to `<prefix>-worker`)
  - `RONIN_BASE_TASK_FAMILY` (defaults to `<prefix>-worker`)
  - `RONIN_TELEGRAM_TASK_FAMILY` (defaults to `<prefix>-telegram-bot`)
  - `RONIN_TELEGRAM_SERVICE_NAME` (defaults to `<prefix>-telegram-bot`)
  - `RONIN_TELEGRAM_BOT_TOKEN_REF` (default `/ronin/telegram/bot_token`)
  - `RONIN_TELEGRAM_CHAT_ID_REF` (default `/ronin/telegram/chat_id`)
  - `RONIN_WORKER_SUBNET_IDS` (CSV fallback if auto-discovery fails)
  - `RONIN_WORKER_SECURITY_GROUP_IDS` (CSV fallback if auto-discovery fails)

### 3) Run deploy

- Manually trigger `Deploy Telegram Bot` from the Actions tab, or
- Push to `main` touching bot/deploy files and let the workflow run automatically.
