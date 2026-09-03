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
	build-ops1 deploy-ops1 security-report security-cfn propose-cleanup ontap-preflight \
	discover-s3ap check-group-ap-tags portal-preflight portal-grant-roles \
	portal-demo-user portal-hosting portal-hosting-url \
	portal-basic-auth portal-basic-auth-off

# Target Python version — must match the Lambda runtime in the SAM templates
# (`Runtime: python3.13`). Declared once here so `install`, the interpreter
# fallback, and the venv freshness check cannot drift apart.
# `scripts/check_lambda_runtime_agrees.py` enforces the "must match" against all
# 350 declaration sites. Until it existed this comment was the only thing asking.
# Deprecation of python3.13 is projected for 2029-06-30. python3.14 carries the
# same date, so a bump buys no support runway — check the current table before
# treating either as a deadline.
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

# And cfn-lint, which was the one left calling whatever PATH offered. On this
# machine that is homebrew's 1.52.1 while requirements-dev.txt pins 1.53.3, so
# `make lint-cfn` was validating templates with a different rule set than the
# lint workflow and reporting success either way. A version that disagrees with
# CI is the case this indirection exists for; leaving one tool out of it meant
# the whole convention only appeared to hold.
ifneq (,$(wildcard .venv/bin/cfn-lint))
  VENV_CFN_LINT := .venv/bin/cfn-lint
else
  VENV_CFN_LINT := cfn-lint
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
	@echo "  make drift         — Docs/code drift, i18n coverage, portal action contracts (offline)"
	@echo "  make ontap-preflight — Name the broken link in the portal's ONTAP chain (calls AWS)"
	@echo "  make propose-cleanup — Report the backlog, then what is standing and its cost (read-only)"
	@echo "  make discover-s3ap — Inventory S3 access points from the FSx API (read-only)"
	@echo "  make check-group-ap-tags — Report groupApMapping vs access point tags (read-only)"
	@echo "  make portal-preflight — Check a deployed sandbox against outputs and config (read-only)"
	@echo "  make portal-grant-roles — Grant portal roles/scopes to Cognito users (dry run unless ARGS=--apply)"
	@echo "  make portal-demo-user — Create a demo account and grant it a role and scope (calls AWS)"
	@echo "  make portal-hosting  — Publish the frontend to Amplify Hosting for an https URL (calls AWS)"
	@echo "  make portal-hosting-url — Report the hosted URL, its backend binding and its gates"
	@echo "  make portal-basic-auth — Put the hosted branch behind basic auth (opt-in, calls AWS)"
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
	$(VENV_CFN_LINT) --non-zero-exit-code error

# ============================================================
# Cleanup proposal
# ============================================================
# Read-only. Needs AWS credentials, so it is not a CI gate. Reports the open items
# in docs/ROADMAP.md and withholds the proposal while any remain — the remaining
# verification work needs the environment, and an FSx for ONTAP file system is
# slow to rebuild. Pass ARGS="--anyway" to inventory regardless.
#
# It never deletes. Deletion lives in scripts/cleanup_generic_ucs.py and
# scripts/teardown-uc29-uc30.sh, and a test asserts this script calls nothing
# that changes state.
propose-cleanup:
	$(PYTHON) scripts/propose_cleanup.py $(ARGS)

# Inventory of FSx for ONTAP S3 access points, derived from the FSx API rather
# than a hand-kept list, so a deleted or MISCONFIGURED access point cannot keep
# looking correct in a config file. Read-only. REGIONS overrides the default;
# ARGS passes the rest (--accounts/--role-name, --lifecycle, --format,
# --require-alias). See the module docstring for the cross-account form.
discover-s3ap:
	$(PYTHON) scripts/discover_s3_access_points.py --regions $(or $(REGIONS),ap-northeast-1) $(ARGS)

# Reports where groupApMapping in portal-config.ts disagrees with the access point
# tags. The file stays authoritative -- this only says when it stopped matching
# the resources, which nothing was reporting. Read-only. Exit 2 means
# portal-config.ts is absent (gitignored), which is not the same as agreement.
check-group-ap-tags:
	$(PYTHON) scripts/check_group_ap_tags.py --regions $(or $(REGIONS),ap-northeast-1) $(ARGS)

