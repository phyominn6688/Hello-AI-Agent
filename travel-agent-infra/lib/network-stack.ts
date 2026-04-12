import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
}

export class NetworkStack extends cdk.Stack {
  readonly vpc: ec2.Vpc;
  readonly appSecurityGroup: ec2.SecurityGroup;
  readonly dbSecurityGroup: ec2.SecurityGroup;
  readonly cacheSecurityGroup: ec2.SecurityGroup;
  readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const { config } = props;

    // VPC with public + private subnets across maxAzs AZs
    this.vpc = new ec2.Vpc(this, "Vpc", {
      ipAddresses: ec2.IpAddresses.cidr(config.vpcCidr),
      maxAzs: config.maxAzs,
      subnetConfiguration: [
        { name: "Public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "Private", subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 24 },
        { name: "Isolated", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
      natGateways: config.env === "prod" ? config.maxAzs : 1, // 1 NAT GW per AZ in prod for HA; 1 in dev to save ~$65/mo
      enableDnsHostnames: true,
      enableDnsSupport: true,
    });

    // ALB security group — accepts HTTP/HTTPS from internet
    this.albSecurityGroup = new ec2.SecurityGroup(this, "AlbSg", {
      vpc: this.vpc,
      description: "ALB — public ingress",
    });
    this.albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80));
    this.albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443));

    // App security group — accepts from ALB only
    this.appSecurityGroup = new ec2.SecurityGroup(this, "AppSg", {
      vpc: this.vpc,
      description: "ECS Fargate tasks",
    });
    this.appSecurityGroup.addIngressRule(this.albSecurityGroup, ec2.Port.tcp(8000));

    // DB security group — accepts from app SG only
    this.dbSecurityGroup = new ec2.SecurityGroup(this, "DbSg", {
      vpc: this.vpc,
      description: "Aurora PostgreSQL",
    });
    this.dbSecurityGroup.addIngressRule(this.appSecurityGroup, ec2.Port.tcp(5432));

    // Cache security group — accepts from app SG only
    this.cacheSecurityGroup = new ec2.SecurityGroup(this, "CacheSg", {
      vpc: this.vpc,
      description: "ElastiCache Redis",
    });
    this.cacheSecurityGroup.addIngressRule(this.appSecurityGroup, ec2.Port.tcp(6379));

    // VPC Flow Logs → CloudWatch
    new ec2.FlowLog(this, "FlowLog", {
      resourceType: ec2.FlowLogResourceType.fromVpc(this.vpc),
      destination: ec2.FlowLogDestination.toCloudWatchLogs(),
    });
  }
}
