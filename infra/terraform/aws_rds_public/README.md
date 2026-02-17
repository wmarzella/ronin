# AWS RDS Postgres (Public) for Ronin

This Terraform stack provisions a publicly reachable Postgres database on Amazon RDS.

It is intended to be used as the shared source-of-truth database for the split
Local Agent + Remote Worker architecture.

Security posture:
- The RDS instance is public, but access is restricted at the security-group level.
- By default, it only allows inbound Postgres (5432) from your current public IP.

## Usage

```bash
cd infra/terraform/aws_rds_public
terraform init
terraform plan
terraform apply
terraform output
```

Outputs include the RDS endpoint, port, db name, username, and the Secrets Manager
secret ARN (AWS-managed master password).

Notes:
- Do not commit `terraform.tfstate` (it can contain sensitive resource metadata). This repo ignores state files.
- For backups, prefer RDS automated backups + manual snapshots. Local `pg_dump` must match the server major version.

To fetch the password:

```bash
aws secretsmanager get-secret-value \
  --secret-id <secret_arn> \
  --query SecretString \
  --output text
```

The returned JSON contains `password`.
