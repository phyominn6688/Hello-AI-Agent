import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import { Construct } from "constructs";
import type { EnvConfig } from "../config/types";

interface Props extends cdk.StackProps {
  config: EnvConfig;
}

export class AuthStack extends cdk.Stack {
  readonly userPool: cognito.UserPool;
  readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const { config } = props;

    // Cognito User Pool
    this.userPool = new cognito.UserPool(this, "UserPool", {
      userPoolName: `travel-agent-${config.env}`,
      selfSignUpEnabled: false, // Social sign-in only
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
        fullname: { required: false, mutable: true },
        profilePicture: { required: false, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy:
        config.env === "prod" ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
    });

    // Google identity provider (Facebook + Amazon follow same pattern — add in Iteration 3)
    const googleProvider = new cognito.UserPoolIdentityProviderGoogle(this, "Google", {
      userPool: this.userPool,
      clientId: cdk.SecretValue.ssmSecure(`/travel-agent/${config.env}/google-client-id`).unsafeUnwrap(),
      clientSecretValue: cdk.SecretValue.ssmSecure(`/travel-agent/${config.env}/google-client-secret`),
      scopes: ["profile", "email", "openid"],
      attributeMapping: {
        email: cognito.ProviderAttribute.GOOGLE_EMAIL,
        fullname: cognito.ProviderAttribute.GOOGLE_NAME,
        profilePicture: cognito.ProviderAttribute.GOOGLE_PICTURE,
      },
    });

    // User Pool domain for hosted UI
    this.userPool.addDomain("Domain", {
      cognitoDomain: { domainPrefix: `travel-agent-${config.env}` },
    });

    // App client — public client for SPA (PKCE)
    this.userPoolClient = new cognito.UserPoolClient(this, "WebClient", {
      userPool: this.userPool,
      userPoolClientName: `travel-agent-web-${config.env}`,
      generateSecret: false,
      authFlows: {
        userSrp: true,
      },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls:
          config.env === "prod"
            ? [`https://${config.domainName}/auth/callback`]
            : ["http://localhost:3000/auth/callback"],
        logoutUrls:
          config.env === "prod"
            ? [`https://${config.domainName}`]
            : ["http://localhost:3000"],
      },
      supportedIdentityProviders: [
        cognito.UserPoolClientIdentityProvider.GOOGLE,
      ],
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
    });

    this.userPoolClient.node.addDependency(googleProvider);

    // Outputs
    new cdk.CfnOutput(this, "UserPoolId", { value: this.userPool.userPoolId });
    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: this.userPoolClient.userPoolClientId,
    });
    new cdk.CfnOutput(this, "CognitoJwksUrl", {
      value: `https://cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}/.well-known/jwks.json`,
    });
  }
}
