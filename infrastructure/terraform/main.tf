terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Route AWS calls to LocalStack
  endpoints {
    s3  = var.localstack_endpoint
    sqs = var.localstack_endpoint
    sns = var.localstack_endpoint
  }
}

# 1. AWS S3 Bucket for Digital QR Tickets & Badges
resource "aws_s3_bucket" "ticket_storage" {
  bucket = var.s3_bucket_name

  tags = {
    Environment = var.environment
    Project     = "EventPulse"
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket_versioning" "ticket_versioning" {
  bucket = aws_s3_bucket.ticket_storage.id
  versioning_configuration {
    status = "Enabled"
  }
}

# 2. Dead Letter Queue (DLQ) for Failed Reservations
resource "aws_sqs_queue" "reservation_dlq" {
  name                      = "eventpulse-reservation-dlq"
  message_retention_seconds = 1209600 # 14 days
}

# 3. AWS SQS Reservation Command Queue
resource "aws_sqs_queue" "reservation_queue" {
  name                       = "eventpulse-reservation-commands"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.reservation_dlq.arn
    maxReceiveCount     = 3
  })
}

# 4. AWS SNS Topic for Ticket Issuance Fan-Out
resource "aws_sns_topic" "ticket_issued_topic" {
  name = "eventpulse-ticket-issued-fanout"
}

# 5. SQS Subscription to SNS Topic for Notification Worker
resource "aws_sqs_queue" "notification_queue" {
  name = "eventpulse-notification-worker-queue"
}

resource "aws_sns_topic_subscription" "notification_sub" {
  topic_arn = aws_sns_topic.ticket_issued_topic.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notification_queue.arn
}
