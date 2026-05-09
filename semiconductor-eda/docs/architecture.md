# UC6: Semiconductor / EDA — Design File Validation

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram (for slides / documentation)

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
        DISC["1️⃣ Discovery Lambda<br/>• VPC内実行<br/>• S3 AP ファイル検出<br/>• .gds/.gds2/.oas/.oasis フィルタ"]
        MAP["2️⃣ Map: Metadata Extraction<br/>• 並列実行 (max 10)<br/>• Range GET (64KB header)<br/>• GDSII/OASIS バイナリパース<br/>• library_name, cell_count,<br/>  bounding_box, units 抽出"]
        DRC["3️⃣ DRC Aggregation<br/>• Glue Data Catalog 更新<br/>• Athena SQL クエリ実行<br/>• cell_count 分布 (min/max/avg/P95)<br/>• bounding_box 外れ値 (IQR法)<br/>• 命名規則違反検出"]
        RPT["4️⃣ Report Generation<br/>• Amazon Bedrock (Nova/Claude)<br/>• 設計レビューサマリー生成<br/>• リスク評価 (High/Medium/Low)<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        META["metadata/*.json<br/>設計ファイルメタデータ"]
        ATHENA["athena-results/*.csv<br/>DRC 統計集計結果"]
        REPORT["reports/*.md<br/>AI 設計レビューレポート"]
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
