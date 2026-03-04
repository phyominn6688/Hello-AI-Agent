export interface EnvConfig {
  env: "dev" | "prod";
  account: string;
  region: string;

  // Network
  vpcCidr: string;
  maxAzs: number;

  // ECS compute
  backendDesiredCount: number;
  backendCpu: number;
  backendMemory: number;
  workerDesiredCount: number;
  workerCpu: number;
  workerMemory: number;

  // Aurora Serverless v2 (ACUs)
  auroraMinCapacity: number;
  auroraMaxCapacity: number;

  // ElastiCache Redis
  redisNodeType: string;
  redisNumShards: number;
  redisReplicasPerShard: number;

  // Optional custom domain
  domainName?: string;
  certificateArn?: string;

  // ECR image tags
  backendImageTag: string;
  workerImageTag: string;
}
