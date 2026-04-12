import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
  albDnsName?: string; // Set after compute stack deploys; omit on first deploy
}

export class StorageStack extends cdk.Stack {
  readonly documentBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const { config } = props;
    const albDnsName = props.albDnsName ?? "api-placeholder.invalid";

    // ── Document / ticket storage ──────────────────────────────────────────────

    this.documentBucket = new s3.Bucket(this, "Documents", {
      bucketName: `travel-agent-docs-${config.env}-${this.account}`,
      versioned: config.env === "prod",
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      lifecycleRules: [
        {
          expiration: cdk.Duration.days(config.env === "prod" ? 365 : 30),
        },
      ],
      removalPolicy:
        config.env === "prod" ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: config.env !== "prod",
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
          allowedOrigins:
            config.env === "prod"
              ? [`https://${config.domainName}`]
              : ["http://localhost:3000"],
          allowedHeaders: ["*"],
          maxAge: 3600,
        },
      ],
    });

    // ── Frontend assets bucket ─────────────────────────────────────────────────

    const frontendBucket = new s3.Bucket(this, "Frontend", {
      bucketName: `travel-agent-frontend-${config.env}-${this.account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ── CloudFront distribution ────────────────────────────────────────────────

    const oac = new cloudfront.S3OriginAccessControl(this, "OAC");

    const distribution = new cloudfront.Distribution(this, "Distribution", {
      comment: `travel-agent-${config.env}`,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(frontendBucket, {
          originAccessControl: oac,
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        compress: true,
      },
      additionalBehaviors: {
        // API requests bypass cache → ALB origin (set endpoint after compute stack)
        "/api/*": {
          origin: new origins.HttpOrigin(albDnsName),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
      errorResponses: [
        // SPA fallback — Next.js handles routing
        {
          httpStatus: 404,
          responsePagePath: "/index.html",
          responseHttpStatus: 200,
          ttl: cdk.Duration.seconds(0),
        },
      ],
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
    });

    new cdk.CfnOutput(this, "CloudFrontDomain", {
      value: distribution.distributionDomainName,
    });
    new cdk.CfnOutput(this, "DocumentBucketName", {
      value: this.documentBucket.bucketName,
    });
  }
}
