# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]
### Added
- **File portal: all industry patterns in the AI processing tab.** The job form lists UC1 to UC28 (and OPS1) with the industry and task in the selected language, in 8 languages. `startProcessing` now sends `pattern` in the Step Functions input, and an optional `stateMachineArns` map in `portal-config.ts` (pattern name to state machine ARN, published to AppSync as `SFN_ARN_<prefix>`) starts one state machine per pattern. A pattern without an entry still starts the single `stateMachineArn`. The ARNs are listed explicitly because the deployed stacks are named in more than one way (`fsxn-uc10-construction-bim`, `fsxn-construction-bim`, `fsxn-chemical-sds`)
- **File portal: industry agent templates.** The agent creator can start from 16 industry templates (contracts and policies, financial documents, quality and maintenance, clinical procedures, claims, ordinances, construction, education, HR, property and leases, logistics, telecom incidents, retail, traceability, lab and safety data, ESG and grants). A template fills in the name, description, system prompt, tools and category; every field stays editable
- **Step Functions × AgentCore Gateway pattern: optional `industry` input.** One of 21 industry ids (`shared/industry_focus.py`) adds the industry's points of attention to the summary prompt. Unknown values are ignored and never reach the prompt. `docs/demo-guide.md` lists the ids
### Fixed
- **File portal: wrong pattern names.** `UC3_HEALTHCARE_IMAGING`, `UC10_MEDIA_PRODUCTION` and `UC15_MANUFACTURING_QC` named industries that do not match the pattern carrying that number (UC3 is manufacturing analytics, UC10 construction BIM, UC15 defense satellite). They are removed from the `ProcessingPattern` enum; job history rows keep the old string. Before this change the selected pattern was used only in the execution name, so every choice started the same state machine

### Changed
- **Directory restructuring**: All 42 pattern directories moved into `solutions/` category hierarchy
  - `solutions/industry/` (28 UC patterns)
  - `solutions/sap/erp-adjacent/`
  - `solutions/flexcache/` (7 FlexCache/FlexClone patterns)
  - `solutions/genai/` (2 GenAI patterns)
  - `solutions/ha/lifekeeper-monitoring/`
  - `solutions/event-driven/` (2 event-driven patterns)
  - `solutions/edge/content-delivery/`
- CI workflows split shared and pattern tests to avoid importlib namespace collision
- Makefile targets updated for new directory paths
- All 8 README translations updated with new paths
- 170+ documentation files updated with new directory references

### Added
- Shared-backup-vault lab under `infrastructure/shared-backup-vault-lab/`: CloudFormation templates, deploy/verify/teardown scripts, a stub-based test harness, a Playwright UI spec, and a ja+en README, runbook and verification record. The record table is empty and its status reads "not yet run on real environment".
- `solutions/ha/lifekeeper-monitoring/README.en.md` (English README with Success Metrics)
- `solutions/ha/lifekeeper-monitoring/docs/demo-guide.md` (DemoMode deployment guide)
- Sample LifeKeeper log files in `test-data/ha-lifekeeper-monitoring/`

### Fixed
- `persist-credentials: false` added to all `actions/checkout` steps in `ci.yml`
- Pattern selection guide stale path reference
- Demo guide `cd` commands updated to new paths

## [0.18.0] — 2026-06-20

### Added
- HA LifeKeeper Monitoring pattern (SIOS LifeKeeper + FSx for ONTAP)
- SAM template, Lambda handlers (discovery/processing/report), Step Functions
- Bedrock-powered root cause analysis and health scoring
- 37 unit tests passing
- Architecture documentation with SIOS/AWS blog references

## [0.17.0] — 2026-06-15

### Added
- UC30 `solutions/genai/quick-agentic-workspace` (Amazon Q-style agentic workspace)
- UC29 `solutions/genai/kb-selfservice-curation` (Bedrock KB self-service)
- RAG evaluation framework with mock harness

## [0.16.0] — 2026-06-10

### Added
- FlexCache patterns (FC1-FC7): anycast-dr, dynamic-render-workflow, rag-enterprise-files,
  automotive-cae, life-sciences-research, gaming-build-pipeline, devops-cicd
- Edge content delivery pattern with CDN vendor-neutral approach

## [0.15.0] — 2026-06-01

### Added
- Event-driven FPolicy pipeline (ECS Fargate TCP server + EventBridge)
- Event-driven prototype with latency reporter

## [0.14.0] — 2026-05-20

### Added
- UC19-UC28 industry patterns (adtech through chemical-sds-management)
- Multi-language README support (8 languages)
- Demo guides in 8 languages per pattern

## [0.13.0] — 2026-05-10

### Added
- UC15-UC18 industry patterns (defense-satellite through telecom-network-analytics)
- TriggerMode HYBRID support across all UC patterns
- Shared observability module (EMF metrics + X-Ray tracing)

## [0.12.0] — 2026-04-25

### Added
- UC9-UC14 industry patterns (autonomous-driving through insurance-claims)
- SageMaker inference integration (UC9)
- Cross-region client for multi-region patterns

## [0.11.0] — 2026-04-10

### Added
- SAP/ERP adjacent pattern
- UC7-UC8 (genomics-pipeline, energy-seismic)
- FPolicy protobuf/XML parser in shared/

## [0.10.0] — 2026-03-25

### Added
- UC1-UC6 core patterns (legal-compliance through semiconductor-eda)
- Shared Python modules (s3ap_helper, ontap_client, fsx_helper, exceptions)
- Property-based tests with Hypothesis
- CI/CD pipeline (cfn-lint, pytest, bandit, deploy)
