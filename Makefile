# FSx for ONTAP S3AP Serverless Patterns — Makefile
#
# Usage:
#   make install    — Install development dependencies
#   make test       — Run all unit tests
#   make lint       — Run linters (ruff + cfn-lint)
#   make test-uc1   — Run UC1 tests only
#   make deploy-uc1 — Deploy UC1 (requires samconfig.toml)
#   make clean      — Remove build artifacts

# Every target is declared, not just the ones that looked like they needed it.
# `security` was omitted and collides with the `security/` directory, so make
# reported "`security' is up to date" and ran bandit zero times. A gate that
# reports success without executing is worse than no gate: `make security` is in
# the pre-commit list and in AGENTS.md, and it had been passing by doing nothing.
# Listing every target closes the class rather than the instance — a future
# target named after any existing path would fail the same silent way.
.PHONY: \
	help install test test-quick test-uc1 test-uc6 test-sap test-fc1 \
	test-content-edge-delivery test-media-ivs-vod-publishing \
	test-genai-kb-selfservice-curation test-ha-lifekeeper lint lint-python lint-python-check \
	lint-python-format format-python lint-cfn drift drift-published security build-uc1 \
	build-sap deploy-uc1 deploy-sap clean build-SharedLayer build-uc12 deploy-uc12 test-ops1 \
	test-ops4 test-ops3 test-ops2 test-ops5 test-ops6 test-ops lint-ops lint-cfn-ops \
	build-ops1 deploy-ops1 security-report

# Target Python version — must match the Lambda runtime in the SAM templates
# (`Runtime: python3.13`). Declared once here so `install`, the interpreter
# fallback, and the venv freshness check cannot drift apart.
PY_VERSION := 3.13

# Python interpreter — auto-detect .venv if available (override with: make test PYTHON=python3.12)
# Priority: 1) explicit override  2) .venv/bin/python  3) system python$(PY_VERSION)
ifeq ($(origin PYTHON), undefined)
  ifneq (,$(wildcard .venv/bin/python))
    PYTHON := .venv/bin/python
  else
    PYTHON := python$(PY_VERSION)
  endif
else
  PYTHON ?= python$(PY_VERSION)
endif

# ruff from the venv, so linting uses the version pinned in requirements-dev.txt
# that CI installs. Falling back to whatever is on PATH is what let a homebrew
# ruff answer for the pipeline's.
ifneq (,$(wildcard .venv/bin/ruff))
  VENV_RUFF := .venv/bin/ruff
else
  VENV_RUFF := ruff
endif

# Same reasoning for bandit, and the same omission had the same effect: the
# `security` recipe called a bare `bandit`, which is not on PATH here, so the
# first run after the target started working at all died with "No such file or
# directory". requirements-dev.txt pins bandit==1.9.4 into .venv; use it.
ifneq (,$(wildcard .venv/bin/bandit))
  VENV_BANDIT := .venv/bin/bandit
else
  VENV_BANDIT := bandit
endif

# Default target
help:
	@echo "Available targets:"
	@echo "  make install       — Create .venv and install all dependencies"
	@echo "  make test          — Run all unit tests"
	@echo "  make test-quick    — Run tests for key patterns only"
	@echo "  make lint          — Run ruff + cfn-lint"
	@echo "  make lint-cfn      — Run cfn-lint only"
	@echo "  make lint-python   — Run ruff only"
	@echo "  make security      — Run bandit security scan"
	@echo "  make clean         — Remove build artifacts"
	@echo ""
	@echo "Python: $(PYTHON) (auto-detects .venv/bin/python; override: PYTHON=...)"
	@echo ""
	@echo "Pattern-specific targets:"
	@echo "  make test-uc1      — Run UC1 (legal-compliance) tests"
	@echo "  make test-uc6      — Run UC6 (semiconductor-eda) tests"
	@echo "  make test-sap      — Run SAP tests"
	@echo "  make test-fc1      — Run FC1 (flexcache-anycast-dr) tests"
	@echo "  make test-ops1     — Run OPS1 (capacity-rightsizing) tests"
	@echo "  make deploy-uc1    — Deploy UC1 (requires samconfig.toml)"
	@echo "  make deploy-ops1   — Deploy OPS1 (requires samconfig.toml)"

# ============================================================
# Setup
# ============================================================
install:
	@echo "🐍 Setting up Python $(PY_VERSION) virtual environment..."
	@command -v python$(PY_VERSION) >/dev/null 2>&1 || { echo "❌ python$(PY_VERSION) not found. Install: brew install python@$(PY_VERSION)"; exit 1; }
	@if [ ! -f .venv/bin/python ] || ! .venv/bin/python --version 2>/dev/null | grep -q "$(PY_VERSION)"; then \
		echo "  Creating .venv (python$(PY_VERSION))..."; \
		python$(PY_VERSION) -m venv .venv --clear; \
	fi
	@echo "  Installing dependencies..."
	.venv/bin/pip install --upgrade pip -q
	.venv/bin/pip install -r requirements.txt -q
