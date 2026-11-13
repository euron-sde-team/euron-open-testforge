# `network` module

The VPC Euron Open TestForge runs in, across `az_count` availability zones:

- Public subnets hold only the load balancer and the NAT gateways; the api, worker, scheduler and web tasks, the sandbox hosts, RDS and ElastiCache all live in the private subnets.
- NAT (one per AZ, or a single one with `single_nat_gateway`) gives the private side its route out: model providers, GitHub, outbound webhooks, and ECR, ECS and CloudWatch Logs for the sandbox hosts.
- An S3 gateway endpoint keeps uploaded ZIPs, source snapshots and reports off the NAT.
- Optional KMS and Secrets Manager interface endpoints (`enable_interface_endpoints`, on in aws-prod) keep sealing and secret injection inside the VPC.
- Encrypted VPC flow logs, and the default security group locked down to no rules.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `name_prefix` | Prefix for every resource name, e.g. "testforge-prod". | `string` | required |
| `cidr_block` | VPC CIDR. Split into /20 public subnets (low half) and /20 private subnets (high half). | `string` | `"10.56.0.0/16"` |
| `az_count` | Number of availability zones to span (2 or 3). | `number` | `3` |
| `single_nat_gateway` | One shared NAT gateway (cheaper, dev) instead of one per AZ (resilient, prod). | `bool` | `true` |
| `logs_kms_key_arn` | CMK that encrypts the flow-log group (its key policy must allow CloudWatch Logs). Null uses CloudWatch's default encryption. | `string` | `null` |
| `flow_log_retention_days` | Retention for VPC flow logs (REJECT + ACCEPT) in CloudWatch Logs. 0 disables flow logs. | `number` | `30` |
| `enable_interface_endpoints` | Create KMS and Secrets Manager interface endpoints so those calls never leave the VPC. | `bool` | `true` |

## Outputs

| Name | Description |
|---|---|
| `vpc_id` | VPC id. |
| `vpc_cidr_block` | VPC CIDR (the api trusts X-Forwarded-For only from it: FORWARDED_ALLOW_IPS). |
| `public_subnet_ids` | Public subnets (ALB, NAT). |
| `private_subnet_ids` | Private subnets (ECS tasks, sandbox hosts, RDS, ElastiCache), one per AZ. |
