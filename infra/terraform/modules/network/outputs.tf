output "vpc_id" {
  description = "VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "VPC CIDR (the api trusts X-Forwarded-For only from it: FORWARDED_ALLOW_IPS)."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnets (ALB, NAT)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnets (ECS tasks, sandbox hosts, RDS, ElastiCache), one per AZ."
  value       = aws_subnet.private[*].id
}
