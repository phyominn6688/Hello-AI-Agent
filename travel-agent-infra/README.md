# Travel AI Agent — Infrastructure

AWS CDK (TypeScript) for the Travel AI Agent. Deploys a production-ready, scale-ready AWS stack from 10 TPS to 10k TPS without re-architecture.

This repo contains only infrastructure code. Business logic lives in [`travel-agent`](../travel-agent).

---

## Architecture

```
                        CloudFront
                            │
              ┌─────────────┴─────────────┐
         Amplify (Next.js)          API Gateway
                                         │
                                        ALB
                                         │
                              ECS Fargate (FastAPI)
                              [auto-scaling, stateless]
                                   │          │
                              Aurora PG    ElastiCache
                              Serverless    Redis Cluster
                              v2 + Proxy
                                   │
                         ┌─────────┴──────────┐
                        SQS                   S3
                         │
              ECS Workers / Lambda
              - Flight change monitoring
              - Push notifications (SNS)
              - Autonomous booking actions
              - Wallet pass generation
```

### Scale path (no re-architecture needed)

| Load | ECS tasks | Aurora | Redis |
|---|---|---|---|
| 10 TPS | 2 tasks | 1 ACU | 1 node |
| 1k TPS | Auto-scaled | ~8 ACU | 3 nodes |
| 10k TPS | Auto-scaled | ~64 ACU | Cluster + read replicas |

---

## Stacks

| Stack | File | What it deploys |
|---|---|---|
| **Network** | `lib/network-stack.ts` | VPC, public/private/isolated subnets, security groups, VPC flow logs |
| **Auth** | `lib/auth-stack.ts` | Cognito User Pool, Google IdP, hosted UI, app client (PKCE) |
| **Data** | `lib/data-stack.ts` | Aurora Serverless v2, RDS Proxy, ElastiCache Redis (cluster mode) |
| **Storage** | `lib/storage-stack.ts` | S3 (documents + frontend), CloudFront distribution |
| **Compute** | `lib/compute-stack.ts` | ECS Fargate backend service, ALB, auto-scaling (CPU + request-based) |
| **Async** | `lib/async-stack.ts` | SQS queues (main + notifications + DLQ), SNS topic, ECS worker services |

Stacks share resources via constructor props — CDK handles cross-stack dependencies automatically.

---

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Node.js 22+**
3. **CDK CLI** — `npm install -g aws-cdk`
4. **CDK bootstrapped** in your target account/region:
   ```bash
   cdk bootstrap aws://ACCOUNT_ID/us-east-1
   ```
5. **ECR repositories** created before first Compute/Async deploy:
   ```bash
   aws ecr create-repository --repository-name travel-agent-backend --region us-east-1
   ```
6. **SSM Parameters** set (used by CDK at synth time):
   ```bash
   # Google OAuth credentials (from Google Cloud Console)
   aws ssm put-parameter --name /travel-agent/dev/google-client-id \
     --value "YOUR_GOOGLE_CLIENT_ID" --type SecureString

   aws ssm put-parameter --name /travel-agent/dev/google-client-secret \
     --value "YOUR_GOOGLE_CLIENT_SECRET" --type SecureString

   # Anthropic API key (read by ECS tasks at runtime)
   aws ssm put-parameter --name /travel-agent/dev/anthropic-api-key \
     --value "sk-ant-..." --type SecureString
   ```

---

## Deployment

```bash
npm install

# Preview changes (no AWS calls made)
npm run diff

# Deploy dev environment
npm run deploy:dev

# Deploy prod environment
CDK_PROD_ACCOUNT=123456789012 \
BACKEND_IMAGE_TAG=v1.2.3 \
WORKER_IMAGE_TAG=v1.2.3 \
npm run deploy:prod
```

### Deploy a single stack

```bash
npx cdk deploy TravelAgent-dev-Network
npx cdk deploy TravelAgent-dev-Auth
npx cdk deploy TravelAgent-dev-Data
npx cdk deploy TravelAgent-dev-Storage
npx cdk deploy TravelAgent-dev-Compute
npx cdk deploy TravelAgent-dev-Async
```

### Destroy

```bash
# Dev only — prod stacks have deletion protection + RETAIN policies
npx cdk destroy --all --context env=dev
```

