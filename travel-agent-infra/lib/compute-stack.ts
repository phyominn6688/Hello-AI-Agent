import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
  vpc: ec2.Vpc;
  appSecurityGroup: ec2.SecurityGroup;
  dbSecret: secretsmanager.Secret;
  dbProxyEndpoint: string;
  redisEndpoint: string;
  documentBucket: s3.Bucket;
  userPoolId: string;
  userPoolClientId: string;
}

export class ComputeStack extends cdk.Stack {
  readonly alb: elbv2.ApplicationLoadBalancer;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const {
      config, vpc, appSecurityGroup, dbSecret,
      dbProxyEndpoint, redisEndpoint, documentBucket,
      userPoolId, userPoolClientId,
    } = props;

    // ── ECR Repositories ───────────────────────────────────────────────────────

    const backendRepo = ecr.Repository.fromRepositoryName(
      this, "BackendRepo", "travel-agent-backend"
    );

    // ── ECS Cluster ────────────────────────────────────────────────────────────

    const cluster = new ecs.Cluster(this, "Cluster", {
      vpc,
      clusterName: `travel-agent-${config.env}`,
      containerInsights: true,
    });

    // ── Task execution role ────────────────────────────────────────────────────

    const taskRole = new iam.Role(this, "TaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      inlinePolicies: {
        AppPolicy: new iam.PolicyDocument({
          statements: [
            // S3 access for documents
            new iam.PolicyStatement({
              actions: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
              resources: [documentBucket.arnForObjects("*")],
            }),
            // Secrets Manager — read DB credentials
            new iam.PolicyStatement({
              actions: ["secretsmanager:GetSecretValue"],
              resources: [dbSecret.secretArn],
            }),
            // SQS — send messages for async jobs
            new iam.PolicyStatement({
              actions: ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage"],
              resources: [`arn:aws:sqs:${this.region}:${this.account}:travel-agent-*`],
            }),
            // SNS — publish push notifications
            new iam.PolicyStatement({
              actions: ["sns:Publish"],
              resources: [`arn:aws:sns:${this.region}:${this.account}:travel-agent-*`],
            }),
            // X-Ray tracing
            new iam.PolicyStatement({
              actions: ["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // ── CloudWatch log group ───────────────────────────────────────────────────

    const logGroup = new logs.LogGroup(this, "BackendLogs", {
      logGroupName: `/ecs/travel-agent-${config.env}/backend`,
      retention: config.env === "prod" ? logs.RetentionDays.ONE_MONTH : logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Task definition ────────────────────────────────────────────────────────

    const taskDef = new ecs.FargateTaskDefinition(this, "BackendTask", {
      cpu: config.backendCpu,
      memoryLimitMiB: config.backendMemory,
      taskRole,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });

    taskDef.addContainer("Backend", {
      image: ecs.ContainerImage.fromEcrRepository(backendRepo, config.backendImageTag),
      portMappings: [{ containerPort: 8000 }],
      environment: {
        REDIS_URL: `rediss://${redisEndpoint}`,
        STORAGE_BUCKET: documentBucket.bucketName,
        AUTH_JWKS_URL: `https://cognito-idp.${this.region}.amazonaws.com/${userPoolId}/.well-known/jwks.json`,
        AUTH_AUDIENCE: userPoolClientId,
        QUEUE_URL: `https://sqs.${this.region}.amazonaws.com/${this.account}/travel-agent-${config.env}`,
        CORS_ORIGINS: `["https://${config.domainName || 'localhost:3000'}"]`,
      },
      secrets: {
        DATABASE_URL: ecs.Secret.fromSecretsManager(dbSecret, "connectionString"),
        ANTHROPIC_API_KEY: ecs.Secret.fromSsmParameter(
          cdk.aws_ssm.StringParameter.fromSecureStringParameterAttributes(
            this, "AnthropicKey", { parameterName: `/travel-agent/${config.env}/anthropic-api-key`, version: 1 }
          )
        ),
      },
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: "backend",
        logGroup,
      }),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(10),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    // ── ALB ────────────────────────────────────────────────────────────────────

    this.alb = new elbv2.ApplicationLoadBalancer(this, "Alb", {
      vpc,
      internetFacing: true,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    });

    const listener = this.alb.addListener("HttpsListener", {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      // Certificate added in prod; dev uses HTTP
      open: true,
    });

    // ── ECS Service ────────────────────────────────────────────────────────────

    const service = new ecs.FargateService(this, "BackendService", {
      cluster,
      taskDefinition: taskDef,
      desiredCount: config.backendDesiredCount,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [appSecurityGroup],
      assignPublicIp: false,
      enableECSManagedTags: true,
      propagateTags: ecs.PropagatedTagSource.SERVICE,
      circuitBreaker: { enable: true, rollback: true },
      deploymentController: { type: ecs.DeploymentControllerType.ECS },
    });

    listener.addTargets("BackendTargets", {
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [service],
      healthCheck: {
        path: "/health",
        interval: cdk.Duration.seconds(30),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    // ── Auto-scaling ───────────────────────────────────────────────────────────

    const scaling = service.autoScaleTaskCount({
      minCapacity: config.backendDesiredCount,
      maxCapacity: config.env === "prod" ? 20 : 4,
    });

    scaling.scaleOnCpuUtilization("CpuScaling", {
      targetUtilizationPercent: 60,
      scaleInCooldown: cdk.Duration.seconds(60),
      scaleOutCooldown: cdk.Duration.seconds(30),
    });

    scaling.scaleOnRequestCount("RequestScaling", {
      requestsPerTarget: 500,
      targetGroup: listener.addTargets("ScalingTarget", {
        port: 8000,
        targets: [],
      }) as elbv2.ApplicationTargetGroup,
    });

    // ── Outputs ────────────────────────────────────────────────────────────────

    new cdk.CfnOutput(this, "AlbDnsName", { value: this.alb.loadBalancerDnsName });
    new cdk.CfnOutput(this, "ClusterName", { value: cluster.clusterName });
  }
}
