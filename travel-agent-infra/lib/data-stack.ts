import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";
import * as elasticache from "aws-cdk-lib/aws-elasticache";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
  vpc: ec2.Vpc;
  dbSecurityGroup: ec2.SecurityGroup;
  cacheSecurityGroup: ec2.SecurityGroup;
}

export class DataStack extends cdk.Stack {
  readonly dbSecret: secretsmanager.Secret;
  readonly redisAuthSecret: secretsmanager.Secret;
  readonly proxyEndpoint: string;
  readonly redisEndpoint: string;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const { config, vpc, dbSecurityGroup, cacheSecurityGroup } = props;

    // ── Aurora PostgreSQL Serverless v2 ────────────────────────────────────────

    this.dbSecret = new secretsmanager.Secret(this, "DbSecret", {
      secretName: `/travel-agent/${config.env}/db-credentials`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: "travelagent" }),
        generateStringKey: "password",
        excludePunctuation: true,
        includeSpace: false,
      },
    });

    const dbSubnetGroup = new rds.SubnetGroup(this, "DbSubnetGroup", {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      description: "Travel Agent Aurora subnet group",
    });

    const cluster = new rds.DatabaseCluster(this, "AuroraCluster", {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_4,
      }),
      serverlessV2MinCapacity: config.auroraMinCapacity,
      serverlessV2MaxCapacity: config.auroraMaxCapacity,
      writer: rds.ClusterInstance.serverlessV2("Writer"),
      readers:
        config.env === "prod"
          ? [rds.ClusterInstance.serverlessV2("Reader", { scaleWithWriter: true })]
          : [],
      credentials: rds.Credentials.fromSecret(this.dbSecret),
      defaultDatabaseName: "travelagent",
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [dbSecurityGroup],
      subnetGroup: dbSubnetGroup,
      backup: {
        retention: config.env === "prod" ? cdk.Duration.days(14) : cdk.Duration.days(1),
        preferredWindow: "03:00-04:00",
      },
      storageEncrypted: true,
      deletionProtection: config.env === "prod",
      removalPolicy:
        config.env === "prod" ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    // ── RDS Proxy — manages connection pooling ─────────────────────────────────

    const proxy = new rds.DatabaseProxy(this, "RdsProxy", {
      proxyTarget: rds.ProxyTarget.fromCluster(cluster),
      secrets: [this.dbSecret],
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSecurityGroup],
      requireTLS: true,
      idleClientTimeout: cdk.Duration.minutes(10),
      maxConnectionsPercent: 90,
    });

    this.proxyEndpoint = proxy.endpoint;

    // ── ElastiCache Redis (cluster mode) ───────────────────────────────────────

    const cacheSubnetGroup = new elasticache.CfnSubnetGroup(this, "CacheSubnetGroup", {
      description: "Travel Agent Redis subnet group",
      subnetIds: vpc.selectSubnets({
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      }).subnetIds,
    });

    const redisAuthToken = new secretsmanager.Secret(this, "RedisAuthToken", {
      secretName: `/travel-agent/${config.env}/redis-auth-token`,
      generateSecretString: {
        excludePunctuation: true,
        passwordLength: 32,
      },
    });

    const redisCluster = new elasticache.CfnReplicationGroup(this, "Redis", {
      replicationGroupDescription: `travel-agent-${config.env}`,
      clusterMode: "enabled",
      numNodeGroups: config.redisNumShards,
      replicasPerNodeGroup: config.redisReplicasPerShard,
      cacheNodeType: config.redisNodeType,
      engine: "redis",
      engineVersion: "7.1",
      cacheSubnetGroupName: cacheSubnetGroup.ref,
      securityGroupIds: [cacheSecurityGroup.securityGroupId],
      atRestEncryptionEnabled: true,
      transitEncryptionEnabled: true,
      transitEncryptionMode: "required",
      authToken: redisAuthToken.secretValueFromJson("password").unsafeUnwrap(),
      automaticFailoverEnabled: config.redisNumShards > 1 || config.redisReplicasPerShard > 0,
      multiAzEnabled: config.maxAzs > 1,
      snapshotRetentionLimit: config.env === "prod" ? 5 : 1,
    });

    this.redisEndpoint = `${redisCluster.attrConfigurationEndPointAddress}:${redisCluster.attrConfigurationEndPointPort}`;
    this.redisAuthSecret = redisAuthToken;

    // ── Outputs ────────────────────────────────────────────────────────────────

    new cdk.CfnOutput(this, "DbProxyEndpoint", { value: proxy.endpoint });
    new cdk.CfnOutput(this, "RedisEndpoint", { value: this.redisEndpoint });
    new cdk.CfnOutput(this, "DbSecretArn", { value: this.dbSecret.secretArn });
  }
}