# Dev tooling comes from requirements-dev.txt, which CI also installs. Keep it that
# way: this used to be an inline unpinned list, so a local .venv drifted ahead of CI
# (ruff 0.16.1 vs 0.15.17, cfn-lint 1.54.0 vs 1.53.3) and `make lint` could disagree
# with the lint workflow on unchanged code.
	.venv/bin/pip install -r requirements-dev.txt -q
	@echo "✅ Setup complete. Run: make test-quick"

# ============================================================
# Testing
# ============================================================
# パターンのテストディレクトリは pattern-test-dirs.txt を単一の出典とする。
# 以前はこの target と ci.yml がそれぞれ手書きの一覧を持っており、CI は 37 個、
# こちらは 16 個しか回していなかった。両方に載っていないディレクトリが 13 個
# （約 790 テスト）あり、どこでも実行されていなかった。
PATTERN_TEST_DIRS := $(shell grep -v '^\#' pattern-test-dirs.txt | grep -v '^$$')

test:
	$(PYTHON) -m pytest shared/tests/ --tb=short -q
	$(PYTHON) -m pytest scripts/tests/ --tb=short -q
# パターンごとに別プロセスで回す。多くのパターンが functions.discovery のような
# 同名モジュールを持つため、まとめて 1 プロセスで実行すると sys.modules が最初の
# パターンのものを掴んで ModuleNotFoundError になる。
	@for d in $(PATTERN_TEST_DIRS); do \
		echo "--- $$d"; \
		$(PYTHON) -m pytest "$$d/tests/" --tb=short -q --ignore=.hypothesis || exit 1; \
	done

test-quick:
	$(PYTHON) -m pytest shared/tests/test_s3ap_helper.py shared/tests/test_properties.py shared/tests/test_fsx_helper.py --tb=short -q
	$(PYTHON) -m pytest solutions/sap/erp-adjacent/tests/ --tb=short -q
	$(PYTHON) -m pytest solutions/industry/semiconductor-eda/tests/ --tb=short -q

test-uc1:
	$(PYTHON) -m pytest solutions/industry/legal-compliance/tests/ -v

test-uc6:
	$(PYTHON) -m pytest solutions/industry/semiconductor-eda/tests/ -v

test-sap:
	$(PYTHON) -m pytest solutions/sap/erp-adjacent/tests/ -v

test-fc1:
	$(PYTHON) -m pytest solutions/flexcache/anycast-dr/tests/ -v

test-content-edge-delivery:
	$(PYTHON) -m pytest solutions/edge/content-delivery/tests/ -v

test-media-ivs-vod-publishing:
	$(PYTHON) -m pytest solutions/edge/media-ivs-vod-publishing/tests/ -v

test-genai-kb-selfservice-curation:
	$(PYTHON) -m pytest solutions/genai/kb-selfservice-curation/tests/ -v

test-ha-lifekeeper:
	$(PYTHON) -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# ============================================================
# Linting
# ============================================================
lint: lint-python lint-cfn

lint-python: lint-python-check lint-python-format

# Matches `.github/workflows/lint.yaml` exactly: same binary, same paths, one
# invocation. It used to run `ruff check ... --config pyproject.toml 2>/dev/null ||
# ruff check ...`, which always took the fallback — the two ruff configs in the
# repo disagreed, so the first form reported hundreds of findings, its exit code
# was discarded and its output was left on the terminal looking like failure. It
# also scoped the check to three directories while CI checks the whole tree, and
# called whichever ruff was on PATH instead of the pinned one, so a local homebrew
# install could disagree with the pipeline on unchanged code.
lint-python-check:
	$(VENV_RUFF) check .

# CI runs `ruff format --check` as its own step, so `make lint` has to run it
# too. Without this, formatting drift passes locally and only fails in the
# pipeline.
lint-python-format:
	$(VENV_RUFF) format --check .

# Rewrites files in place. Use after lint-python-format reports drift.
format-python:
	$(VENV_RUFF) format .

# Template discovery comes from the `templates:` globs in .cfnlintrc, so this
# target cannot drift out of sync with the patterns that actually exist.
# Informational (I) and warning (W) findings are printed but do not fail the
# build; only errors (E) do.
lint-cfn:
	cfn-lint --non-zero-exit-code error

# ============================================================
# Drift checks
# ============================================================
# Offline. Covers docs/, the portal docs, and drafts/blog when it exists locally.
# The rules' own tests run under `make test` with the rest of scripts/tests; this
# target runs them too so a rule change can be checked without the full suite.
drift:
	$(PYTHON) -m pytest scripts/tests/test_stale_claim_rules.py --tb=short -q
	$(PYTHON) scripts/check_portal_drift.py
# The generic dispatch endpoints take an untyped `params` blob, so nothing checks
# that a component sends what its action requires. A lock button shipped that had
# never worked once: it sent a name and a duration where the action reads a UUID
# and an absolute expiry.
	$(PYTHON) -m pytest scripts/tests/test_portal_action_params.py --tb=short -q
	$(PYTHON) scripts/check_portal_action_params.py
# The parameter check above compares names. It cannot see a name that is right and a
# value that is wrong — a volume name where a UUID belongs spells the key correctly.
# That needs types, and types generated from the handlers need checking against them.
	$(PYTHON) -m pytest scripts/tests/test_portal_action_types.py --tb=short -q
	$(PYTHON) scripts/portal_action_types.py --check
