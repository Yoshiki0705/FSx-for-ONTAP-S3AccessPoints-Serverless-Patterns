# Nextcloud External Storage — S3 AP Verification
#
# Quick start:
#   make up
#   export S3_BUCKET=my-bucket-or-ap-alias
#   make configure-s3
#   make verify
#   open http://localhost:8080

.PHONY: up down clean configure-s3 verify list-files help

# ─── Configuration ──────────────────────────────────────────────────────────
S3_BUCKET    ?=
S3_REGION    ?= ap-northeast-1
S3_HOSTNAME  ?= s3.$(S3_REGION).amazonaws.com
MOUNT_NAME   ?= FSxONTAP-Data
NC_CONTAINER ?= nextcloud-s3ap-test
NC_USER      ?= admin
NC_PASS      ?= admin123

# ─── Targets ────────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start Nextcloud + DB containers and enable External Storage app
	docker compose up -d
	@echo "Waiting for Nextcloud to initialize (20s)..."
	@sleep 20
	docker exec -u 33 $(NC_CONTAINER) php occ app:enable files_external
	@echo ""
	@echo "✅ Nextcloud running at http://localhost:8080"
	@echo "   Login: $(NC_USER) / $(NC_PASS)"
	@echo ""
	@echo "Next: export S3_BUCKET=<your-bucket-or-ap-alias> && make configure-s3"

configure-s3: ## Configure External Storage with S3 bucket/AP alias (requires S3_BUCKET)
	@if [ -z "$(S3_BUCKET)" ]; then \
		echo "❌ Error: S3_BUCKET is not set"; \
		echo "   Usage: export S3_BUCKET=my-bucket-or-ap-alias && make configure-s3"; \
		exit 1; \
	fi
	@echo "Creating External Storage mount '$(MOUNT_NAME)'..."
	@MOUNT_ID=$$(docker exec -u 33 $(NC_CONTAINER) php occ files_external:create \
		$(MOUNT_NAME) amazons3 amazons3::accesskey 2>&1 | grep -o '[0-9]*'); \
	if [ -z "$$MOUNT_ID" ]; then \
		echo "❌ Failed to create mount (may already exist)"; \
		echo "   Run: make clean && make up && make configure-s3"; \
		exit 1; \
	fi; \
	echo "Mount ID: $$MOUNT_ID"; \
	echo "Configuring parameters..."; \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID bucket $(S3_BUCKET); \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID hostname $(S3_HOSTNAME); \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID region $(S3_REGION); \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID use_ssl true; \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID use_path_style true; \
	KEY=$$(aws configure get aws_access_key_id); \
	SECRET=$$(aws configure get aws_secret_access_key); \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID key "$$KEY"; \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:config $$MOUNT_ID secret "$$SECRET"; \
	echo ""; \
	echo "✅ External Storage configured:"; \
	echo "   Mount: /$(MOUNT_NAME)"; \
	echo "   Bucket/AP: $(S3_BUCKET)"; \
	echo "   Region: $(S3_REGION)"; \
	echo "   Path Style: enabled"; \
	echo ""; \
	echo "Next: make verify"

verify: ## Verify External Storage connection (should show 'status: ok')
	@MOUNT_ID=$$(docker exec -u 33 $(NC_CONTAINER) php occ files_external:list --output=json 2>/dev/null \
		| grep -o '"mount_id":[0-9]*' | head -1 | grep -o '[0-9]*'); \
	if [ -z "$$MOUNT_ID" ]; then \
		echo "❌ No External Storage configured. Run: make configure-s3"; \
		exit 1; \
	fi; \
	echo "Verifying mount ID $$MOUNT_ID..."; \
	docker exec -u 33 $(NC_CONTAINER) php occ files_external:verify $$MOUNT_ID

list-files: ## List files via WebDAV API (shows S3 contents through Nextcloud)
	@echo "Files in /$(MOUNT_NAME):"
	@curl -s -u $(NC_USER):$(NC_PASS) \
		"http://localhost:8080/remote.php/dav/files/$(NC_USER)/$(MOUNT_NAME)/" \
		-X PROPFIND -H "Depth: 1" 2>&1 \
		| grep -o '<d:href>[^<]*</d:href>' \
		| sed 's|<d:href>/remote.php/dav/files/$(NC_USER)/$(MOUNT_NAME)/||;s|</d:href>||' \
		| tail -n +2
	@echo ""

down: ## Stop containers (volumes preserved for next startup)
	docker compose down

clean: ## Full reset — stop containers AND delete volumes
	docker compose down -v
	@echo "✅ All containers and volumes removed"
