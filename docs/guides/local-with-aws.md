# Local stack against real AWS

`make up-aws` runs the same containers as `make up`, but the api, worker, scheduler and
migrate use a real KMS key and S3 bucket instead of Floci. Postgres, Redis, Mailpit, the
mock services, the sandbox and the web app stay local. Use it to check the AWS code paths
with your own account.

```bash
cd infra/terraform/envs/aws-dev && terraform apply -target=module.kms -target=module.storage   # or use your own key and bucket
cd -
cp deploy/compose/.env.aws.example deploy/compose/.env.aws    # OBJECTS_BUCKET and KMS_KEY_ID from terraform output
make up-aws
```

Credentials come from your AWS CLI profile (`AWS_PROFILE` in `.env.aws`), mounted
read-only into the containers that call AWS; nothing in the repository holds a static key.
The containers run with `TESTFORGE_CLOUD=aws`, `STORAGE=s3` and `KEY_MODE=kms`. The
sandbox never calls AWS in any mode and never sees the profile.

What changes: uploaded ZIPs, source snapshots and reports are written to and read from S3
(SSE-KMS), and model provider keys, GitHub tokens and webhook secrets are sealed with KMS
`Encrypt` under the `testforge:record` encryption context. Everything else behaves exactly
as in `make up`. Never commit `deploy/compose/.env.aws`.

`make down` stops the local containers; the bucket and key stay in your account until you
destroy them with Terraform.