# Compares the deployed sandbox against amplify_outputs.json and portal-config.ts:
# which pool the browser will use and which sandbox owns it, whether the
# ONTAP-facing functions are in the VPC, and whether the DynamoDB route matches
# what the config claims. Read-only. Run before handing a URL to a reviewer --
# reaching the page is not evidence that anyone can sign in.
portal-preflight:
	$(PYTHON) scripts/portal_preflight.py $(ARGS)

# Grant the two-axis groups. Dry run unless ARGS includes --apply, and idempotent, so
# it can be re-run after adding people without tracking who was done.
#
# Order is load bearing: grant, have those users re-authenticate, then set
# enforceRoles: true and deploy. Reversed, every write is refused until the last user
# has signed in again, because the AppSync rules name groups and the groups travel in
# the ID token.
#
#   make portal-grant-roles ARGS='--assign a@example.com=contributor,internal'
#   make portal-grant-roles ARGS='--apply --from-file roles.txt'
portal-grant-roles:
	$(PYTHON) scripts/grant_portal_roles.py $(ARGS)

# Create a demo account and grant it a role and a scope. Delegates the grant to
# grant_portal_roles.py, so the group semantics live in exactly one place; this adds
# the account, a password the pool's policy accepts, and a statement of what the role
# unlocks before it is granted.
#
# Pass --expected-sandbox whenever a second sandbox exists. An account created in the
# wrong pool is not an error at creation time: the portal loads, the form renders, and
# the credential is rejected with nothing else said.
#
#   make portal-demo-user ARGS='--username demo@example.com --groups storage-admin,internal --expected-sandbox demo'
portal-demo-user:
	$(PYTHON) scripts/portal_provision_demo_user.py $(ARGS)

# Publish the built frontend to Amplify Hosting, which is the AWS-internal way to give
# another machine an https origin. https is required rather than preferred: sign-in
# uses crypto.subtle, which browsers restrict to secure contexts, so a LAN address
# cannot stand in.
#
# The bundle compiles amplify_outputs.json into itself, so the hosted URL is only as
# permanent as the backend behind it. `portal-hosting-url` reports which sandbox and
# pool the published bundle was built against.
#
#   make portal-hosting                      # build, publish, report the URL
#   make portal-hosting ARGS=--skip-build    # publish the existing dist/
portal-hosting:
	$(PYTHON) scripts/portal_deploy_hosting.py $(ARGS)

portal-hosting-url:
	$(PYTHON) scripts/portal_deploy_hosting.py --show

# Basic auth is opt-in, not the default: Cognito sign-in is already a real gate, so
# requiring a second credential for every demo adds a secret to hand over without
# changing who can sign in. What it adds is keeping a published URL out of casual
# reach, which matters once the URL has travelled further than the accounts have.
# `portal-hosting-url` reports which gates are in front of the page.
#
#   make portal-basic-auth        # generate a password and enable it
#   make portal-basic-auth-off    # remove it
portal-basic-auth:
	$(PYTHON) scripts/portal_deploy_hosting.py --basic-auth

portal-basic-auth-off:
	$(PYTHON) scripts/portal_deploy_hosting.py --no-basic-auth

# ============================================================
# Drift checks
# ============================================================
# Offline. Covers docs/, the portal docs, and drafts/blog when it exists locally.
# The rules' own tests run under `make test` with the rest of scripts/tests; this
# target runs them too so a rule change can be checked without the full suite.
drift:
# The gates themselves, before anything they check. A gate that reports success
# without running is worse than no gate, and three shapes of that had shipped:
# `security` not declared .PHONY (make answered "up to date" and ran bandit zero
# times while sitting in the pre-commit list), `lint-python-check` and `lint-ops`
# ending in `|| <same command without the config>` (the fallback always ran and
# `||` reports only its status), and `lint-cfn` calling whatever cfn-lint PATH
# offered — homebrew 1.52.1 against a pinned 1.53.3, a different rule set
# reporting success either way. These run the gate targets with an empty PATH and
# require each to fail, rather than reading the recipes and reasoning about them.
	$(PYTHON) -m pytest scripts/tests/test_makefile_phony.py scripts/tests/test_gate_integrity.py --tb=short -q
