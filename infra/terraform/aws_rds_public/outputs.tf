output "aws_region" {
  value = var.aws_region
}

output "db_identifier" {
  value = aws_db_instance.ronin.identifier
}

output "vpc_id" {
  value = aws_vpc.ronin.id
}

output "public_subnet_ids" {
  value = [aws_subnet.public_a.id, aws_subnet.public_b.id]
}

output "db_endpoint" {
  value = aws_db_instance.ronin.address
}

output "db_port" {
  value = aws_db_instance.ronin.port
}

output "db_name" {
  value = aws_db_instance.ronin.db_name
}

output "db_username" {
  value = aws_db_instance.ronin.username
}

output "db_secret_arn" {
  value = aws_db_instance.ronin.master_user_secret[0].secret_arn
}

output "allowed_ip_cidr" {
  value = local.my_ip_cidr
}

output "dsn_template" {
  value = "postgresql://${aws_db_instance.ronin.username}:<PASSWORD>@${aws_db_instance.ronin.address}:${aws_db_instance.ronin.port}/${aws_db_instance.ronin.db_name}?sslmode=require"
}
