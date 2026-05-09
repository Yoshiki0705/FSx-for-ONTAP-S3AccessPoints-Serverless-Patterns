# UC14: Insurance / Claims — Accident Photo Damage Assessment, Estimate OCR & Assessment Report

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["Insurance claims data<br/>.jpg/.jpeg/.png (accident photos)<br/>.pdf/.tiff (repair estimates)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Runs inside VPC<br/>• S3 AP file discovery<br/>• Photo/estimate type separation<br/>• Manifest generation"]
        DA["2️⃣ Damage Assessment Lambda<br/>• Retrieves photos via S3 AP<br/>• Rekognition DetectLabels<br/>• Damage label detection<br/>• severity_level evaluation<br/>• affected_components identification<br/>• Manual review flag setting"]
        EO["3️⃣ Estimate OCR Lambda<br/>• Retrieves estimates via S3 AP<br/>• Textract (us-east-1 cross-region)<br/>• Text & form extraction<br/>• Repair items, costs, labor, parts<br/>• Low confidence flag setting"]
        CR["4️⃣ Claims Report Lambda<br/>• Bedrock InvokeModel<br/>• Damage assessment + estimate data integration<br/>• Comprehensive assessment report generation<br/>• JSON + human-readable format<br/>• SNS notification"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        DMGOUT["damage-assessment/*.json<br/>Damage assessment results"]
        OCROUT["estimate-ocr/*.json<br/>Estimate OCR results"]
        REPORT["reports/*.json + *.md<br/>Assessment reports"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(assessment completion notification)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> DA
    DISC --> EO
    DA --> CR
    EO --> CR
    DA --> DMGOUT
    EO --> OCROUT
    CR --> REPORT
    CR --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .jpg/.jpeg/.png (accident photos), .pdf/.tiff (repair estimates) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | Full image/PDF retrieval (required for Rekognition / Textract) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | Discover accident photos & estimates via S3 AP, generate manifest by type |
| Damage Assessment | Lambda + Rekognition | DetectLabels for damage label detection, severity evaluation, affected component identification |
| Estimate OCR | Lambda + Textract | Estimate text & form extraction (repair items, costs, labor, parts) |
| Claims Report | Lambda + Bedrock | Integrate damage assessment + estimate data for comprehensive assessment report |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Damage Assessment | `damage-assessment/YYYY/MM/DD/{claim}_damage.json` | Damage assessment results (damage_type, severity_level, affected_components) |
| Estimate OCR | `estimate-ocr/YYYY/MM/DD/{claim}_estimate.json` | Estimate OCR results (repair items, costs, labor, parts) |
| Claims Report (JSON) | `reports/YYYY/MM/DD/{claim}_report.json` | Structured assessment report |
| Claims Report (MD) | `reports/YYYY/MM/DD/{claim}_report.md` | Human-readable assessment report |
| SNS Notification | Email | Assessment completion notification |

---

## Key Design Decisions

1. **Parallel processing (Damage Assessment + Estimate OCR)** — Accident photo damage assessment and estimate OCR are independent; parallelized via Step Functions Parallel State for improved throughput
2. **Rekognition tiered damage assessment** — Manual review flag set when no damage labels detected, promoting human verification
3. **Textract cross-region** — Textract available only in us-east-1; cross-region invocation used
4. **Bedrock integrated report** — Correlates damage assessment and estimate data to generate comprehensive claims report in JSON + human-readable format
5. **Low confidence flag management** — Manual review flag set when Rekognition / Textract confidence scores fall below threshold
6. **Polling (not event-driven)** — S3 AP does not support event notifications, so periodic scheduled execution is used

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | Accident photo & estimate storage |
| S3 Access Points | Serverless access to ONTAP volumes |
| EventBridge Scheduler | Periodic trigger |
| Step Functions | Workflow orchestration (parallel path support) |
| Lambda | Compute (Discovery, Damage Assessment, Estimate OCR, Claims Report) |
| Amazon Rekognition | Accident photo damage detection (DetectLabels) |
| Amazon Textract | Estimate OCR text & form extraction (us-east-1 cross-region) |
| Amazon Bedrock | Assessment report generation (Claude / Nova) |
| SNS | Assessment completion notification |
| Secrets Manager | ONTAP REST API credential management |
| CloudWatch + X-Ray | Observability |
