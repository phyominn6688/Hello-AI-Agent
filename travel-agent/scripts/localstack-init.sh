#!/bin/bash
# Initializes LocalStack resources on startup
set -e

echo "==> Initializing LocalStack resources..."

# Create S3 bucket for documents
aws --endpoint-url=http://localhost:4566 s3 mb s3://travel-agent-local --region us-east-1 2>/dev/null || true
aws --endpoint-url=http://localhost:4566 s3api put-bucket-cors \
  --bucket travel-agent-local \
  --cors-configuration '{"CORSRules":[{"AllowedHeaders":["*"],"AllowedMethods":["GET","PUT","POST"],"AllowedOrigins":["http://localhost:3000"],"MaxAgeSeconds":3600}]}' \
  2>/dev/null || true

# Create SQS queues
aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name travel-agent \
  --region us-east-1 \
  2>/dev/null || true

aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name travel-agent-notifications \
  --region us-east-1 \
  2>/dev/null || true

aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name travel-agent-dlq \
  --region us-east-1 \
  2>/dev/null || true

# Create SNS topic
aws --endpoint-url=http://localhost:4566 sns create-topic \
  --name travel-agent-push \
  --region us-east-1 \
  2>/dev/null || true

echo "==> LocalStack initialization complete"