# The pinned binary is only pinned if it is the one that runs. Fails rather than
# warns: a warning about a silent divergence is the same kind of thing as the
# divergence, something that scrolls past while the wrong tool keeps answering.
	$(PYTHON) -m pytest scripts/tests/test_check_tool_versions.py --tb=short -q
	$(PYTHON) scripts/check_tool_versions.py
# A tests/ directory no runner lists does not fail — it passes on the machine of
# whoever types the path, and is absent from every pipeline. 790 tests were in
# neither the Makefile nor CI before pattern-test-dirs.txt became the single list;
# 53 more (thumbnails 37, snapshots 13, security 3) were still outside it after.
	$(PYTHON) -m pytest scripts/tests/test_test_dir_coverage.py --tb=short -q
# Listing every tests/ directory is not enough if running them together answers
# differently from running them one at a time. Fourteen functions have an `index.py` and
# nine a `handler.py`; each test directory imported its own as `handler` or `index`, so
# whichever was imported first won `sys.modules` and the rest silently received that one.
# Per-directory runs passed. The whole tree in one invocation gave 375 failures and 58
# errors, and one test that patched the wrong module reached real AWS instead of a stub,
# turning a 10-second directory into a 5-minute one. `--import-mode=importlib` does not
# cover it: the colliding name belongs to the application module, not the test module.
	$(PYTHON) -m pytest scripts/tests/test_check_test_module_names.py --tb=short -q
	$(PYTHON) scripts/check_test_module_names.py
# The cdk-nag ratchet's own tests. The check itself is not run here: it needs a synth
# (node_modules plus a portal-config), so it runs in the portal's CI job. These assert the
# comparison fails in both directions -- a finding that is not recorded, and a recorded
# finding that has been fixed -- and that every entry in the committed baseline still has a
# reason attached, which is the part that decays as the file is edited.
	$(PYTHON) -m pytest scripts/tests/test_check_cdk_nag_baseline.py --tb=short -q
# `make drift` and the workflows are two lists of checks, and nothing made them
# agree. Four checks below this line ran here and in no workflow at all, so a pull
# request could merge past every one of them: check_en_doc_language,
# check_pattern_env_contract, check_samconfig_contract and check_ops_shared_staged.
	$(PYTHON) -m pytest scripts/tests/test_gates_run_in_ci.py --tb=short -q
# A workflow GitHub refuses to load runs nothing, and the run list says "failure",
# which reads like a failing test rather than a file that never started. ci.yml sat
# like that for three days: a job was deleted and its name left in
# `final-status.needs`, so all 8 of its jobs were absent from every pull request
# merged in between while 94 runs were recorded as failures. yaml.safe_load parses
# that file happily -- a dangling `needs` is valid YAML and invalid only against the
# Actions schema -- so nothing local could see it.
	$(PYTHON) -m pytest scripts/tests/test_workflows_are_loadable.py --tb=short -q
# The irreversible-operations guard. It has to be a TRACKED file: `.kiro/` is
# gitignored, so a guard living only there does not exist for a collaborator, a
# fresh clone, or CI, and a hook pointing at $HOME silently protects one machine.
# In the sibling repository the $HOME copy was the one executing and it allowed 10
# of the 26 cases the tracked copy documented. These tests assert the guard is in
# the repository, that the hook runs the tracked path, and that all three outcomes
# (block / ask / allow) behave as declared — a guard tested only on block cases
# could be blocking everything.
	$(PYTHON) -m pytest scripts/tests/test_guard_irreversible_ops.py --tb=short -q
# A workflow step that ends in `|| true` cannot fail. 24 occurrences were audited
# on 2026-08-15: 21 were the grep-no-match idiom (output captured, then tested),
# and 3 were disarmed gates. cfn-guard was given `solutions/**/template-deploy.yaml`,
# which the Actions shell does not expand, so it exited 255 having scanned nothing
# — in two duplicated jobs — while all 7 of its rule files also failed to parse
# under 3.x. `zizmor .` could not fail either, so the workflow named "Actions
# Security Lint" was advisory without saying so.
	$(PYTHON) -m pytest scripts/tests/test_workflow_gate_integrity.py --tb=short -q
