# UC15: 國防 / 太空 — 衛星影像分析管線

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文件**: [架構](docs/architecture.zh-TW.md) | [示範腳本](docs/demo-guide.zh-TW.md) | [疑難排解](../docs/phase7-troubleshooting.md)

## 概述

運用 Amazon FSx for NetApp ONTAP S3 Access Points 的衛星影像（SAR / 光學）
自動分析管線。將大容量衛星影像資料儲存於 FSx for ONTAP，
並透過 S3 Access Points 執行無伺服器處理。

## 使用案例

國防·情報機關以及太空相關組織自動處理·分析從衛星取得的
地球觀測資料（Earth Observation）。

### 處理流程

```
FSx for ONTAP (衛星影像儲存)
  → S3 Access Point
    → Step Functions 工作流程
      → Discovery: 偵測新影像 (GeoTIFF, NITF, HDF5)
      → Tiling: 將大型影像分割為圖磚 (Cloud Optimized GeoTIFF 轉換)
      → ObjectDetection: 使用 Rekognition / SageMaker 進行物體偵測
      → ChangeDetection: 透過時間序列比較進行變化偵測
      → GeoEnrichment: 附加中繼資料 (座標、拍攝時間、解析度)
      → AlertGeneration: 偵測到異常時產生警報
```

### 目標資料

| 資料格式 | 說明 | 典型大小 |
|-----------|------|-----------|
| GeoTIFF | 光學衛星影像 | 100 MB – 10 GB |
| NITF | 軍事標準影像格式 | 500 MB – 50 GB |
| HDF5 | SAR 資料 (Sentinel-1 等) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | 已圖磚化影像 | 10 – 500 MB |

### AWS 服務

| 服務 | 用途 |
|---------|------|
| FSx for ONTAP | 衛星影像的持久性儲存 (透過 NTFS ACL 進行存取控制) |
| S3 Access Points | 從無伺服器存取影像 |
| Step Functions | 工作流程協調 |
| Lambda | 圖磚分割、中繼資料擷取、警報產生 |
| SageMaker (Batch Transform) | 物體偵測·變化偵測 ML 推論 |
| Amazon Rekognition | 標籤偵測 (車輛、建築、船舶) |
| Amazon Bedrock | 影像標題產生、報告摘要 |
| DynamoDB | 處理狀態管理、偵測結果索引 |
| SNS | 警報通知 |
| CloudWatch | 可觀測性 |

### Public Sector 適配性

- **DoD CC SRG**: FSx for ONTAP 已通過 Impact Level 2/4/5 認證 (GovCloud)
- **CSfC**: NetApp ONTAP 已通過 Commercial Solutions for Classified 認證
- **FedRAMP**: 在 AWS GovCloud 中符合 FedRAMP High
- **資料主權**: 資料在區域內完結 (ap-northeast-1 / us-gov-west-1)

## 已驗證的畫面（螢幕截圖）

以 2026-05-10 在 ap-northeast-1 實際確認運作時**一般職員日常操作的 UI**
為中心進行展示。面向技術人員的主控台畫面（Step Functions 圖形等）請參見
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md)。

### 1. 衛星影像儲存（透過 FSx for ONTAP / S3 Access Point）