---

## Configuration

Environment sizing is defined in `config/dev.ts` and `config/prod.ts`.

### `config/dev.ts` (minimal, cost-optimized)

```typescript
backendDesiredCount: 1,   backendCpu: 512,   backendMemory: 1024
auroraMinCapacity: 0.5,   auroraMaxCapacity: 4     // scales to zero
redisNodeType: "cache.t4g.small",  redisNumShards: 1
```

### `config/prod.ts` (HA, auto-scaling)

```typescript
backendDesiredCount: 2,   backendCpu: 1024,  backendMemory: 2048
auroraMinCapacity: 1,     auroraMaxCapacity: 64
redisNodeType: "cache.r7g.large",  redisNumShards: 3, redisReplicasPerShard: 2
maxAzs: 3   // 3-AZ deployment
```

All config fields are typed in `config/types.ts`.

---

## CI/CD Integration

The `travel-agent` CI pipeline builds and pushes images to ECR, then triggers a CDK deploy by setting image tag environment variables:

```bash
# In your CI pipeline (GitHub Actions, CodePipeline, etc.):
IMAGE_TAG=$(git rev-parse --short HEAD)

# Build + push
docker build -t travel-agent-backend:$IMAGE_TAG ./backend
docker tag travel-agent-backend:$IMAGE_TAG $ECR_REPO:$IMAGE_TAG
docker push $ECR_REPO:$IMAGE_TAG

# Deploy (infra repo)
cd travel-agent-infra
BACKEND_IMAGE_TAG=$IMAGE_TAG \
WORKER_IMAGE_TAG=$IMAGE_TAG \
npx cdk deploy TravelAgent-prod-Compute TravelAgent-prod-Async \
  --context env=prod --require-approval never
```

The ECS service uses rolling deployments with circuit breaker + automatic rollback enabled.

---

## Outputs

After deploy, CDK prints these outputs (also in CloudFormation console):

| Stack | Output | Value |
|---|---|---|
| Auth | `UserPoolId` | Cognito user pool ID |
| Auth | `UserPoolClientId` | App client ID for frontend |
| Auth | `CognitoJwksUrl` | JWKS endpoint for backend JWT validation |
| Data | `DbProxyEndpoint` | RDS Proxy hostname (set as `DATABASE_URL` in ECS) |
| Data | `RedisEndpoint` | Redis cluster config endpoint |
| Data | `DbSecretArn` | Secrets Manager ARN for DB credentials |
| Storage | `CloudFrontDomain` | CloudFront URL for frontend |
| Storage | `DocumentBucketName` | S3 bucket for e-tickets / documents |
| Compute | `AlbDnsName` | ALB DNS (origin for CloudFront `/api/*`) |

Use these outputs to configure the frontend Amplify app and backend ECS environment variables.

---

## Security Notes

- All subnets follow least-privilege: ECS tasks in private subnets, DB in isolated subnets
- Security groups allow only the minimum required cross-service traffic
- RDS Proxy enforces TLS and connection pooling
- ElastiCache enforces in-transit encryption
- S3 buckets block all public access; CloudFront serves assets via OAC
- Secrets in AWS Secrets Manager and SSM Parameter Store — never in environment variables directly
- ECS task roles follow least-privilege IAM policies
- Prod Aurora and S3 have `RETAIN` removal policy — not deleted on stack destroy

---

## Structure

```
travel-agent-infra/
├── bin/
│   └── app.ts               # CDK app entry — loads env config, instantiates stacks
├── lib/
│   ├── network-stack.ts     # VPC, subnets, security groups
│   ├── auth-stack.ts        # Cognito + Google IdP
│   ├── data-stack.ts        # Aurora Serverless v2, RDS Proxy, ElastiCache
│   ├── compute-stack.ts     # ECS Fargate, ALB, auto-scaling
│   ├── async-stack.ts       # SQS, SNS, ECS workers
│   └── storage-stack.ts     # S3, CloudFront
├── config/
│   ├── types.ts             # EnvConfig interface
│   ├── dev.ts               # Dev environment sizing
│   └── prod.ts              # Prod environment sizing
├── package.json
└── tsconfig.json
```
