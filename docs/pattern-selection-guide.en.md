# Pattern Selection Guide — Use Case Recommendations Based on Customer Situations

🌐 **Language / 言語**: [日本語](pattern-selection-guide.md) | [English](pattern-selection-guide.en.md)

## Overview

A guide for selecting the optimal pattern from 28 use cases + 6 FlexCache/FlexClone patterns based on customer circumstances. Intended for use by Partners/SIs during initial customer conversations.

## Recommended Patterns by Customer Situation

| Customer Situation | Recommended Pattern |
|---|---|
| Already using FSx for ONTAP for file sharing | Industry-specific UC + DemoMode=false |
| FSx for ONTAP not deployed, wants to evaluate workflow | Any UC + DemoMode=true |
| Document processing-centric (PDF, contracts, reports) | UC20 / UC23 / UC24 / UC26 / UC27 / UC28 |
| Image/inspection workload-centric | UC19 / UC21 / UC22 / UC25 |
| Log / time-series / analytics workload | UC18 / UC25 (SCADA) |
| Safety-critical domain requiring Human Review | UC22 / UC25 + human_review module |
| PII / personal data protection required | UC27 / UC26 + data_classification module |
| ESG / sustainability reporting | UC23 + framework mapping |
| Expansion of existing NFS/SMB workloads | FC1-FC6 (FlexCache/FlexClone patterns) |
| Equipment maintenance × multimodal AI (image + document RAG) | UC22 + Rekognition + Bedrock multimodal ([7-Eleven case ref](investigations/dais2026-agent-bricks-industry-cases.md#1-7-eleven-メンテナンス技術者向け-genai-アシスタント)) |
| Pharma/Life Sciences × multi-agent permission-aware RAG | UC7 + Step Functions multi-agent routing ([AstraZeneca case ref](investigations/dais2026-agent-bricks-industry-cases.md#2-astrazeneca-マルチエージェントシステム10x-スケール)) |
| Greenfield object-native workload (no NAS requirement) | Prefer standard S3 / DynamoDB serverless-native architecture |

## Technical Selection by Workload

| Workload Characteristics | Recommended AI Service | Representative UC |
|---|---|---|
| Image object detection/classification | Rekognition | UC19, UC21, UC22, UC25, UC26 |
| Structured data extraction from PDF/documents | Textract + Comprehend | UC20, UC24, UC26, UC27, UC28 |
| Natural language inference/classification/summarization | Bedrock (Nova/Claude) | All UCs |
| Time-series anomaly detection | Athena + Bedrock | UC18, UC25 |
| ESG framework mapping | Bedrock (structured prompt) | UC23 |

## DemoMode → Production Migration Criteria

| Evaluation Point | Verified in DemoMode | Additional Verification Before Production |
|---|---|---|
| Workflow operation | ✅ Step Functions SUCCEEDED | — |
| AI extraction accuracy | ✅ Confirmed with sample data | Evaluate with domain validation set |
| Performance | ⚠️ Via S3 bucket (reference value) | Measure via FSx for ONTAP S3 AP |
| Authorization model | ⚠️ S3 IAM only | IAM + S3 AP policy + ONTAP ID |
| Network | ⚠️ Public path | Internet/VPC-origin design decision |
| Governance | ⚠️ Demo labels | Data classification + lineage + retention |
| Cost | ✅ ~$0.10/execution | + FSx for ONTAP (~$194/month base) |

## Additional Considerations for Safety-Critical / Regulated Industries

The following industries require additional governance review after pattern selection:

| Industry | Additional Considerations |
|---|---|
| Transportation/Railway (UC22) | Escalation threshold settings, Human Review SLA, coordination with maintenance planning teams |
| Power/Utilities (UC25) | SCADA data classification, integrated evaluation process for multimodal results |
| HR/Talent (UC27) | Labor law/anti-discrimination law compliance, PII handling rules, hiring decisions made by humans |
| Finance/Insurance (UC2/UC14) | FISC compliance, audit trails, data retention policies |
| Healthcare (UC5/UC7) | Personal information protection laws, medical information handling regulations |
| Public Sector (UC16) | NARA compliance, Freedom of Information Act compliance, data residency requirements |

> **Important**: These patterns are reference implementations and do not automatically satisfy customer regulatory, audit, operational, or data classification requirements. Verify compliance with the customer's own policies and regulatory requirements before production use.

## NetworkOrigin Design Decision

| Requirement | Recommended NetworkOrigin |
|---|---|
| All consumers within the same VPC | VPC-origin |
| External / on-premises client access | Internet-origin |
| Strict private access restriction | VPC-origin |
| Access from multiple VPCs | Evaluate TGW/peering, or Internet-origin |
| Lambda (outside VPC) access | Internet-origin |
| Lambda (inside VPC) access | VPC-origin + S3 Gateway EP |

> **Note**: NetworkOrigin cannot be changed after creation. Choose carefully during design.
