# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

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
