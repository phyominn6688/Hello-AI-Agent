import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as sns from "aws-cdk-lib/aws-sns";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
  vpc: ec2.Vpc;
  workerSecurityGroup: ec2.SecurityGroup;
  dbSecret: secretsmanager.Secret;
  dbProxyEndpoint: string;
  redisEndpoint: string;
}

export class AsyncStack extends cdk.Stack {
  readonly mainQueue: sqs.Queue;
  readonly notificationTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const { config, vpc, workerSecurityGroup, dbSecret, dbProxyEndpoint, redisEndpoint } = props;

    // ── SQS Queues ─────────────────────────────────────────────────────────────

    const dlq = new sqs.Queue(this, "DeadLetterQueue", {
      queueName: `travel-agent-${config.env}-dlq`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    this.mainQueue = new sqs.Queue(this, "MainQueue", {
      queueName: `travel-agent-${config.env}`,
      visibilityTimeout: cdk.Duration.seconds(300),
      retentionPeriod: cdk.Duration.days(4),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });

    const notificationQueue = new sqs.Queue(this, "NotificationQueue", {
      queueName: `travel-agent-${config.env}-notifications`,
      visibilityTimeout: cdk.Duration.seconds(60),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
      deadLetterQueue: { queue: dlq, maxReceiveCount: 3 },
    });

    // ── SNS Push Notifications ─────────────────────────────────────────────────

    this.notificationTopic = new sns.Topic(this, "PushNotifications", {
      topicName: `travel-agent-${config.env}-push`,
      displayName: "Travel Agent Push Notifications",
    });
    // Subscribe notification queue to topic for async processing
    this.notificationTopic.addSubscription(
      new cdk.aws_sns_subscriptions.SqsSubscription(notificationQueue)
    );

    // ── ECS Worker cluster (shared with compute stack) ─────────────────────────

    const cluster = new ecs.Cluster(this, "WorkerCluster", {
      vpc,
      clusterName: `travel-agent-workers-${config.env}`,
      containerInsights: true,
    });

    const workerRepo = ecr.Repository.fromRepositoryName(
      this, "WorkerRepo", "travel-agent-backend"
    );

    const workerRole = new iam.Role(this, "WorkerRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      inlinePolicies: {
        WorkerPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes",
                "sqs:ChangeMessageVisibility", "sqs:SendMessage",
              ],
              resources: [this.mainQueue.queueArn, notificationQueue.queueArn],
            }),
            new iam.PolicyStatement({
              actions: ["secretsmanager:GetSecretValue"],
              resources: [dbSecret.secretArn],
            }),
            new iam.PolicyStatement({
              actions: ["sns:Publish"],
              resources: [this.notificationTopic.topicArn],
            }),
            new iam.PolicyStatement({
              actions: ["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    const logGroup = new logs.LogGroup(this, "WorkerLogs", {
      logGroupName: `/ecs/travel-agent-${config.env}/workers`,
      retention: config.env === "prod" ? logs.RetentionDays.ONE_MONTH : logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── Flight monitor worker ──────────────────────────────────────────────────

    const flightMonitorTask = new ecs.FargateTaskDefinition(this, "FlightMonitorTask", {
      cpu: config.workerCpu,
      memoryLimitMiB: config.workerMemory,
      taskRole: workerRole,
    });

    flightMonitorTask.addContainer("FlightMonitor", {
      image: ecs.ContainerImage.fromEcrRepository(workerRepo, config.workerImageTag),
      command: ["python", "-m", "app.workers.flight_monitor"],
      environment: {
        QUEUE_URL: this.mainQueue.queueUrl,
        REDIS_URL: `rediss://${redisEndpoint}`,
      },
      secrets: {
        DATABASE_URL: ecs.Secret.fromSecretsManager(dbSecret, "connectionString"),
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "flight-monitor", logGroup }),
    });

    new ecs.FargateService(this, "FlightMonitorService", {
      cluster,
      taskDefinition: flightMonitorTask,
      desiredCount: config.workerDesiredCount,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [workerSecurityGroup],
      assignPublicIp: false,
    });

    // ── Notifier worker ────────────────────────────────────────────────────────

    const notifierTask = new ecs.FargateTaskDefinition(this, "NotifierTask", {
      cpu: config.workerCpu,
      memoryLimitMiB: config.workerMemory,
      taskRole: workerRole,
    });

    notifierTask.addContainer("Notifier", {
      image: ecs.ContainerImage.fromEcrRepository(workerRepo, config.workerImageTag),
      command: ["python", "-m", "app.workers.notifier"],
      environment: {
        QUEUE_URL: notificationQueue.queueUrl,
        SNS_TOPIC_ARN: this.notificationTopic.topicArn,
      },
      secrets: {
        DATABASE_URL: ecs.Secret.fromSecretsManager(dbSecret, "connectionString"),
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "notifier", logGroup }),
    });

    new ecs.FargateService(this, "NotifierService", {
      cluster,
      taskDefinition: notifierTask,
      desiredCount: config.workerDesiredCount,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [workerSecurityGroup],
      assignPublicIp: false,
    });

    // ── Outputs ────────────────────────────────────────────────────────────────

    new cdk.CfnOutput(this, "MainQueueUrl", { value: this.mainQueue.queueUrl });
    new cdk.CfnOutput(this, "NotificationTopicArn", {
      value: this.notificationTopic.topicArn,
    });
  }
}
