# UC9: Autonomous Driving / ADAS — Video & LiDAR Preprocessing, Quality Check & Annotation

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["Video / LiDAR data<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Runs inside VPC<br/>• S3 AP file discovery<br/>• .bag/.pcd/.mp4/.h264 filter<br/>• Manifest generation"]
        FE["2️⃣ Frame Extraction Lambda<br/>• Key frame extraction from video<br/>• Rekognition DetectLabels<br/>  (vehicles, pedestrians, traffic signs)<br/>• Frame image S3 output"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR point cloud retrieval<br/>• Quality checks<br/>  (point density, coordinate integrity, NaN validation)<br/>• QC report generation"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock annotation suggestions<br/>• COCO-compatible JSON generation<br/>• Annotation job management"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform execution<br/>• Point cloud segmentation inference<br/>• Object detection result output"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>Extracted key frames"]
        QCR["qc-reports/*.json<br/>Point cloud quality reports"]
        ANNOT["annotations/*.json<br/>COCO annotations"]
        INFER["inference/*.json<br/>ML inference results"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Processing completion notification"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> FE
    DISC --> PC
    FE --> AM
    PC --> AM
    AM --> SM
    FE --> FRAMES
    PC --> QCR
    AM --> ANNOT
    SM --> INFER
    SM --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .bag, .pcd, .mp4, .h264 (ROS bag, LiDAR point cloud, dashcam video) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | Full file retrieval (required for frame extraction & point cloud analysis) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | Discover video/LiDAR data via S3 AP, generate manifest |
| Frame Extraction | Lambda + Rekognition | Extract key frames from video, object detection |
| Point Cloud QC | Lambda | LiDAR point cloud quality checks (point density, coordinate integrity, NaN validation) |
| Annotation Manager | Lambda + Bedrock | Generate annotation suggestions, COCO JSON output |
| SageMaker Invoke | Lambda + SageMaker | Batch Transform for point cloud segmentation inference |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Key Frames | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | Extracted key frame images |
| QC Report | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | Point cloud quality check results |
| Annotations | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO-compatible annotations |
| Inference | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML inference results |
| SNS Notification | Email | Processing completion notification (count & quality scores) |

---

## Key Design Decisions

1. **S3 AP over NFS** — No NFS mount needed from Lambda; large data retrieved via S3 API
2. **Parallel processing** — Frame Extraction and Point Cloud QC run in parallel to reduce processing time
3. **Rekognition + SageMaker two-stage** — Rekognition for immediate object detection, SageMaker for high-accuracy segmentation
4. **COCO-compatible format** — Industry-standard annotation format ensures compatibility with downstream ML pipelines
5. **Quality gate** — Point Cloud QC filters out data not meeting quality standards early in the pipeline
6. **Polling (not event-driven)** — S3 AP does not support event notifications, so periodic scheduled execution is used

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | Autonomous driving data storage (video & LiDAR) |
| S3 Access Points | Serverless access to ONTAP volumes |
| EventBridge Scheduler | Periodic trigger |
| Step Functions | Workflow orchestration |
| Lambda | Compute (Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke) |
| Amazon Rekognition | Object detection (vehicles, pedestrians, traffic signs) |
| Amazon SageMaker | Batch Transform (point cloud segmentation inference) |
| Amazon Bedrock | Annotation suggestion generation |
| SNS | Processing completion notification |
| Secrets Manager | ONTAP REST API credential management |
| CloudWatch + X-Ray | Observability |
