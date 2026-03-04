import type { EnvConfig } from "./types";

const devConfig: EnvConfig = {
  env: "dev",
  account: process.env.CDK_DEFAULT_ACCOUNT!,
  region: process.env.CDK_DEFAULT_REGION || "us-east-1",

  // Network
  vpcCidr: "10.0.0.0/16",
  maxAzs: 2,

  // Compute — minimal for dev
  backendDesiredCount: 1,
  backendCpu: 512,
  backendMemory: 1024,
  workerDesiredCount: 1,
  workerCpu: 256,
  workerMemory: 512,

  // Aurora Serverless v2 — min capacity to allow scale-to-zero in dev
  auroraMinCapacity: 0.5,
  auroraMaxCapacity: 4,

  // ElastiCache — single node in dev
  redisNodeType: "cache.t4g.small",
  redisNumShards: 1,
  redisReplicasPerShard: 0,

  // Domain — dev uses CloudFront default domain
  domainName: undefined,
  certificateArn: undefined,

  // Container image tags (set by CI pipeline; default to 'latest' for dev)
  backendImageTag: process.env.BACKEND_IMAGE_TAG || "latest",
  workerImageTag: process.env.WORKER_IMAGE_TAG || "latest",
};

export default devConfig;
