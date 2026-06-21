# UC28: 화학 및 소재 — SDS 위험 분류 추출 / GHS 검증 Architecture

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | 한국어 | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["Business Data<br/>Files on FSx for ONTAP Volume"]
    end
    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end
    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>Daily 00:00 UTC"]
    end
    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda"]
        PROC["2️⃣ Processing Lambda(s)<br/>Textract, Rekognition, Bedrock"]
        RL["3️⃣ Report Lambda"]
    end
    subgraph OUTPUT["📤 Output"]
        REPORTS["reports/ — Results"]
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

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for ONTAP | File storage |
| S3 Access Points | Serverless access to ONTAP volumes |
| Lambda | Compute (Discovery, SDS Extractor, Labbook Analyzer, Report) |
| Amazon Textract | AI/ML processing |
| Amazon Rekognition | AI/ML processing |
| Amazon Bedrock | AI/ML processing |
| CloudWatch + X-Ray | Observability |
