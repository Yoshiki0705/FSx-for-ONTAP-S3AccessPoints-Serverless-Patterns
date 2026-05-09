# UC6: Semiconductor / EDA — Design File Validation

🌐 **Language / 言語**: [日本語](architecture.md) | English | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/eda_designs/                                                           │
│  ├── top_chip_v3.gds        (GDSII format, multi-GB)                        │
│  ├── block_a_io.gds2        (GDSII format)                                  │
│  ├── memory_ctrl.oasis      (OASIS format)                                  │
│  └── analog_frontend.oas    (OASIS format)                                  │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-eda-vol-ext-s3alias                                             │
│  • ListObjectsV2 (file discovery)                                            │
│  • GetObject with Range header (64KB header read)                            │
│  • No NFS mount required from Lambda                                         │
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
│  ┌─────────────┐    ┌──────────────────────┐    ┌────────────────┐          │
│  │  Discovery   │───▶│  Map State           │───▶│ DRC Aggregation│          │
│  │  Lambda      │    │  (MetadataExtraction)│    │ Lambda         │          │
│  │             │    │  MaxConcurrency: 10  │    │               │          │
│  │  • VPC内     │    │  • Retry 3x          │    │  • Athena SQL  │          │
│  │  • S3 AP List│    │  • Catch → MarkFailed│    │  • Glue Catalog│          │
│  │  • ONTAP API │    │  • Range GET 64KB    │    │  • IQR outliers│          │
│  └─────────────┘    └──────────────────────┘    └───────┬────────┘          │
│                                                          │                   │
│                                                          ▼                   │
│                                                 ┌────────────────┐          │
│                                                 │Report Generation│          │
│                                                 │ Lambda         │          │
│                                                 │               │          │
│                                                 │ • Bedrock      │          │
│                                                 │ • SNS notify   │          │
│                                                 └────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── metadata/YYYY/MM/DD/                                                    │
│  │   ├── top_chip_v3.json          ← Extracted metadata                     │
│  │   ├── block_a_io.json                                                     │
│  │   ├── memory_ctrl.json                                                    │
│  │   └── analog_frontend.json                                                │
│  ├── athena-results/                                                         │
│  │   └── {query-execution-id}.csv  ← DRC statistics                         │
│  └── reports/YYYY/MM/DD/                                                     │
│      └── eda-design-review-{id}.md ← Bedrock report                         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid Diagram (for slides / documentation)

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        GDS["GDS/OASIS Design Files<br/>.gds, .gds2, .oas, .oasis"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject (Range)"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Runs inside VPC<br/>• S3 AP file discovery<br/>• .gds/.gds2/.oas/.oasis filter"]
        MAP["2️⃣ Map: Metadata Extraction<br/>• Parallel execution (max 10)<br/>• Range GET (64KB header)<br/>• GDSII/OASIS binary parsing<br/>• Extracts library_name, cell_count,<br/>  bounding_box, units"]
        DRC["3️⃣ DRC Aggregation<br/>• Updates Glue Data Catalog<br/>• Executes Athena SQL queries<br/>• cell_count distribution (min/max/avg/P95)<br/>• bounding_box outliers (IQR method)<br/>• Naming convention violation detection"]
        RPT["4️⃣ Report Generation<br/>• Amazon Bedrock (Nova/Claude)<br/>• Generates design review summary<br/>• Risk assessment (High/Medium/Low)<br/>• SNS notification"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        META["metadata/*.json<br/>Design file metadata"]
        ATHENA["athena-results/*.csv<br/>DRC statistical aggregation results"]
        REPORT["reports/*.md<br/>AI design review report"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    GDS --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> MAP
    MAP --> DRC
    DRC --> RPT
    MAP --> META
    DRC --> ATHENA
    RPT --> REPORT
    RPT --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .gds, .gds2 (GDSII), .oas, .oasis (OASIS) |
| **Access Method** | S3 Access Point (no NFS mount) |
| **Read Strategy** | Range request — first 64KB only (header parsing) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | List design files via S3 AP |
| Metadata Extraction | Lambda (Map) | Parse GDSII/OASIS binary headers |
| DRC Aggregation | Lambda + Athena | SQL-based statistical analysis |
| Report Generation | Lambda + Bedrock | AI design review summary |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| Metadata JSON | `metadata/YYYY/MM/DD/{stem}.json` | Per-file extracted metadata |
| Athena Results | `athena-results/{id}.csv` | DRC statistics (cell distribution, outliers) |
| Design Review | `reports/YYYY/MM/DD/eda-design-review-{id}.md` | Bedrock-generated report |
| SNS Notification | Email | Summary with file counts and report location |

---

## Key Design Decisions

1. **S3 AP over NFS** — Lambda cannot mount NFS; S3 AP provides serverless-native access to ONTAP data
2. **Range requests** — GDS files can be multi-GB; only 64KB header needed for metadata
3. **Athena for analytics** — SQL-based DRC aggregation scales to millions of files
4. **IQR outlier detection** — Statistical method for bounding box anomaly detection
5. **Bedrock for reports** — Natural language summaries for non-technical stakeholders
6. **Polling (not event-driven)** — S3 AP does not support `GetBucketNotificationConfiguration`

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | Enterprise file storage (GDS/OASIS files) |
| S3 Access Points | Serverless data access to ONTAP volumes |
| EventBridge Scheduler | Periodic trigger |
| Step Functions | Workflow orchestration with Map state |
| Lambda | Compute (Discovery, Extraction, Aggregation, Report) |
| Glue Data Catalog | Schema management for Athena |
| Amazon Athena | SQL analytics on metadata |
| Amazon Bedrock | AI report generation (Nova Lite / Claude) |
| SNS | Notification |
| CloudWatch + X-Ray | Observability |
