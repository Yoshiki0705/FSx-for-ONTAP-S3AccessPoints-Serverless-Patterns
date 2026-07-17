# FSx for ONTAP File Portal — Amplify Gen2
# Development & deployment workflow commands
#
# Quick start:
#   make install
#   cp amplify/portal-config.example.ts amplify/portal-config.ts
#   make sandbox
#   make dev

.PHONY: install dev sandbox sandbox-delete sandbox-status build test lint clean \
        sfn-test-create sfn-test-delete cleanup-all help

# Configuration
REGION ?= ap-northeast-1
SFN_TEST_NAME ?= amplify-portal-test-workflow
SFN_TEST_ROLE ?= amplify-portal-sfn-test-role
S3_TEST_BUCKET ?= fsxn-audit-logs-observability-test

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ──────────────────────────────────────────────────────────────────

install: ## Install npm dependencies
	npm install

# ─── Development ────────────────────────────────────────────────────────────

dev: ## Start Vite dev server (frontend only, no backend)
	npm run dev

sandbox: ## Deploy/update Amplify backend (personal sandbox, ~30s incremental)
	npx ampx sandbox --once

sandbox-watch: ## Start Amplify sandbox in watch mode (auto-redeploy on file changes)
	npx ampx sandbox

sandbox-delete: ## Delete all Amplify sandbox resources (Cognito, AppSync, Lambda)
	npx ampx sandbox delete

sandbox-status: ## Show CloudFormation stack status for current sandbox
	@STACK=$$(aws cloudformation list-stacks --region $(REGION) \
		--query "StackSummaries[?contains(StackName,'amplify-fsxns3ap') && StackStatus!='DELETE_COMPLETE'].{Name:StackName,Status:StackStatus}" \
		--output table 2>/dev/null); \
	if [ -z "$$STACK" ]; then echo "No sandbox stack found"; else echo "$$STACK"; fi

# ─── Build & Deploy ─────────────────────────────────────────────────────────

build: ## Build production frontend (outputs to dist/)
	npm run build

# ─── Testing ────────────────────────────────────────────────────────────────

test: ## Run frontend tests (vitest, single run)
	npx vitest run

test-watch: ## Run frontend tests in watch mode
	npx vitest

# ─── Quality ────────────────────────────────────────────────────────────────

lint: ## Run ESLint on all source files
	npx eslint .

typecheck: ## Run TypeScript type checking (no emit)
	npx tsc --noEmit

# ─── Step Functions Test Workflow ────────────────────────────────────────────

sfn-test-create: ## Create a test Step Functions state machine (5s wait → result)
	@echo "Creating IAM role for Step Functions..."
	@aws iam create-role \
		--role-name $(SFN_TEST_ROLE) \
		--assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"states.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
		--region $(REGION) --output text --query "Role.Arn" 2>/dev/null || \
		aws iam get-role --role-name $(SFN_TEST_ROLE) --query "Role.Arn" --output text
	@echo "Waiting for IAM role propagation (10s)..."
	@sleep 10
	@echo "Creating state machine..."
	@ARN=$$(aws stepfunctions create-state-machine \
		--name $(SFN_TEST_NAME) \
		--role-arn $$(aws iam get-role --role-name $(SFN_TEST_ROLE) --query "Role.Arn" --output text) \
		--definition '{"Comment":"Test workflow for Amplify portal (5s wait + result)","StartAt":"ProcessFiles","States":{"ProcessFiles":{"Type":"Wait","Seconds":5,"Next":"Result"},"Result":{"Type":"Pass","Result":{"status":"completed","filesProcessed":3,"dataClassification":"INTERNAL","pattern":"UC1_LEGAL_COMPLIANCE","outputPrefix":"documents/results/"},"End":true}}}' \
		--region $(REGION) \
		--query "stateMachineArn" --output text 2>&1); \
	echo ""; \
	echo "✅ State machine created:"; \
	echo "   $$ARN"; \
	echo ""; \
	echo "📋 Next steps:"; \
	echo "   1. Set stateMachineArn in amplify/portal-config.ts:"; \
	echo "      stateMachineArn: \"$$ARN\""; \
	echo "   2. Update amplify/data/resolvers/start-processing.js:"; \
	echo "      const stateMachineArn = \"$$ARN\";"; \
	echo "   3. Redeploy: make sandbox"

sfn-test-delete: ## Delete the test Step Functions state machine + IAM role
	@echo "Deleting state machine..."
	@aws stepfunctions delete-state-machine \
		--state-machine-arn "arn:aws:states:$(REGION):$$(aws sts get-caller-identity --query Account --output text):stateMachine:$(SFN_TEST_NAME)" \
		--region $(REGION) 2>/dev/null || echo "(already deleted)"
	@echo "Deleting IAM role..."
	@aws iam delete-role --role-name $(SFN_TEST_ROLE) 2>/dev/null || echo "(already deleted)"
	@echo "✅ Test resources deleted"

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts, node_modules, and .amplify cache
	rm -rf dist node_modules .amplify

cleanup-all: sandbox-delete sfn-test-delete ## Full cleanup: sandbox + test SFn + IAM role
	@echo "Removing test S3 data..."
	@aws s3 rm "s3://$(S3_TEST_BUCKET)/" --recursive --region $(REGION) 2>/dev/null || true
	@echo "✅ All test resources cleaned up"

# ─── Amplify-specific ───────────────────────────────────────────────────────

amplify-outputs: ## Generate amplify_outputs.json without full sandbox deploy
	npx ampx generate outputs

amplify-forms: ## Generate form components from data schema
	npx ampx generate forms
