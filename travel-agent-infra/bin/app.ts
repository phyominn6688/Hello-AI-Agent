#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { NetworkStack } from "../lib/network-stack";
import { AuthStack } from "../lib/auth-stack";
import { DataStack } from "../lib/data-stack";
import { ComputeStack } from "../lib/compute-stack";
import { AsyncStack } from "../lib/async-stack";
import { StorageStack } from "../lib/storage-stack";
import devConfig from "../config/dev";
import prodConfig from "../config/prod";
import type { EnvConfig } from "../config/types";

const app = new cdk.App();

const envName = app.node.tryGetContext("env") as string || "dev";
const config: EnvConfig = envName === "prod" ? prodConfig : devConfig;

const env: cdk.Environment = {
  account: config.account,
  region: config.region,
};

const stackPrefix = `TravelAgent-${envName}`;

// Stack 1: VPC, subnets, security groups
const networkStack = new NetworkStack(app, `${stackPrefix}-Network`, { env, config });

// Stack 2: Cognito user pool + social IdPs
const authStack = new AuthStack(app, `${stackPrefix}-Auth`, { env, config });

// Stack 3: Aurora, ElastiCache, RDS Proxy
const dataStack = new DataStack(app, `${stackPrefix}-Data`, {
  env,
  config,
  vpc: networkStack.vpc,
  dbSecurityGroup: networkStack.dbSecurityGroup,
  cacheSecurityGroup: networkStack.cacheSecurityGroup,
});

// Stack 4: S3 + CloudFront
const storageStack = new StorageStack(app, `${stackPrefix}-Storage`, { env, config });

// Stack 5: ECS Fargate backend + ALB
const computeStack = new ComputeStack(app, `${stackPrefix}-Compute`, {
  env,
  config,
  vpc: networkStack.vpc,
  appSecurityGroup: networkStack.appSecurityGroup,
  dbSecret: dataStack.dbSecret,
  dbProxyEndpoint: dataStack.proxyEndpoint,
  redisEndpoint: dataStack.redisEndpoint,
  documentBucket: storageStack.documentBucket,
  userPoolId: authStack.userPool.userPoolId,
  userPoolClientId: authStack.userPoolClient.userPoolClientId,
});

// Stack 6: SQS queues + ECS workers + Lambda
const asyncStack = new AsyncStack(app, `${stackPrefix}-Async`, {
  env,
  config,
  vpc: networkStack.vpc,
  workerSecurityGroup: networkStack.appSecurityGroup,
  dbSecret: dataStack.dbSecret,
  dbProxyEndpoint: dataStack.proxyEndpoint,
  redisEndpoint: dataStack.redisEndpoint,
});

// Tag all resources
cdk.Tags.of(app).add("Project", "TravelAgent");
cdk.Tags.of(app).add("Environment", envName);
cdk.Tags.of(app).add("ManagedBy", "CDK");