# The cfn-guard rules and the gate that runs them. Only the tests run here: the scan
# itself needs the cfn-guard binary, which is installed in CI but not assumed on a
# laptop, so it lives in `make security-cfn` and the tests skip when it is absent.
# The static half — no 2.x `when %INPUT`, no bare `FAIL`, no duplicate rule names —
# runs everywhere, because those are the faults that made the gate vacuous and they
# are all visible without the tool.
	$(PYTHON) -m pytest scripts/tests/test_check_cfn_guard.py --tb=short -q
# The account-ID shape check. Its own tests matter more than the rule: a scanner that
# reads nothing reports a clean tree, so one test disables every placeholder shape and
# requires the repository to then produce findings, and another asserts the reported
# output does not contain the value it found — CI logs are public here.
	$(PYTHON) -m pytest scripts/tests/test_check_account_id_placeholders.py --tb=short -q
	$(PYTHON) -m pytest scripts/tests/test_stale_claim_rules.py --tb=short -q
# The measured-false claim rule. Separate from the stale-claim rules above because it
# retires on a new measurement rather than on a code marker, and because its scan range
# is every tracked document rather than DOC_GLOBS -- the older globs read docs/ja/ and
# docs/en/, and all twelve occurrences of the claim were outside both, in docs/*.md, an
# infrastructure README and a CloudFormation parameter description. Its own tests assert
# that an empty corpus and a missing evidence file both fail rather than report clean.
	$(PYTHON) -m pytest scripts/tests/test_measured_false_claims.py --tb=short -q
# A name the code depends on and no template creates. Both rules below exist because
# the same shape shipped twice: five endpoints guarded on a Cognito group that
# `defineAuth` never declared, and handlers reading environment variables nothing
# set. Neither failed loudly — the group made a fresh deploy's admin sections
# absent, and the variables made a reachable endpoint fail as though it were
# unconfigured.
	$(PYTHON) -m pytest scripts/tests/test_iac_completeness_rules.py --tb=short -q
# The theme and i18n rules inside check_portal_drift.py. Each was added after the
# previous version of it passed while the defect was present: the colour-literal rule
# was anchored to the start of a line and could not see `.state-online { background:
# #dcfce7; }`, so it reported 5 literals out of 201; it read only the stylesheet, so
# six agent cards kept light fills in inline styles; and a t() call anywhere on a
# line excused an untranslated literal beside it. A rule whose pattern misses the
# shape it is aimed at is indistinguishable from a clean tree.
	$(PYTHON) -m pytest scripts/tests/test_theme_literal_check.py --tb=short -q
# The `enabled` / `isPending` rule, also inside check_portal_drift.py. A gated query is
# pending forever, so reading that as loading is a spinner that never clears: the qtree
# panel rendered one instead of the volume dropdown it needed someone to use, and no
# request was ever made. Types, lint and every other gate passed -- the query is correct
# and only the meaning taken from the flag was wrong. Its tests carry more weight than
# the rule: three versions of the source reader silently stopped seeing code, and a
# reader that sees nothing reports a clean tree.
	$(PYTHON) -m pytest scripts/tests/test_query_gate_rule.py --tb=short -q
# The unsubstituted-placeholder rule, also inside check_portal_drift.py. The quota panel
# asked `「{name}」を本当に削除しますか？` in a delete confirmation, braces and all, while
# four other panels substituted the same key. Its own tests carry the weight: the first
# version of the rule reported the four call sites that use the fill() and withNodes()
# helpers, and a rule that reports correct code is a rule someone turns off.
	$(PYTHON) -m pytest scripts/tests/test_i18n_placeholder_check.py --tb=short -q
# The presign-safe S3 client rule, also inside check_portal_drift.py. The portal's upload
# link had never worked: `generate_presigned_url` signs with SigV2 unless told otherwise,
# and the default addressing style presigns the global host, which answers 301 with a
# regional one the signature cannot follow. Six other functions presign and all six were
# already correct, so the rule accepts both working shapes and rejects only the default.
	$(PYTHON) -m pytest scripts/tests/test_presign_config_check.py --tb=short -q
	$(PYTHON) scripts/check_portal_drift.py
