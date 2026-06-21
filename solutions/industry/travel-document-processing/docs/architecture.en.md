# UC20: Travel & Hospitality — Reservation Document Processing / Facility Inspection Architecture

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for ONTAP"]
        DATA["Travel & Hospitality Data<br/>.pdf/.jpg/.png/.tiff<br/>Booking confirmations, cancellation notices<br/>Facility inspection photos"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC execution<br/>• Reservation docs + inspection image detection<br/>• Manifest generation"]
        RE["2️⃣ Reservation Extractor Lambda<br/>• Textract AnalyzeDocument (Cross-Region us-east-1)<br/>• Language detection → Textract hints<br/>• Comprehend entity extraction<br/>(guest name, dates, room type, amount)"]
        FI["3️⃣ Facility Inspector Lambda<br/>• Rekognition DetectLabels<br/>(damage detection, cleanliness 0–100)<br/>• Bedrock maintenance recommendations"]
        RL["4️⃣ Report Lambda<br/>• Facility condition trend report<br/>• Reservation processing summary<br/>• JSON + human-readable output"]
    end

    subgraph OUTPUT["📤 Output"]
        RESOUT["reservation-summary.json"]
        FACOUT["facility-condition.json"]
    end

    DATA --> ALIAS --> DISC
    DISC --> RE
    DISC --> FI
    RE --> RL
    FI --> RL
    RL --> RESOUT
    RL --> FACOUT
```

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for ONTAP | Storage for reservation documents and inspection images |
| S3 Access Points | Serverless access to ONTAP volumes |
| Amazon Textract | Document analysis (Cross-Region us-east-1) |
| Amazon Comprehend | Entity extraction and language detection |
| Amazon Rekognition | Facility condition image analysis |
| Amazon Bedrock | Maintenance recommendation generation |
| Step Functions | Workflow orchestration |
| EventBridge Scheduler | Daily trigger |

## Key Design Decisions

1. **Parallel processing** — Reservation extraction and facility inspection run independently
2. **Cross-Region Textract** — Uses us-east-1 for full Textract feature availability
3. **Multilingual auto-detection** — Comprehend detects language, selects appropriate models
4. **Cleanliness scoring** — Rekognition labels interpreted by Bedrock into 0–100 score
5. **Error isolation** — Individual document failures don't stop the batch
