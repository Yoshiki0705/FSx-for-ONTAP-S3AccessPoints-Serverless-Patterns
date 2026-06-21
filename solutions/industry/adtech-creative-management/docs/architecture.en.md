# UC19: Advertising & Marketing / Creative Asset Management — Asset Cataloging and Brand Compliance Check

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["Creative Assets<br/>.jpeg/.png/.tiff (Images)<br/>.mp4/.mov (Video)<br/>.psd (Design Files)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Daily 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC execution<br/>• Media file detection<br/>• Format + size filter (5 GB limit)<br/>• Manifest generation"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• Get asset via S3 AP<br/>• Rekognition DetectLabels (80% confidence threshold)<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• Generate up to 50 tags/asset"]
        TC["3️⃣ Text Compliance Lambda<br/>• Textract text extraction (us-east-1 cross-region)<br/>• Load brand terminology guidelines JSON<br/>• Bedrock InvokeModel — brand compliance check<br/>• Result: compliant / non-compliant + matched terms list"]
        RL["4️⃣ Report Lambda<br/>• Asset catalog generation (JSON + CSV)<br/>• Moderation violation flagging (requires-review)<br/>• CloudWatch EMF Metrics emission<br/>• SNS notification"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json<br/>Asset catalog (one record per asset)"]
        CSV["reports/{execution-id}/asset-catalog.csv<br/>CSV format catalog"]
        FLAGGED["reports/{execution-id}/flagged-assets.json<br/>Moderation-violated assets list"]
        ERROUT["errors/{execution-id}/{filename}.json<br/>Processing error records"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email<br/>(Moderation violation detection alert)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    VA --> CATALOG
    TC --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
    RL --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for ONTAP volume |
| **File Types** | .jpeg / .png / .tiff (images), .mp4 / .mov (video), .psd (design files) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Filter Strategy** | Media format filter + 5 GB size limit |

### Processing
| Step | Service | Processing |
|------|---------|------------|
| Discovery | Lambda (VPC) | Media file detection, format/size filter, manifest generation |
| Visual Analyzer | Lambda + Rekognition | DetectLabels (80% threshold), DetectModerationLabels, DetectText, tag generation (max 50) |
| Text Compliance | Lambda + Textract + Bedrock | Text overlay extraction, brand terminology guideline matching, compliant/non-compliant determination |
| Report | Lambda | Asset catalog generation (JSON + CSV), moderation violation flagging, SNS notification |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Asset Catalog (JSON) | `reports/{execution-id}/asset-catalog.json` | Labels, compliance status, tags for all processed assets |
| Asset Catalog (CSV) | `reports/{execution-id}/asset-catalog.csv` | CSV format catalog (for BI tool integration) |
| Flagged Assets | `reports/{execution-id}/flagged-assets.json` | Moderation-violated assets (violation_category, confidence, path) |
| Processing Errors | `errors/{execution-id}/{filename}.json` | File path, error type, timestamp |
| SNS Notification | Email | Moderation violation detection alert |

---

## Key Design Decisions

1. **Parallel Visual Analyzer and Text Compliance** — Image analysis and text compliance checking are independent. Parallelized via Step Functions Map State to reduce processing time
2. **Hybrid Rekognition + Bedrock Analysis** — Rekognition for quantitative label/moderation determination, Bedrock for contextual brand guideline compliance judgment
3. **Cross-Region Textract** — Textract requires us-east-1 for some features; cross-region invocation is transparently handled via shared/cross_region_client.py
4. **80% Moderation Threshold** — Balances reducing false positives while minimizing risk of missing problematic content
5. **JSON + CSV Dual Format Output** — JSON for API integration, CSV for BI tool / Excel review
6. **5 GB File Size Limit** — Practical limit considering S3 AP PutObject constraints and Lambda memory
7. **Polling-based** — S3 AP does not support event notifications; daily execution via EventBridge Scheduler

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for ONTAP | Creative asset storage |
| S3 Access Points | Serverless access to ONTAP volumes |
| EventBridge Scheduler | Daily trigger (00:00 UTC) |
| Step Functions | Workflow orchestration (parallel Map State) |
| Lambda | Compute (Discovery, Visual Analyzer, Text Compliance, Report) |
| Amazon Rekognition | Visual analysis (labels, moderation, text detection) |
| Amazon Textract | Text overlay extraction (us-east-1 cross-region) |
| Amazon Bedrock | Brand guideline compliance inference (Claude / Nova) |
| SNS | Moderation violation alert notification |
| Secrets Manager | ONTAP REST API credential management |
| CloudWatch + X-Ray | Observability (EMF Metrics, tracing) |