# boto3 and urllib3 are pinned in pyproject.toml and requirements.txt both, and
# Renovate manages the two as separate managers. It raised boto3 in pyproject.toml
# and left requirements.txt a patch behind; nothing failed, because the tests run
# against one file and the package metadata claims the other.
	$(PYTHON) -m pytest scripts/tests/test_check_runtime_pins_agree.py --tb=short -q
	$(PYTHON) scripts/check_runtime_pins_agree.py
# The Lambda runtime version, which the check above does NOT cover despite the
# similar name — that one compares dependency pins. `PY_VERSION` carried a comment
# saying it "must match the Lambda runtime in the SAM templates" and nothing
# verified it, while the version was repeated in 350 tracked places: 325
# `Runtime: python3.13` lines, 24 CDK tokens and one CDK assertion test. Raising
# PY_VERSION alone changes which interpreter runs the tests and nothing that gets
# deployed; raising some templates and not others deploys two runtimes from one
# repository, and they are independent stacks, so nothing else ever puts two side
# by side. This also caught the CI matrix gating the build on 3.11 while
# requires-python declared >=3.12.
	$(PYTHON) -m pytest scripts/tests/test_check_lambda_runtime_agrees.py --tb=short -q
	$(PYTHON) scripts/check_lambda_runtime_agrees.py
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
# The two checks above are about the shape of a call. This one is about who the call is
# allowed to name: eight endpoints took a client-supplied object key while consulting
# neither the caller's access point nor the caller's prefixes. Two of them were already
# handed the mapping in backend.ts and never read it, so reviewing the CDK would not
# have found it. It also checks that the resolver forwards the groups, because a
# boundary whose input is missing resolves to "unrestricted" rather than to an error.
	$(PYTHON) -m pytest scripts/tests/test_portal_key_boundary.py --tb=short -q
	$(PYTHON) scripts/check_portal_key_boundary.py
# Two capabilities are withheld from callers outside the organisation -- the AI
# endpoints and share links -- and both are enforced in the handler rather than in
# AppSync, so nothing structural stops a new endpoint from omitting the check. This
# finds the endpoints by what they do (which AWS client they build, whether the caller
# chooses the URL lifetime) rather than by a list, so one added later is in scope
# without anybody remembering to add it. It also checks the resolver forwards the
# groups: with none arriving, every caller reads as internal and the restriction is
# absent while the code that implements it is present and correct.
	$(PYTHON) -m pytest scripts/tests/test_portal_external_policy.py --tb=short -q
	$(PYTHON) scripts/check_portal_external_policy.py
# Translations nobody can reach, and relative links that resolve to nothing. 27 of
# 83 pairs had no language switcher, and 18 links in the portal docs alone were
# dead because ../../docs/ from that directory is solutions/docs/, which does not
# exist. A dead relative link renders as ordinary text until someone clicks it.
	$(PYTHON) scripts/check_doc_pairs.py
# check_doc_pairs above verifies the translations that EXIST are reachable. Nothing
# said which ones ought to exist: every i18n check here discovered groups from what
# was on disk, so a document with no twin was not a finding, it was a smaller group
# — a missing translation invisible by construction. docs/i18n-manifest.toml declares
# the requirement, and this compares the tree against it. It also compares heading
# structure across ALL locales; the older parity check covers docs/ja vs docs/en only
# (28 of 209 groups) and nothing looked at the other six languages at all, which is
# why they drifted together: produced in one batch, never re-run as the sources grew.
	$(PYTHON) -m pytest scripts/tests/test_i18n_parity.py --tb=short -q
	$(PYTHON) scripts/check_i18n_parity.py --quiet
# The language switcher is generated. Hand-maintained across 1,361 files it produced
# 12 different label formats, marked the current language three different ways, and
# left 53 group members with no switcher at all — so a reader who landed on one
# language had no way to reach their own. `--check` makes a hand edit a build failure.
	$(PYTHON) scripts/sync_lang_switcher.py --check
