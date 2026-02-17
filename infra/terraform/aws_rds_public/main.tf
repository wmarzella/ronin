data "aws_availability_zones" "available" {
  state = "available"
}

data "http" "myip" {
  url = "https://checkip.amazonaws.com/"
}

resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  db_identifier = "${var.name_prefix}-${random_id.suffix.hex}"
  my_ip_cidr    = "${chomp(data.http.myip.response_body)}/32"
  tags = {
    Project = "ronin"
    Managed = "terraform"
  }
}

resource "aws_vpc" "ronin" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = "${local.db_identifier}-vpc" })
}

resource "aws_internet_gateway" "ronin" {
  vpc_id = aws_vpc.ronin.id
  tags   = merge(local.tags, { Name = "${local.db_identifier}-igw" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ronin.id
  tags   = merge(local.tags, { Name = "${local.db_identifier}-public-rt" })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.ronin.id
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.ronin.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags = merge(
    local.tags,
    { Name = "${local.db_identifier}-public-a" }
  )
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.ronin.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 2)
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true
  tags = merge(
    local.tags,
    { Name = "${local.db_identifier}-public-b" }
  )
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "ronin_db" {
  name_prefix = "${var.name_prefix}-db-"
  description = "Ronin Postgres (public RDS, SG-restricted)"
  vpc_id      = aws_vpc.ronin.id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_my_ip" {
  security_group_id = aws_security_group.ronin_db.id
  description       = "Postgres from current public IP"
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  cidr_ipv4         = local.my_ip_cidr
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_additional" {
  for_each          = toset(var.additional_allowed_cidrs)
  security_group_id = aws_security_group.ronin_db.id
  description       = "Postgres from additional CIDR"
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "all_egress" {
  security_group_id = aws_security_group.ronin_db.id
  description       = "Allow all outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_db_subnet_group" "ronin" {
  name       = "${local.db_identifier}-subnets"
  subnet_ids = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  tags       = local.tags
}

resource "aws_db_instance" "ronin" {
  identifier              = local.db_identifier
  engine                  = "postgres"
  instance_class          = var.instance_class
  allocated_storage       = var.allocated_storage_gb
  storage_encrypted       = true
  publicly_accessible     = true
  multi_az                = false
  backup_retention_period = var.backup_retention_days

  db_name  = var.db_name
  username = var.db_username

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.ronin.name
  vpc_security_group_ids = [aws_security_group.ronin_db.id]

  # Keep this dev-friendly. If you want deletion safety, set deletion_protection=true.
  deletion_protection = false
  skip_final_snapshot = true
  apply_immediately   = true

  tags = local.tags
}
