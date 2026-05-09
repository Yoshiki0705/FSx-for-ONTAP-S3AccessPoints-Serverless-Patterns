# UC11: Retail / E-Commerce — Product Image Auto-Tagging & Catalog Metadata Generation

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["Product images<br/>.jpg/.jpeg/.png/.webp"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(30 minutes)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Runs inside VPC<br/>• S3 AP file discovery<br/>• .jpg/.jpeg/.png/.webp filter<br/>• Manifest generation"]
        IT["2️⃣ Image Tagging Lambda<br/>• Retrieves images via S3 AP<br/>• Rekognition DetectLabels<br/>• Category, color, material labels<br/>• Confidence score evaluation<br/>• Manual review flag setting"]
        QC["3️⃣ Quality Check Lambda<br/>• Image metadata analysis<br/>• Resolution check (min 800x800)<br/>• File size validation<br/>• Aspect ratio check<br/>• Quality fail flag setting"]
        CM["4️⃣ Catalog Metadata Lambda<br/>• Bedrock InvokeModel<br/>• Tags + quality info as input<br/>• Structured metadata generation<br/>• Product description generation<br/>• product_category, color, material"]
        SP["5️⃣ Stream Producer/Consumer Lambda<br/>• Kinesis PutRecord<br/>• Real-time integration<br/>• Downstream system notification<br/>• SNS notification"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket + Kinesis"]
        TAGOUT["image-tags/*.json<br/>Image tag results"]
        QCOUT["quality-check/*.json<br/>Quality check results"]
        CATOUT["catalog-metadata/*.json<br/>Catalog metadata"]
        KINESIS["Kinesis Data Stream<br/>Real-time integration"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(processing completion notification)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> IT
    IT --> QC
    QC --> CM
    CM --> SP
    IT --> TAGOUT
    QC --> QCOUT
    CM --> CATOUT
    SP --> KINESIS
    SP --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .jpg/.jpeg/.png/.webp (product images) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | Full image retrieval (required for Rekognition / quality check) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | Discover product images via S3 AP, generate manifest |
| Image Tagging | Lambda + Rekognition | DetectLabels for label detection (category, color, material), confidence threshold evaluation |
| Quality Check | Lambda | Image quality metrics validation (resolution, file size, aspect ratio) |
| Catalog Metadata | Lambda + Bedrock | Structured catalog metadata generation (product_category, color, material, product description) |
| Stream Producer/Consumer | Lambda + Kinesis | Real-time integration, data delivery to downstream systems |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Image Tags | `image-tags/YYYY/MM/DD/{sku}_{view}_tags.json` | Rekognition label detection results (with confidence scores) |
| Quality Check | `quality-check/YYYY/MM/DD/{sku}_{view}_quality.json` | Quality check results (resolution, size, aspect ratio, pass/fail) |
| Catalog Metadata | `catalog-metadata/YYYY/MM/DD/{sku}_metadata.json` | Structured metadata (product_category, color, material, description) |
| Kinesis Stream | `retail-catalog-stream` | Real-time integration records (for downstream PIM/EC systems) |
| SNS Notification | Email | Processing completion notification & quality alerts |

---

## Key Design Decisions

1. **Rekognition auto-tagging** — DetectLabels for automatic category/color/material detection. Manual review flag set when confidence below threshold (default: 70%)
2. **Image quality gate** — Resolution (min 800x800), file size, and aspect ratio validation for automatic e-commerce listing standards check
3. **Bedrock for metadata generation** — Tags + quality info as input to auto-generate structured catalog metadata and product descriptions
4. **Kinesis real-time integration** — PutRecord to Kinesis Data Streams after processing for real-time integration with downstream PIM/EC systems
5. **Sequential pipeline** — Step Functions manages order dependencies: tagging → quality check → metadata generation → stream delivery
6. **Polling (not event-driven)** — S3 AP does not support event notifications; 30-minute interval for rapid new product processing

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | Product image storage |
| S3 Access Points | Serverless access to ONTAP volumes |
| EventBridge Scheduler | Periodic trigger (30-minute interval) |
| Step Functions | Workflow orchestration (sequential) |
| Lambda | Compute (Discovery, Image Tagging, Quality Check, Catalog Metadata, Stream Producer/Consumer) |
| Amazon Rekognition | Product image label detection (DetectLabels) |
| Amazon Bedrock | Catalog metadata & product description generation (Claude / Nova) |
| Kinesis Data Streams | Real-time integration (for downstream PIM/EC systems) |
| SNS | Processing completion notification & quality alerts |
| Secrets Manager | ONTAP REST API credential management |
| CloudWatch + X-Ray | Observability |