# Translations nobody can reach, and relative links that resolve to nothing. 27 of
# 83 pairs had no language switcher, and 18 links in the portal docs alone were
# dead because ../../docs/ from that directory is solutions/docs/, which does not
# exist. A dead relative link renders as ordinary text until someone clicks it.
	$(PYTHON) scripts/check_doc_pairs.py
# AGENTS.md is loaded on every turn and cannot be made conditional, so it had grown
# to 78 KB carrying pitfall tables that matter only while doing that one kind of
# work. Splitting it into task-triggered steering is undone by one useful paragraph
# at a time unless something objects. This also catches the failure that made the
# split necessary: `inclusion: auto` without `name` and `description` is never
# registered, so the file is never read and nothing says so.
	$(PYTHON) -m pytest scripts/tests/test_agent_context_budget.py --tb=short -q
	$(PYTHON) scripts/check_agent_context_budget.py

# Fetches the published posts from Hatena and dev.to, so it needs network and is
# not part of `make lint`. Run it after shipping a feature that makes an article's
# "you would have to build this yourself" list shorter.
drift-published:
	$(PYTHON) scripts/check_published_articles.py

# ============================================================
# Security
# ============================================================
# Every directory that carries Python, not a subset. `infrastructure/` and
# `scripts/` were outside the old list, and CI's blocking scan covered only
# `shared/` plus three of the twenty-eight industry patterns — its comprehensive
# run ended in `|| true`, so it wrote a JSON artifact and failed nothing. Both SQL
# injection vectors found in this repository sat in that gap. Declared once here so
# the pipeline and a laptop cannot scan different trees.
BANDIT_PATHS := shared/ solutions/ operations/ infrastructure/ scripts/

security:
	$(VENV_BANDIT) -r $(BANDIT_PATHS) -ll -c .bandit

# Same scan, machine-readable, for upload as a CI artifact. Non-blocking on
# purpose: `security` above is the gate, and having two blocking scans of the same
# tree means fixing the same finding twice.
security-report:
	$(VENV_BANDIT) -r $(BANDIT_PATHS) -ll -c .bandit -f json -o bandit-report.json || true

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
	rm -rf .hypothesis/examples/ 2>/dev/null || true
	rm -rf build/ htmlcov/ coverage.xml

# ============================================================
# SAM Layer Build Target (used by sam build --BuildMethod makefile)
# ============================================================
build-SharedLayer:
	mkdir -p "$(ARTIFACTS_DIR)/python/shared"
	# Copy the whole shared/ package so eager imports in shared/__init__.py
	# (streaming, routing, etc.) and any subpackage a handler imports are present
	# in the layer. Prune non-runtime dirs (tests, standalone servers, CFn/lambda
	# sources) and bytecode caches.
	cp -r shared/. "$(ARTIFACTS_DIR)/python/shared/"
	rm -rf "$(ARTIFACTS_DIR)/python/shared/tests" \
	       "$(ARTIFACTS_DIR)/python/shared/fpolicy-server" \
	       "$(ARTIFACTS_DIR)/python/shared/cfn" \
	       "$(ARTIFACTS_DIR)/python/shared/lambdas"
	find "$(ARTIFACTS_DIR)/python/shared" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build & Deploy logistics-ocr (UC12)
build-uc12:
	cd solutions/industry/logistics-ocr && sam build

deploy-uc12:
	cd solutions/industry/logistics-ocr && sam deploy --config-file samconfig.toml

# ============================================================
# Operations Patterns (operations/)
# ============================================================
test-ops1:
	$(PYTHON) -m pytest operations/capacity-rightsizing/tests/ -v

test-ops4:
	$(PYTHON) -m pytest operations/snapshot-lifecycle/tests/ -v

test-ops3:
	$(PYTHON) -m pytest operations/tiering-optimizer/tests/ -v

test-ops2:
	$(PYTHON) -m pytest operations/storage-efficiency/tests/ -v

test-ops5:
	$(PYTHON) -m pytest operations/cost-optimization/tests/ -v

test-ops6:
	$(PYTHON) -m pytest operations/qos-monitoring/tests/ -v

test-ops:
	$(PYTHON) -m pytest operations/ --tb=short -q

lint-ops:
	ruff check operations/ shared/ontap_metrics.py shared/demo_data_loader.py shared/schemas/ops_events.py \
		--config pyproject.toml 2>/dev/null || \
	ruff check operations/ shared/ontap_metrics.py shared/demo_data_loader.py shared/schemas/ops_events.py

lint-cfn-ops:
	cfn-lint operations/capacity-rightsizing/template.yaml \
		operations/snapshot-lifecycle/template.yaml \
		operations/tiering-optimizer/template.yaml \
		operations/storage-efficiency/template.yaml \
		operations/cost-optimization/template.yaml \
		operations/qos-monitoring/template.yaml

build-ops1:
	cd operations/capacity-rightsizing && sam build

deploy-ops1:
	cd operations/capacity-rightsizing && sam deploy --config-file samconfig.toml
