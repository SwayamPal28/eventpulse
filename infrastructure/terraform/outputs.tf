output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.ticket_storage.arn
}

output "reservation_queue_url" {
  description = "URL of the SQS reservation command queue"
  value       = aws_sqs_queue.reservation_queue.id
}

output "reservation_dlq_url" {
  description = "URL of the Dead-Letter Queue"
  value       = aws_sqs_queue.reservation_dlq.id
}

output "ticket_sns_topic_arn" {
  description = "ARN of the Ticket Issued SNS fan-out topic"
  value       = aws_sns_topic.ticket_issued_topic.arn
}
