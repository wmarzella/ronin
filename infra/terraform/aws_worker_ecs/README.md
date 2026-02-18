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

docker build -t ronin-worker:latest .
docker tag ronin-worker:latest <ecr_repository_url>:latest
docker push <ecr_repository_url>:latest
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