# AGENTS.md is loaded on every turn and cannot be made conditional, so it had grown
# to 78 KB carrying pitfall tables that matter only while doing that one kind of
# work. Splitting it into task-triggered steering is undone by one useful paragraph
# at a time unless something objects. This also catches the failure that made the
# split necessary: `inclusion: auto` without `name` and `description` is never
# registered, so the file is never read and nothing says so.
	$(PYTHON) -m pytest scripts/tests/test_agent_context_budget.py --tb=short -q
	$(PYTHON) scripts/check_agent_context_budget.py
# A missed translation leaves no trace: the .en.md file renders, its links resolve,
# and only a reader who does not read Japanese notices. 96 lines were sitting in 37
# files, 24 of them the same `# 前提: AWS SAM CLI ...` comment copied into every
# pattern's demo guide. Japanese that belongs in an English document — statutes,
# the language switcher, links that say they go to the Japanese version — is
# allowlisted with its reason.
	$(PYTHON) -m pytest scripts/tests/test_en_doc_language.py --tb=short -q
	$(PYTHON) scripts/check_en_doc_language.py
# The OPS handlers import shared/ lazily, inside functions, so a package missing
# shared/ raises ImportError only in Lambda at first call. The unit tests run from
# the repo root where shared/ is importable already, so they pass either way. Five
# of the six patterns shipped with no staging step at all and every test was green;
# the built artifact held handler.py and nothing else.
	bash scripts/check_ops_shared_staged.sh
# A template passing an environment variable under a name its handler does not read.
# The portal has the opposite rule and exempts reads that carry a default, which is
# what hid this: nonprofit-grant-management sent GRANT_PREFIX while the handler read
# GRANT_APPLICATION_PREFIX with a default of its own, so the operator's parameter was
# discarded without a word and the run discovered nothing. Two more patterns had the
# same shape, one of them with the parameter entirely unwired.
	$(PYTHON) -m pytest scripts/tests/test_pattern_env_contract.py --tb=short -q
	$(PYTHON) scripts/check_pattern_env_contract.py
# The demo guides tell the operator to copy samconfig.toml.example and deploy, so the
# example is the documented interface and a defect in it is a defect in that path.
# 2026-08-12: 17 examples shipped S3AccessPointName= empty, which drops the
# accesspoint-form ARNs from the IAM policy -- the stack deploys clean and then denies
# every S3 AP access. 3 more used parameter names the template does not declare (which
# CloudFormation rejects outright) and 4 patterns had no example at all. cfn-lint cannot
# see any of this: the template is valid and the example is not a template.
	$(PYTHON) -m pytest scripts/tests/test_samconfig_contract.py --tb=short -q
	$(PYTHON) scripts/check_samconfig_contract.py
# Obligations that come due on a date rather than on a code change. A SnapLock audit
# log volume carries a 6-month minimum retention that blocks deletion of the volume,
# its SVM and the file system; AWS confirmed there is no early-deletion route and that
# a case cannot be held open that long, so the billing follow-up has to be re-opened at
# expiry. All of that was recorded in a document, and a paragraph does not fire on
# 2027-02-06 -- nothing in the repository would have said anything on that date while
# the resource kept billing and kept the file system undeletable. The ledger holds the
# action and the date; the case number and resource IDs stay in a gitignored note,
# which the check verifies is actually ignored.
	$(PYTHON) -m pytest scripts/tests/test_check_dated_obligations.py --tb=short -q
	$(PYTHON) scripts/check_dated_obligations.py
# Text half only. The OCR half reads 463 tracked images and takes ~8 minutes, which
# does not belong in a check run before every commit, but the text half takes seconds
# and is the half that catches an identifier pasted into a source file or a fixture.
# CI runs both. Added because a real VPC id reached a test fixture and only CI saw
# it: `make drift` had no sensitive-string check at all, so the leak survived every
# local gate and was caught after the pull request was opened.
	$(PYTHON) scripts/_check_sensitive_leaks.py --text

# Fetches the published posts from Hatena and dev.to, so it needs network and is
# not part of `make lint`. Run it after shipping a feature that makes an article's
# "you would have to build this yourself" list shorter.
drift-published:
	$(PYTHON) scripts/check_published_articles.py

