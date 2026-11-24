variable "aws_region" {
  description = "AWS region for infrastructure provisioning"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Target deployment environment"
  type        = string
  default     = "staging"
}

variable "localstack_endpoint" {
  description = "LocalStack endpoint URL for local emulation"
  type        = string
  default     = "http://localhost:4566"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for digital QR tickets"
  type        = string
  default     = "eventpulse-tickets-staging"
}
