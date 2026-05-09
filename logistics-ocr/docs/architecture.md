# UC12: 物流 / サプライチェーン — 配送伝票 OCR・倉庫在庫画像分析

🌐 **Language / 言語**: 日本語 | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["物流データ<br/>.jpg/.jpeg/.png/.tiff/.pdf (配送伝票)<br/>.jpg/.jpeg/.png (倉庫在庫写真)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC内実行<br/>• S3 AP ファイル検出<br/>• 伝票/在庫を種別分離<br/>• Manifest 生成"]
        OCR["2️⃣ OCR Lambda<br/>• S3 AP 経由で伝票取得<br/>• Textract (us-east-1 クロスリージョン)<br/>• テキスト・フォーム抽出<br/>• 低信頼度フラグ設定"]
        DS["3️⃣ Data Structuring Lambda<br/>• Bedrock InvokeModel<br/>• 抽出フィールド正規化<br/>• 送り先・品名・数量・追跡番号<br/>• 構造化配送レコード生成"]
        IA["4️⃣ Inventory Analysis Lambda<br/>• S3 AP 経由で在庫写真取得<br/>• Rekognition DetectLabels<br/>• 物体検出・カウント<br/>• パレット・箱・棚占有率"]
        RPT["5️⃣ Report Lambda<br/>• Bedrock InvokeModel<br/>• 配送データ + 在庫データ統合<br/>• 配送ルート最適化レポート生成<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        OCROUT["ocr-results/*.json<br/>OCR テキスト抽出結果"]
        STROUT["structured-records/*.json<br/>構造化配送レコード"]
        INVOUT["inventory-analysis/*.json<br/>在庫分析結果"]
        REPORT["reports/*.md<br/>最適化レポート"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(レポート完了通知)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    DISC --> IA
    OCR --> DS
    DS --> RPT
    IA --> RPT
    OCR --> OCROUT
    DS --> STROUT
    IA --> INVOUT
    RPT --> REPORT
    RPT --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .jpg/.jpeg/.png/.tiff/.pdf (配送伝票), .jpg/.jpeg/.png (倉庫在庫写真) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 画像・PDF 全体を取得 (Textract / Rekognition に必要) |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | S3 AP で伝票画像・在庫写真検出、種別ごとに Manifest 生成 |
| OCR | Lambda + Textract | 配送伝票のテキスト・フォーム抽出 (送り主、受取人、追跡番号、品目) |
| Data Structuring | Lambda + Bedrock | 抽出フィールドの正規化、構造化配送レコード生成 (送り先、品名、数量等) |
| Inventory Analysis | Lambda + Rekognition | 倉庫在庫画像の物体検出・カウント (パレット、箱、棚占有率) |
| Report | Lambda + Bedrock | 配送データ + 在庫データを統合した最適化レポート生成 |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| OCR Results | `ocr-results/YYYY/MM/DD/{slip}_ocr.json` | Textract テキスト抽出結果 (信頼度スコア付き) |
| Structured Records | `structured-records/YYYY/MM/DD/{slip}_record.json` | 構造化配送レコード (送り先、品名、数量、追跡番号) |
| Inventory Analysis | `inventory-analysis/YYYY/MM/DD/{warehouse}_{shelf}.json` | 在庫分析結果 (物体カウント、棚占有率) |
| Logistics Report | `reports/YYYY/MM/DD/logistics_report.md` | Bedrock 生成配送ルート最適化レポート |
| SNS Notification | Email | レポート完了通知 |

---

## Key Design Decisions

1. **並列処理 (OCR + Inventory Analysis)** — 配送伝票 OCR と倉庫在庫分析は独立して実行可能。Step Functions の Parallel State で並列化
2. **Textract クロスリージョン** — Textract は us-east-1 でのみ利用可能なため、クロスリージョン呼び出しで対応
3. **Bedrock によるフィールド正規化** — OCR 結果の非構造化テキストを Bedrock で正規化し、構造化配送レコードを生成
4. **Rekognition による在庫カウント** — DetectLabels で物体検出し、パレット・箱・棚占有率を自動算出
5. **低信頼度フラグ管理** — Textract の信頼度スコアが閾値未満の場合、手動検証フラグを設定
6. **ポーリングベース** — S3 AP はイベント通知非対応のため、定期スケジュール実行

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | 配送伝票・倉庫在庫画像ストレージ |
| S3 Access Points | ONTAP ボリュームへのサーバーレスアクセス |
| EventBridge Scheduler | 定期トリガー |
| Step Functions | ワークフローオーケストレーション (並列パス対応) |
| Lambda | コンピュート (Discovery, OCR, Data Structuring, Inventory Analysis, Report) |
| Amazon Textract | 配送伝票 OCR テキスト・フォーム抽出 (us-east-1 クロスリージョン) |
| Amazon Rekognition | 倉庫在庫画像の物体検出・カウント (DetectLabels) |
| Amazon Bedrock | フィールド正規化・最適化レポート生成 (Claude / Nova) |
| SNS | レポート完了通知 |
| Secrets Manager | ONTAP REST API 認証情報管理 |
| CloudWatch + X-Ray | オブザーバビリティ |