# ============================================================
# ONTAP connection preflight
# ============================================================
# Not a drift check and not offline: it calls AWS. Kept separate so `make drift` stays
# runnable without credentials.
#
# Six things have to line up for the portal's ONTAP panels to show data, and a failure
# in any of them used to reach the UI as the same sentence -- "Volume 'vol1' not found
# on SVM 'fsxsvm01'" -- under a heading that blamed the network. On the verification
# environment that volume existed, the request reached the cluster, and the actual cause
# was a password Secrets Manager and ONTAP disagreed about. This walks the six in order
# and names the one that broke.
#
#   make ontap-preflight
#   make ontap-preflight FS_ID=fs-0123456789abcdef0        # adds stages 2-4
#   make ontap-preflight FS_ID=... LAMBDA=<function-name>  # adds stage 6
#
# The auth stage -- whether ONTAP accepts the credentials -- cannot be reached from a
# laptop: the management LIF is private. LAMBDA asks the deployed function to make the
# call. Without it the stage reports SKIP rather than passing, because a green run that
# never tried the one thing that was wrong is worse than no run.
#
# FS_ID also enables the pairing stage, which answers a question the auth stage cannot be
# used to answer safely: is the secret for the same file system as the management IP. An
# account with two file systems has two fsxadmin passwords, and pairing one cluster's
# address with the other's credentials passes every other stage. Trying it is not a way to
# find out -- fsxadmin locks out after 5 failures with lockout-duration=0, so five
# attempts take the credential out of service and waiting does not restore it. The stage
# compares the secret's FileSystemId tag instead, and authenticates nothing.
PORTAL_CONFIG := solutions/amplify-portal/amplify/portal-config.ts

ontap-preflight:
	$(PYTHON) scripts/check_ontap_connection.py --config $(PORTAL_CONFIG) \
		$(if $(FS_ID),--file-system-id $(FS_ID),) \
		$(if $(LAMBDA),--via-lambda $(LAMBDA),) \
		$(if $(AWS_DEFAULT_REGION),--region $(AWS_DEFAULT_REGION),)

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
# Account IDs, by shape rather than by value. The exact-match check in
# security-check.yml compares against a repository secret, which means it cannot run
# without one — and an absent secret produced the same green result as a clean tree,
# which is how it sat unnoticed since it was written. This needs no secret, so it has
# no such state, and it catches any real ID rather than the single configured one.
	$(PYTHON) scripts/check_account_id_placeholders.py

# cfn-guard over every deployable template. Separate from `security` because it needs
# the cfn-guard binary rather than a pip package, and separate from `lint-cfn` because
# cfn-lint checks template validity while these rules check security posture —
# encryption at rest, no public access, least-privilege IAM, SageMaker isolation.
# Fails on any finding not in the recorded baseline, and also when a baseline finding
# has been fixed, so progress gets locked in rather than leaving room to reopen.
security-cfn:
	$(PYTHON) scripts/check_cfn_guard.py

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

# One invocation with the pinned binary. It used to be two: the first with
# `--config pyproject.toml 2>/dev/null`, then `|| ` the same command without it.
# The fallback always ran — the first form's exit code was discarded along with
# its stderr — so this target silently linted with a different config than it
# named, and could not fail in the first place because `||` only reports the
# second command's status. Same shape that `lint-python-check` was fixed for.
lint-ops:
	$(VENV_RUFF) check operations/ shared/ontap_metrics.py shared/demo_data_loader.py shared/schemas/ops_events.py

lint-cfn-ops:
	$(VENV_CFN_LINT) operations/capacity-rightsizing/template.yaml \
		operations/snapshot-lifecycle/template.yaml \
		operations/tiering-optimizer/template.yaml \
		operations/storage-efficiency/template.yaml \
		operations/cost-optimization/template.yaml \
		operations/qos-monitoring/template.yaml

build-ops1:
	cd operations/capacity-rightsizing && sam build

deploy-ops1:
	cd operations/capacity-rightsizing && sam deploy --config-file samconfig.toml
