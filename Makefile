.PHONY: help test run-local docker-up docker-down k8s-deploy terraform-init terraform-apply load-test

help:
	@echo "EventPulse Makefile Targets:"
	@echo "  run-local        - Runs unified gateway & dashboard locally on port 8000"
	@echo "  test             - Executes automated pytest verification suite"
	@echo "  docker-up        - Launches all microservices via Docker Compose"
	@echo "  docker-down      - Stops all containers and cleans resources"
	@echo "  k8s-deploy       - Applies Kubernetes staging manifests using Kustomize"
	@echo "  terraform-init   - Initializes Terraform IaC for LocalStack emulation"
	@echo "  terraform-apply  - Provisions SQS, SNS, and S3 resources on LocalStack"
	@echo "  load-test        - Simulates high-concurrency flash sale traffic spike"

run-local:
	python start_demo.py

test:
	python -m pytest eventpulse/tests/test_eventpulse.py -v

docker-up:
	docker compose -f umbrella/docker-compose.yml up --build -d

docker-down:
	docker compose -f umbrella/docker-compose.yml down -v

k8s-deploy:
	kubectl apply -k infrastructure/k8s/overlays/staging

terraform-init:
	cd infrastructure/terraform && terraform init

terraform-apply:
	cd infrastructure/terraform && terraform apply -auto-approve

load-test:
	python load_tests/simulate_concurrency.py
