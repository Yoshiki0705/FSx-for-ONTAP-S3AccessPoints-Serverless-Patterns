# Pattern Selection Guide — Use Case Recommendations Based on Customer Situations

🌐 **Language / 言語**: [日本語](pattern-selection-guide.md) | English

## Overview

A guide for choosing among every pattern in this repository, based on the customer's situation. Intended for use by Partners and SIs during initial conversations.

**One thing first: this page answers "which one to deploy". It does not answer "is that the right shape".** The reasoning behind the design decisions lives in the [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/README.md), and each pattern README ends with the modules to read before going to production. The same content is deliberately not in two places. Its industry-by-industry reading order is currently Japanese only.

### Reading order

| # | What to do | Where |
|---|---|---|
| 1 | **Decide which pattern** | This page |
| 2 | Run it | Each pattern's `README` and `docs/demo-guide.md` |
| 3 | Read before going to production | The "read before going to production" section at the end of each README, which points into the Playbook |
| 4 | Operate it | OPS1-6 under [operations/](#operations-optimisation-ops16--lowering-idle-capacity-and-cost) |

---

## 1. By business problem (industry UC1-UC28)

All of these are Lambda pipelines reading through an S3 Access Point, and all run without FSx for ONTAP when `DemoMode=true`.

### Reading documents (OCR, extraction, classification)

| Problem | Pattern |
|---|---|
| Contract and invoice processing | [UC2 financial-idp](../solutions/industry/financial-idp/) |
| File server audit and data governance | [UC1 legal-compliance](../solutions/industry/legal-compliance/) |
| Paper PDF classification and citation networks | [UC13 education-research](../solutions/industry/education-research/) |
| Delivery slip OCR and warehouse inventory images | [UC12 logistics-ocr](../solutions/industry/logistics-ocr/) |
| Public records archive and FOIA response | [UC16 government-archives](../solutions/industry/government-archives/) |
| Reservation documents and facility inspection | [UC20 travel-document-processing](../solutions/industry/travel-document-processing/) |
| ESG metric extraction and framework mapping | [UC23 sustainability-esg-reporting](../solutions/industry/sustainability-esg-reporting/) |
| Grant application classification and outcome matching | [UC24 nonprofit-grant-management](../solutions/industry/nonprofit-grant-management/) |
| Property image analysis and contract extraction | [UC26 real-estate-portfolio](../solutions/industry/real-estate-portfolio/) |
| Resume screening (strict PII mode) | [UC27 hr-document-screening](../solutions/industry/hr-document-screening/) |
| SDS hazard classification and GHS validation | [UC28 chemical-sds-management](../solutions/industry/chemical-sds-management/) |

### Processing images and video

| Problem | Pattern |
|---|---|
| DICOM classification and de-identification | [UC5 healthcare-dicom](../solutions/industry/healthcare-dicom/) |
| VFX render quality checks | [UC4 media-vfx](../solutions/industry/media-vfx/) |
| Video and LiDAR pre-processing, annotation | [UC9 autonomous-driving](../solutions/industry/autonomous-driving/) |
| BIM model management and drawing OCR | [UC10 construction-bim](../solutions/industry/construction-bim/) |
| Product image auto-tagging | [UC11 retail-catalog](../solutions/industry/retail-catalog/) |
| Satellite imagery analysis | [UC15 defense-satellite](../solutions/industry/defense-satellite/) |
| Creative asset cataloguing and brand compliance | [UC19 adtech-creative-management](../solutions/industry/adtech-creative-management/) |
| Aerial farmland imagery and traceability | [UC21 agri-food-traceability](../solutions/industry/agri-food-traceability/) |
| Equipment inspection images and maintenance reports | [UC22 transportation-maintenance](../solutions/industry/transportation-maintenance/) |
| Accident photo damage assessment and estimate OCR | [UC14 insurance-claims](../solutions/industry/insurance-claims/) |
| Drone inspection imagery and SCADA anomalies | [UC25 utilities-asset-inspection](../solutions/industry/utilities-asset-inspection/) |

### Large scientific and engineering datasets

| Problem | Pattern |
|---|---|
| Design file validation and metadata extraction | [UC6 semiconductor-eda](../solutions/industry/semiconductor-eda/) |
| Quality checks and variant call aggregation | [UC7 genomics-pipeline](../solutions/industry/genomics-pipeline/) |
| Seismic data processing and well log anomalies | [UC8 energy-seismic](../solutions/industry/energy-seismic/) |
| IoT sensor logs and quality inspection images | [UC3 manufacturing-analytics](../solutions/industry/manufacturing-analytics/) |
| Geospatial analysis and urban planning | [UC17 smart-city-geospatial](../solutions/industry/smart-city-geospatial/) |
| CDR and network log anomaly detection | [UC18 telecom-network-analytics](../solutions/industry/telecom-network-analytics/) |

---

## 2. By how the data is placed (FlexCache / FlexClone / SnapMirror)

**Use these when an existing NFS/SMB workload must keep running while something else reads the same data from elsewhere.** Unlike the UC patterns, these are about volume placement rather than a pipeline.

| Problem | Pattern |
|---|---|
| S3 AP alongside NFS/SMB in the same Region | [same-region-s3ap](../solutions/flexcache/same-region-s3ap/) |
| Low-latency reads from another Region | [cross-region-s3ap](../solutions/flexcache/cross-region-s3ap/) |
| A DR replica (SnapMirror) | [snapmirror-cross-region-dr](../solutions/flexcache/snapmirror-cross-region-dr/) |
| The same data read from several sites (AnyCast / DR) | [anycast-dr](../solutions/flexcache/anycast-dr/) |
| CAE analysis run in parallel | [automotive-cae](../solutions/flexcache/automotive-cae/) |
| Render / EDA workflows that scale dynamically | [dynamic-render-workflow](../solutions/flexcache/dynamic-render-workflow/) |
| Game asset sharing and build pipelines | [gaming-build-pipeline](../solutions/flexcache/gaming-build-pipeline/) |
| Research data analysed by several teams | [life-sciences-research](../solutions/flexcache/life-sciences-research/) |
| Fast Dev/Test refresh with FlexClone | [devops-cicd](../solutions/flexcache/devops-cicd/) |
| Internal files as RAG input | [rag-enterprise-files](../solutions/flexcache/rag-enterprise-files/) |

---

## 3. By how it reaches its users

| Problem | Pattern |
|---|---|
| Browser access to NAS files, without a VPN | [File portal (Amplify Gen2)](../solutions/amplify-portal/) |
| Content delivered through a CDN or edge | [content-delivery](../solutions/edge/content-delivery/) ([CDN comparison](cdn-comparison.en.md)) |
| Live streams published as VOD | [media-ivs-vod-publishing](../solutions/edge/media-ivs-vod-publishing/) |
| Internal knowledge curated by its own users | [kb-selfservice-curation](../solutions/genai/kb-selfservice-curation/) |
| Access from an agentic workspace | [quick-agentic-workspace](../solutions/genai/quick-agentic-workspace/) |
| File workflows adjacent to an ERP | [sap/erp-adjacent](../solutions/sap/erp-adjacent/) |

---

## 4. By how it is triggered (polling or event-driven)

| Problem | Pattern |
|---|---|
| Detecting file operations in real time | [event-driven/fpolicy](../solutions/event-driven/fpolicy/) ([FPolicy setup](guides/fpolicy-setup-guide-en.md)) |
| Trying the smallest event-driven shape | [event-driven/prototype](../solutions/event-driven/prototype/) |
| Choosing between polling and event-driven | [TriggerMode decision guide](trigger-mode-decision-guide.en.md) |
| Monitoring built into an HA configuration | [ha/lifekeeper-monitoring](../solutions/ha/lifekeeper-monitoring/) |

---

## 5. Operations optimisation (OPS1-6) — lowering idle capacity and cost

**This is the pillar that does not use S3 Access Points.** These act on a file system that is already running, independently of deploying any pattern.

| Problem | Pattern |
|---|---|
| Deciding whether capacity or throughput is over-provisioned | [OPS1 capacity-rightsizing](../operations/capacity-rightsizing/) |
| Measuring how well dedup and compression work | [OPS2 storage-efficiency](../operations/storage-efficiency/) |
| Optimising FabricPool tiering | [OPS3 tiering-optimizer](../operations/tiering-optimizer/) |
| Tidying snapshot retention | [OPS4 snapshot-lifecycle](../operations/snapshot-lifecycle/) |
| Bringing cost into a FinOps process | [OPS5 cost-optimization](../operations/cost-optimization/) |
| Monitoring QoS policies | [OPS6 qos-monitoring](../operations/qos-monitoring/) |

---

## 6. Entry points by situation

| Customer situation | How to enter |
|---|---|
| Already using FSx for ONTAP for file sharing | Industry UC + `DemoMode=false` |
| FSx for ONTAP not deployed, evaluating the workflow only | Any UC + `DemoMode=true` |
| Safety-critical domain requiring human review | UC22 / UC25 + `shared/human_review.py` |
| PII or personal data protection required | UC26 / UC27 + `shared/data_classification.py` |
| Equipment maintenance × multimodal AI | UC22 + Rekognition + Bedrock multimodal ([case](investigations/dais2026-agent-bricks-industry-cases.md#1-7-eleven-メンテナンス技術者向け-genai-アシスタント)) |
| Pharma and life sciences × multi-agent RAG | UC7 + Step Functions multi-agent routing ([case](investigations/dais2026-agent-bricks-industry-cases.md#2-astrazeneca-マルチエージェントシステム10x-スケール)) |
| Greenfield object-native workload (no NAS requirement) | **The patterns here are not needed.** A standard S3 / DynamoDB serverless architecture is the simpler answer |

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