從檔案伺服器管理員角度看到的、待分析衛星影像的放置確認畫面。
只需在 `satellite/YYYY/MM/` 前綴下放置新影像，
定期的 Step Functions 工作流程就會自動拾取。

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     內容: 透過 S3 AP 列表顯示 satellite/2026/05/*.tif (物件名、大小、更新時間)
     遮罩: 帳戶 ID、Access Point ARN、真實衛星影像名 -->
![UC15: 衛星影像放置](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. 分析結果檢視（S3 輸出儲存貯體）

偵測結果（`detections/*.json`）、地理中繼資料（`enriched/*.json`）、
圖磚資訊（`tiles/*/metadata.json`）經整理後儲存。

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     內容: 在 S3 主控台俯瞰 detections/、enriched/、tiles/ 三個前綴
     遮罩: 帳戶 ID、儲存貯體名前綴 -->
![UC15: S3 輸出儲存貯體](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. 變化偵測警報（SNS 電子郵件通知）

一般職員（維運負責人）接收的 SNS 警報郵件。
當變化面積超過門檻（預設 1 km²）時自動傳送。

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     內容: 在郵件用戶端 (Gmail/Outlook) 顯示 alert_type=SATELLITE_CHANGE_DETECTED
     遮罩: 收件人郵件地址、寄件人地址、真實座標、tile_id -->
![UC15: SNS 警報通知郵件](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. 偵測結果 JSON 的內容

偵測結果（標籤、信賴度、bbox）的清晰 JSON 檢視器。

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     內容: 在 S3 主控台預覽物件，detections JSON 的內容
     遮罩: 帳戶 ID -->
![UC15: 偵測結果 JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
透過衛星影像分析（物體偵測·變化偵測·警報）的自動化，實現情報分析的提速。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 已處理影像數 / 執行 | > 50 images |
| 物體偵測精度 | > 80% |
| 變化偵測成功率 | > 85% |
| 警報產生時間 | < 5 分鐘 |
| 成本 / 執行 | < $15 |
| Human Review 必要率 | 100%（警報發出前必須人工核准） |

> **100% Human Review 的理由**: 由於警報誤報·漏報的業務影響極大，因此要求對全部項目進行人工核准。

### Measurement Method
Step Functions 執行歷史、Rekognition 偵測結果、Bedrock 分析報告、SNS 通知日誌、CloudWatch Metrics。核准記錄儲存於 DynamoDB，以便稽核時可追蹤「誰·何時·核准了什麼」。

## 部署

### 事前驗證

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一鍵部署

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### 手動部署

```bash
# 前提: 需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**重要**: `S3AccessPointName` 是為 S3 AP 授予 IAM 權限所必需的。
詳情請參見 [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md)。

## 目錄結構

```
defense-satellite/
├── template.yaml              # SAM 範本 (開發用)
├── template-deploy.yaml       # CloudFormation 範本 (部署用)
├── functions/
│   ├── discovery/handler.py   # 新衛星影像偵測
│   ├── tiling/handler.py      # 圖磚分割 + COG 轉換
│   ├── object_detection/handler.py  # 物體偵測 (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # 時間序列變化偵測
│   ├── geo_enrichment/handler.py    # 地理中繼資料附加
│   └── alert_generation/handler.py  # 警報產生
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## AWS 文件連結

| 服務 | 文件 |
|---------|------------|
| FSx for ONTAP | [使用者指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [開發者指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [開發者指南](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [開發者指南](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [使用者指南](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Well-Architected Framework 對應

| 支柱 | 對應 |
|----|------|
| 卓越營運 | X-Ray、EMF、警報產生、100% Human Review |
| 安全性 | DoD CC SRG、FedRAMP、最小權限 IAM、KMS、VPC 隔離 |
| 可靠性 | Step Functions Retry/Catch、resilience 測試、回退 |
| 效能效率 | COG 圖磚化、並行物體偵測、SageMaker Batch |
| 成本最佳化 | 無伺服器、SageMaker 競價、圖磚單位處理 |
| 永續性 | 隨需執行、差分變化偵測 |





---

## 成本估算（每月概算）

> **注意**: 以下為 ap-northeast-1 區域的概算，實際成本因使用量而異。最新價格請在 [AWS Pricing Calculator](https://calculator.aws/) 確認。

### 無伺服器元件（按量計費）

| 服務 | 單價 | 假定使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 函數 × 10 scenes/天 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/天 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/天 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/執行 | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/查詢 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/天 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### 固定成本（FSx for ONTAP — 以現有環境為前提）

| 元件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共用現有環境) |
| S3 Access Point | 無額外費用 (僅 S3 API 費用) |

### 合計概算

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每日 1 次執行） | ~$5-15 |
| 標準組態（每小時執行） | ~$15-50 |
| 大規模組態（高頻 + 警報） | ~$50-150 |

> **Governance Caveat**: 成本估算為概算，並非保證值。實際帳單金額因使用模式、資料量、區域而異。

---

## 本地測試

### Prerequisites 檢查

```bash
# 確認前提條件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 認證資訊
```

### sam local invoke

```bash
# 建置
# 前提: 需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

# 本地執行 Discovery Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 帶環境變數覆寫
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 單元測試

```bash
python3 -m pytest tests/ -v
```

詳情請參見 [本地測試快速入門](../docs/local-testing-quick-start.md)。

---

## 輸出範例 (Output Sample)

衛星影像分析管線的輸出範例 (Human Review 必需):

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **注意**: 以上為範例輸出，實際值因環境·輸入資料而異。基準數值為 sizing reference，並非 service limit。

---

## Governance Note

> 本模式提供技術架構指導。它並非法律·合規·監管建議。組織應諮詢合格的專業人士。

---

## S3AP Compatibility

關於 S3 Access Points for FSx for ONTAP 的相容性限制、疑難排解和觸發模式，請參見 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
