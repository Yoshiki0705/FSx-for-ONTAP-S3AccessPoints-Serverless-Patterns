# UC27: Human Resources — Resume Screening / PII Strict Mode Architecture

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["Business Data<br/>Files on FSx ONTAP Volume"]
    end
    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end
    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>Daily 00:00 UTC"]
    end
    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda"]
        PROC["2️⃣ Processing Lambda(s)<br/>Textract, Comprehend, Bedrock"]
        RL["3️⃣ Report Lambda"]
    end
    subgraph OUTPUT["📤 Output"]
        REPORTS["reports/ — Analysis Results"]
        ERROUT["errors/ — Error Records"]
    end
    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> PROC
    PROC --> RL
    RL --> REPORTS
    RL --> ERROUT
```

---

## Key Design Decisions

1. **Error Isolation** — Single file failure does not block other file processing
2. **Exponential Backoff** — Unified retry via shared/retry_handler.py
3. **Polling-Based** — S3 AP does not support event notifications; uses EventBridge Scheduler
4. **Cross-Region** — Textract called in us-east-1
5. **Idempotency** — Re-processing same file does not create duplicate records

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for ONTAP | File storage |
| S3 Access Points | Serverless access to ONTAP volumes |
| EventBridge Scheduler | Daily trigger |
| Step Functions | Workflow orchestration |
| Lambda | Compute (Discovery, Resume Extractor, Candidate Scorer, Report) |
| Amazon Textract | AI/ML processing |
| Amazon Comprehend | AI/ML processing |
| Amazon Bedrock | AI/ML processing |
| SNS | Alert notification |
| Secrets Manager | ONTAP REST API credential management |
| CloudWatch + X-Ray | Observability |
