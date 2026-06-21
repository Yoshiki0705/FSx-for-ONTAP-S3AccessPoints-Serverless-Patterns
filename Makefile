# FSx ONTAP S3AP Serverless Patterns — Makefile
#
# Usage:
#   make install    — Install development dependencies
#   make test       — Run all unit tests
#   make lint       — Run linters (ruff + cfn-lint)
#   make test-uc1   — Run UC1 tests only
#   make deploy-uc1 — Deploy UC1 (requires samconfig.toml)
#   make clean      — Remove build artifacts

.PHONY: install test lint clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  make install       — Install development dependencies"
	@echo "  make test          — Run all unit tests"
	@echo "  make test-quick    — Run tests for key patterns only"
	@echo "  make lint          — Run ruff + cfn-lint"
	@echo "  make lint-cfn      — Run cfn-lint only"
	@echo "  make lint-python   — Run ruff only"
	@echo "  make security      — Run bandit security scan"
	@echo "  make clean         — Remove build artifacts"
	@echo ""
	@echo "Pattern-specific targets:"
	@echo "  make test-uc1      — Run UC1 (legal-compliance) tests"
	@echo "  make test-uc6      — Run UC6 (semiconductor-eda) tests"
	@echo "  make test-sap      — Run SAP tests"
	@echo "  make test-fc1      — Run FC1 (flexcache-anycast-dr) tests"
	@echo "  make deploy-uc1    — Deploy UC1 (requires samconfig.toml)"
	@echo "  make build-uc1     — Build UC1"

# ============================================================
# Setup
# ============================================================
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# ============================================================
# Testing
# ============================================================
test:
	python3 -m pytest \
		shared/tests/ \
		solutions/industry/legal-compliance/tests/ \
		solutions/industry/semiconductor-eda/tests/ \
		solutions/sap/erp-adjacent/tests/ \
		solutions/industry/smart-city-geospatial/tests/ \
		solutions/industry/defense-satellite/tests/ \
		solutions/industry/education-research/tests/ \
		--tb=short -q
	python3 -m pytest \
		solutions/flexcache/anycast-dr/tests/ \
		--tb=short -q
	python3 -m pytest \
		solutions/ha/lifekeeper-monitoring/tests/ \
		--tb=short -q

test-quick:
	python3 -m pytest \
		shared/tests/ \
		solutions/sap/erp-adjacent/tests/ \
		solutions/industry/semiconductor-eda/tests/ \
		--tb=short -q

test-uc1:
	python3 -m pytest solutions/industry/legal-compliance/tests/ -v

test-uc6:
	python3 -m pytest solutions/industry/semiconductor-eda/tests/ -v

test-sap:
	python3 -m pytest solutions/sap/erp-adjacent/tests/ -v

test-fc1:
	python3 -m pytest solutions/flexcache/anycast-dr/tests/ -v

test-content-edge-delivery:
	python3 -m pytest solutions/edge/content-delivery/tests/ -v

test-ha-lifekeeper:
	python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# ============================================================
# Linting
# ============================================================
lint: lint-python lint-cfn

lint-python:
	ruff check shared/ solutions/ \
		--config pyproject.toml 2>/dev/null || \
	ruff check shared/ solutions/

lint-cfn:
	cfn-lint solutions/industry/legal-compliance/template.yaml \
		solutions/industry/semiconductor-eda/template.yaml \
		solutions/sap/erp-adjacent/template.yaml \
		solutions/flexcache/anycast-dr/template.yaml \
		solutions/edge/content-delivery/template.yaml \
		solutions/ha/lifekeeper-monitoring/template.yaml

# ============================================================
# Security
# ============================================================
security:
	bandit -r shared/ solutions/ \
		-ll -c .bandit

# ============================================================
# Build & Deploy (SAM)
# ============================================================
build-uc1:
	cd solutions/industry/legal-compliance && sam build

build-sap:
	cd solutions/sap/erp-adjacent && sam build

deploy-uc1:
	cd solutions/industry/legal-compliance && sam deploy --config-file samconfig.toml

deploy-sap:
	cd solutions/sap/erp-adjacent && sam deploy --config-file samconfig.toml

# ============================================================
# Clean
# ============================================================
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".aws-sam" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf build/ htmlcov/ coverage.xml
