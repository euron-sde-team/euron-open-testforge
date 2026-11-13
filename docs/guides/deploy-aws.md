# Deploy to AWS

The Terraform in `infra/terraform/` builds a production deployment. The maintainers
develop against the local emulator: the AWS environments pass `terraform validate`,
tflint and checkov, and the full `aws-dev` environment is planned, applied, re-planned and
destroyed against Floci in the gates (`make tf-aws-on-floci`). Applying it to a real
account is your step; read the plan before you apply.

## What it builds

| Module | Resources |
| --- | --- |
| `network` | VPC across availability zones, public subnets for the load balancer and NAT only, private subnets for everything else, flow logs, optional interface endpoints |
| `database` | RDS PostgreSQL 16 in private subnets, encrypted with the CMK, TLS enforced; it also holds the job queue |
| `cache` | ElastiCache (Valkey) with `allkeys-lru`, TLS and AUTH, for rate limits and the snapshot file index |
| `storage` | The objects bucket (`uploads/`, `snapshots/`, `reports/`), SSE-KMS, public access blocked |
| `kms` | The key that seals provider keys, GitHub tokens and webhook secrets and encrypts everything at rest |
| `secrets` | Secrets Manager: `<prefix>/app` (`SESSION_SECRET`, `API_KEY_PEPPER`), `<prefix>/sandbox` (`SANDBOX_SECRET`), and the database and cache URLs |
| `ecr` | Repositories for the `api`, `sandbox` and `web` images |
| `email` | An SES domain identity with DKIM for member notices |
| `service` | ECS Fargate services for api, worker, scheduler and web behind an ALB with WAF, a one-off `migrate` task definition, and a Cloud Map namespace |
| `sandbox` | An ECS cluster on EC2 (Auto Scaling group, launch template, ECS-optimized ARM64 AMI) running the sandbox tasks, one per host, registered as `sandbox.<prefix>.internal` |
| `observability` | CloudWatch log groups per app, metric filters (`JobQueueQueued`, `SandboxFailures`, `SandboxErrors`), alarms to an SNS topic, and a dashboard |

Each module's README lists its inputs and outputs.

### Why the sandbox is on EC2

nsjail builds each run's jail from user namespaces, which needs Docker's default seccomp
profile plus the namespace calls ([sandbox.md](../architecture/sandbox.md)). Fargate cannot
take a custom seccomp profile, so the sandbox runs on hosts of its own whose Docker daemon
uses `infra/docker/sandbox-seccomp.json` as its default. The task drops every capability,
has a read-only root and tmpfs scratch, and a task role with no policy; the hosts require
IMDSv2 with a hop limit of 1 and block task access to instance metadata; the sandbox
security group admits only the worker and has no egress rule at all.

## Steps

```bash
cd infra/terraform/envs/aws-dev
cp terraform.tfvars.example terraform.tfvars   # region, name prefix, host name, ACM certificate, mail domain, image tag
cp backend.tf.example backend.tf               # optional: remote state in S3
terraform init
terraform apply -target=module.ecr             # the image repositories first
terraform output ecr_repositories
```

Build the three images for ARM64 (the default `cpu_architecture` and the sandbox's
Graviton instances) and push them with the tag you set as `image_tag`:

```bash
docker buildx build --platform linux/arm64 -f infra/docker/server.Dockerfile --target api \
  -t <api repository>:0.1.0 --push apps/api
docker buildx build --platform linux/arm64 -f infra/docker/sandbox.Dockerfile --target sandbox \
  -t <sandbox repository>:0.1.0 --push apps/api
docker buildx build --platform linux/arm64 -f infra/docker/web.Dockerfile \
  -t <web repository>:0.1.0 --push apps/web
```

Then apply everything and run the migrations as a one-off task:

```bash
terraform apply
terraform output run_task      # cluster, task definition, subnets, security groups
aws ecs run-task --launch-type FARGATE --cluster <cluster> --task-definition <task definition> \
  --network-configuration 'awsvpcConfiguration={subnets=[<subnets>],securityGroups=[<security groups>]}'
```

The same task definition creates the first admin with a command override
(`["create-admin", "--email", "you@example.com"]` and `TESTFORGE_ADMIN_PASSWORD` in the
override's environment). `make aws-plan ENV=aws-dev` runs `terraform plan` for an
environment.

Then add the DKIM records from `terraform output dkim_records` to your DNS (done for you
with `route53_zone_id`) and point your host name at `load_balancer_dns_name`. SES starts in
its sandbox: ask AWS to lift it before notifying members outside verified addresses.

`aws-prod` is the same with production settings: three availability zones, a NAT gateway
per zone, a Multi-AZ database, a cache replica with automatic failover, sandbox hosts across
every zone, deletion protection, interface endpoints and a year of log retention.

## Settings worth knowing

| tfvars | Effect |
| --- | --- |
| `sandbox_desired_count` | Sandbox tasks, one host each; each runs one test run at a time |
| `worker_concurrency` | Jobs one worker task runs at once |
| `queue_queued_threshold` | Jobs waiting for 15 minutes that raise the queue alarm |
| `github_api_url` | A GitHub Enterprise server instead of github.com |
| `extra_egress` | A self-hosted model inside the VPC on a port other than 443 |
| `api_extra_environment`, `sandbox_extra_environment` | Extra non-secret settings (any name in `core/config.py`); never a credential for the sandbox |
| `alarm_email` | Subscribes an address to the alarm topic |
| `metrics_allowed_cidrs` | Source addresses allowed to read `/metrics` through the load balancer |

## After deploying

- Sign in as the admin, create an organization and a project, and add a model provider
  per project (or a local one inside the VPC).
- Watch the job queue and sandbox failure alarms while people use it the first time; add
  sandbox tasks if runs wait ([operations.md](operations.md)).
- If anyone outside your organization can upload code, add a kernel boundary around the
  sandbox (gVisor or Kata) or keep it on dedicated hosts
  ([sandbox.md](../architecture/sandbox.md)).
