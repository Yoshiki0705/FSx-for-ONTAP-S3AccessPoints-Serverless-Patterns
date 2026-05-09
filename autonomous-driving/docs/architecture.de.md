# UC9: Autonomes Fahren / ADAS — Video- und LiDAR-Vorverarbeitung, Qualitätsprüfung und Annotation

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Übergeordneter Ablauf

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/driving_data/                                                          │
│  ├── rosbag/drive_20240315_001.bag       (ROS bag video+LiDAR)               │
│  ├── lidar/scan_20240315_001.pcd         (LiDAR point cloud)                 │
│  ├── camera/front_20240315_001.mp4       (Dashcam video)                     │
│  └── camera/rear_20240315_001.h264       (Rear camera video)                 │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-driving-vol-ext-s3alias                                         │
│  • ListObjectsV2 (video/LiDAR data discovery)                                │
│  • GetObject (BAG/PCD/MP4/H264 retrieval)                                    │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Discovery  │─▶│Frame Extract │─▶│Point Cloud QC│─▶│Annotation Manager│   │
│  │ Lambda     │  │ Lambda       │  │ Lambda       │  │ Lambda           │   │
│  │           │  │             │  │             │  │                 │   │
│  │ • VPC内    │  │ • Key frame │  │ • Point     │  │ • Bedrock       │   │
│  │ • S3 AP   │  │   extraction│  │   density   │  │   suggestions   │   │
│  │ • BAG/PCD │  │ • Rekognition│  │ • Coordinate│  │ • SageMaker     │   │
│  │   /MP4    │  │   detection │  │   integrity │  │   inference     │   │
│  └───────────┘  └──────────────┘  │ • NaN check │  │ • COCO JSON     │   │
│                                    └──────────────┘  └──────────────────┘   │
│                                                          │                   │
│                                                          ▼                   │
│                                                 ┌────────────────┐          │
│                                                 │SageMaker Invoke │          │
│                                                 │ Lambda          │          │
│                                                 │                │          │
│                                                 │ • Batch Transform│         │
│                                                 │ • Point cloud   │          │
│                                                 │   segmentation  │          │
│                                                 └────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── frames/YYYY/MM/DD/                                                      │
│  │   └── drive_001_frame_0001.jpg    ← Extracted key frames                 │
│  ├── qc-reports/YYYY/MM/DD/                                                  │
│  │   └── scan_001_qc.json           ← Point cloud quality report            │
│  ├── annotations/YYYY/MM/DD/                                                 │
│  │   └── drive_001_coco.json        ← COCO format annotations              │
│  └── inference/YYYY/MM/DD/                                                   │
│      └── scan_001_segmentation.json  ← Segmentation results                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid-Diagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DATA["Video- / LiDAR-Daten<br/>.bag, .pcd, .mp4, .h264"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• .bag/.pcd/.mp4/.h264 Filter<br/>• Manifest-Generierung"]
        FE["2️⃣ Frame Extraction Lambda<br/>• Schlüsselbilder aus Video extrahieren<br/>• Rekognition DetectLabels<br/>  (Fahrzeuge, Fußgänger, Verkehrszeichen)<br/>• Frame-Bilder S3-Ausgabe"]
        PC["3️⃣ Point Cloud QC Lambda<br/>• LiDAR-Punktwolke abrufen<br/>• Qualitätsprüfungen<br/>  (Punktdichte, Koordinatenintegrität, NaN-Validierung)<br/>• QC-Bericht-Generierung"]
        AM["4️⃣ Annotation Manager Lambda<br/>• Bedrock Annotationsvorschläge<br/>• COCO-kompatible JSON-Generierung<br/>• Annotationsaufgaben-Verwaltung"]
        SM["5️⃣ SageMaker Invoke Lambda<br/>• Batch Transform Ausführung<br/>• Punktwolken-Segmentierungsinferenz<br/>• Objekterkennungsergebnis-Ausgabe"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        FRAMES["frames/*.jpg<br/>Extrahierte Schlüsselbilder"]
        QCR["qc-reports/*.json<br/>Punktwolken-Qualitätsberichte"]
        ANNOT["annotations/*.json<br/>COCO-Annotationen"]
        INFER["inference/*.json<br/>ML-Inferenzergebnisse"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Verarbeitungsabschluss-Benachrichtigung"]
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

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .bag, .pcd, .mp4, .h264 (ROS bag, LiDAR-Punktwolke, Dashcam-Video) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger Dateiabruf (erforderlich für Frame-Extraktion und Punktwolkenanalyse) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Discovery | Lambda (VPC) | Video-/LiDAR-Daten über S3 AP erkennen, Manifest generieren |
| Frame Extraction | Lambda + Rekognition | Schlüsselbilder aus Video extrahieren, Objekterkennung |
| Point Cloud QC | Lambda | LiDAR-Punktwolken-Qualitätsprüfungen (Punktdichte, Koordinatenintegrität, NaN-Validierung) |
| Annotation Manager | Lambda + Bedrock | Annotationsvorschläge generieren, COCO JSON-Ausgabe |
| SageMaker Invoke | Lambda + SageMaker | Batch Transform für Punktwolken-Segmentierungsinferenz |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| Schlüsselbilder | `frames/YYYY/MM/DD/{stem}_frame_{n}.jpg` | Extrahierte Schlüsselbilder |
| QC-Bericht | `qc-reports/YYYY/MM/DD/{stem}_qc.json` | Punktwolken-Qualitätsprüfungsergebnisse |
| Annotationen | `annotations/YYYY/MM/DD/{stem}_coco.json` | COCO-kompatible Annotationen |
| Inferenz | `inference/YYYY/MM/DD/{stem}_segmentation.json` | ML-Inferenzergebnisse |
| SNS-Benachrichtigung | E-Mail | Verarbeitungsabschluss-Benachrichtigung (Anzahl und Qualitätswerte) |

---

## Wichtige Designentscheidungen

1. **S3 AP statt NFS** — Kein NFS-Mount von Lambda erforderlich; große Daten werden über die S3-API abgerufen
2. **Parallele Verarbeitung** — Frame Extraction und Point Cloud QC laufen parallel zur Reduzierung der Verarbeitungszeit
3. **Rekognition + SageMaker zweistufig** — Rekognition für sofortige Objekterkennung, SageMaker für hochpräzise Segmentierung
4. **COCO-kompatibles Format** — Branchenstandard-Annotationsformat gewährleistet Kompatibilität mit nachgelagerten ML-Pipelines
5. **Qualitäts-Gate** — Point Cloud QC filtert Daten, die Qualitätsstandards nicht erfüllen, frühzeitig in der Pipeline
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Speicherung autonomer Fahrdaten (Video und LiDAR) |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Compute (Discovery, Frame Extraction, Point Cloud QC, Annotation Manager, SageMaker Invoke) |
| Amazon Rekognition | Objekterkennung (Fahrzeuge, Fußgänger, Verkehrszeichen) |
| Amazon SageMaker | Batch Transform (Punktwolken-Segmentierungsinferenz) |
| Amazon Bedrock | Generierung von Annotationsvorschlägen |
| SNS | Verarbeitungsabschluss-Benachrichtigung |
| Secrets Manager | ONTAP REST API Anmeldedatenverwaltung |
| CloudWatch + X-Ray | Observability |
