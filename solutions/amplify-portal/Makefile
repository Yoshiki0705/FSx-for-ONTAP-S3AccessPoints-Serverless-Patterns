# FSx for ONTAP File Portal — Amplify Gen2
# Development workflow commands

.PHONY: install dev sandbox sandbox-delete build test lint clean help

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup ---

install: ## Install dependencies (npm)
	npm install

# --- Development ---

dev: ## Start Vite dev server (frontend only, no backend)
	npm run dev

sandbox: ## Start Amplify sandbox (deploys backend to personal AWS env)
	npx ampx sandbox

sandbox-delete: ## Delete Amplify sandbox resources
	npx ampx sandbox delete

# --- Build & Deploy ---

build: ## Build production frontend
	npm run build

# --- Testing ---

test: ## Run frontend tests (vitest, single run)
	npx vitest run

test-watch: ## Run frontend tests in watch mode
	npx vitest

# --- Quality ---

lint: ## Run ESLint on all source files
	npx eslint .

typecheck: ## Run TypeScript type checking
	npx tsc --noEmit

# --- Cleanup ---

clean: ## Remove build artifacts and node_modules
	rm -rf dist node_modules .amplify

# --- Amplify-specific ---

amplify-outputs: ## Generate amplify_outputs.json without full sandbox
	npx ampx generate outputs

amplify-forms: ## Generate form components from data schema
	npx ampx generate forms
