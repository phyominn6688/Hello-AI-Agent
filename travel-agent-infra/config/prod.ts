import type { EnvConfig } from "./types";

const prodConfig: EnvConfig = {
  env: "prod",
  account: process.env.CDK_PROD_ACCOUNT!,
  region: "us-east-1",

  // Network — 3 AZs for true HA
  vpcCidr: "10.1.0.0/16",
  maxAzs: 3,

  // Compute — auto-scaling from 2→20 tasks
  backendDesiredCount: 2,
  backendCpu: 1024,
  backendMemory: 2048,
  workerDesiredCount: 2,
  workerCpu: 512,
  workerMemory: 1024,

  // Aurora Serverless v2 — 1→64 ACUs, no interruption scaling
  auroraMinCapacity: 1,
  auroraMaxCapacity: 64,

  // ElastiCache cluster mode — 3 shards × 2 replicas
  redisNodeType: "cache.r7g.large",
  redisNumShards: 3,
  redisReplicasPerShard: 2,

  // Custom domain
  domainName: "travelagent.example.com",
  certificateArn: process.env.CERTIFICATE_ARN,

  backendImageTag: process.env.BACKEND_IMAGE_TAG!,
  workerImageTag: process.env.WORKER_IMAGE_TAG!,
};

export default prodConfig;
