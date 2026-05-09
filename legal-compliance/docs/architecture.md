# UC1: 法務・コンプライアンス — ファイルサーバー監査・データガバナンス

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        FILES["ファイルサーバーデータ<br/>NTFS ACL 付きファイル群"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / ONTAP REST API"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(24 hours)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC内実行<br/>• S3 AP ファイル一覧取得<br/>• ONTAP メタデータ収集<br/>• セキュリティスタイル確認"]
        ACL["2️⃣ ACL Collection Lambda<br/>• ONTAP REST API 呼び出し<br/>• file-security エンドポイント<br/>• NTFS ACL / CIFS 共有 ACL 取得<br/>• JSON Lines 形式で S3 出力"]
        ATH["3️⃣ Athena Analysis Lambda<br/>• Glue Data Catalog 更新<br/>• Athena SQL クエリ実行<br/>• 過剰権限共有の検出<br/>• 陳腐化アクセスの検出<br/>• ポリシー違反の検出"]
        RPT["4️⃣ Report Generation Lambda<br/>• Amazon Bedrock (Nova/Claude)<br/>• コンプライアンスレポート生成<br/>• リスク評価・改善提案<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        ACLDATA["acl-data/*.jsonl<br/>ACL 情報 (日付パーティション)"]
        ATHENA["athena-results/*.csv<br/>違反検出結果"]
        REPORT["reports/*.md<br/>AI コンプライアンスレポート"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    FILES --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> ACL
    ACL --> ATH
    ATH --> RPT
    ACL --> ACLDATA
    ATH --> ATHENA
    RPT --> REPORT
    RPT --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | 全ファイル（NTFS ACL 付き） |
| **Access Method** | S3 Access Point (ファイル一覧) + ONTAP REST API (ACL 情報) |
| **Read Strategy** | メタデータのみ取得（ファイル本体は読まない） |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | S3 AP でファイル一覧取得、ONTAP メタデータ収集 |
| ACL Collection | Lambda (VPC) | ONTAP REST API で NTFS ACL / CIFS 共有 ACL 取得 |
| Athena Analysis | Lambda + Glue + Athena | SQL で過剰権限・陳腐化アクセス・ポリシー違反検出 |
| Report Generation | Lambda + Bedrock | 自然言語コンプライアンスレポート生成 |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| ACL Data | `acl-data/YYYY/MM/DD/*.jsonl` | ファイル別 ACL 情報 (JSON Lines) |
| Athena Results | `athena-results/{id}.csv` | 違反検出結果（過剰権限、孤立ファイル等） |
| Compliance Report | `reports/YYYY/MM/DD/compliance-report-{id}.md` | Bedrock 生成レポート |
| SNS Notification | Email | 監査結果サマリーとレポート格納先 |

---

## Key Design Decisions

1. **S3 AP + ONTAP REST API の併用** — S3 AP でファイル一覧を取得し、ONTAP REST API で ACL 詳細を取得する二段構成
2. **ファイル本体を読まない** — 監査目的のためメタデータ・権限情報のみ収集し、データ転送コストを最小化
3. **JSON Lines + 日付パーティション** — Athena でのクエリ効率化と履歴追跡を両立
4. **Athena SQL による違反検出** — 柔軟なルールベース分析（Everyone 権限、90日未アクセス等）
5. **Bedrock による自然言語レポート** — 非技術者（法務・コンプライアンス担当）向けの可読性確保
6. **ポーリングベース** — S3 AP はイベント通知非対応のため、定期スケジュール実行

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | エンタープライズファイルストレージ（NTFS ACL 付き） |
| S3 Access Points | ONTAP ボリュームへのサーバーレスアクセス |
| EventBridge Scheduler | 定期トリガー（日次監査） |
| Step Functions | ワークフローオーケストレーション |
| Lambda | コンピュート（Discovery, ACL Collection, Analysis, Report） |
| Glue Data Catalog | Athena 用スキーマ管理 |
| Amazon Athena | SQL ベースの権限分析・違反検出 |
| Amazon Bedrock | AI コンプライアンスレポート生成 (Nova / Claude) |
| SNS | 監査結果通知 |
| Secrets Manager | ONTAP REST API 認証情報管理 |
| CloudWatch + X-Ray | オブザーバビリティ |
