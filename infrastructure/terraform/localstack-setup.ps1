# LocalStack Initialization Script for EventPulse
# Creates S3 bucket, SQS queues, and SNS topics via AWS CLI pointed to LocalStack (port 4566)

$Endpoint = "http://localhost:4566"
$Region = "us-east-1"

Write-Host "Initializing EventPulse Cloud Resources on LocalStack ($Endpoint)..." -ForegroundColor Cyan

# 1. S3 Bucket
Write-Host "Creating S3 Bucket: eventpulse-tickets..." -ForegroundColor Yellow
aws --endpoint-url=$Endpoint s3 mb s3://eventpulse-tickets-staging --region $Region

# 2. SQS Dead-Letter Queue
Write-Host "Creating SQS DLQ: eventpulse-reservation-dlq..." -ForegroundColor Yellow
aws --endpoint-url=$Endpoint sqs create-queue --queue-name eventpulse-reservation-dlq --region $Region

# 3. SQS Reservation Command Queue
Write-Host "Creating SQS Command Queue: eventpulse-reservation-commands..." -ForegroundColor Yellow
aws --endpoint-url=$Endpoint sqs create-queue --queue-name eventpulse-reservation-commands --region $Region

# 4. SNS Topic
Write-Host "Creating SNS Topic: eventpulse-ticket-issued-fanout..." -ForegroundColor Yellow
aws --endpoint-url=$Endpoint sns create-topic --name eventpulse-ticket-issued-fanout --region $Region

Write-Host "LocalStack cloud infrastructure setup complete!" -ForegroundColor Green
