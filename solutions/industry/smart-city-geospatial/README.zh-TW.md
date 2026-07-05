# UC17：智慧城市 — 地理空間資料分析·都市規劃

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文件**: [架構](docs/architecture.md) | [示範腳本](docs/demo-guide.md) | [疑難排解](../docs/phase7-troubleshooting.md)

## 概述

基於 FSx for ONTAP S3 Access Points 的地理空間資料（GIS）
自動分析管線。為都市規劃、基礎設施監控、災害應對而
整合處理衛星影像·LiDAR·IoT 感測器資料。

## 使用案例

地方政府·都市規劃機構整合來自多個來源的地理空間資料，
自動化都市基礎設施狀態監控、變化偵測與災害風險評估。

### 處理流程

```
FSx for ONTAP (GIS 資料儲存 — 依部門存取控制)
  → S3 Access Point
    → Step Functions 工作流程
      → Discovery：偵測新資料（GeoTIFF, Shapefile, GeoJSON, LAS）
      → Preprocessing：座標系轉換·正規化（EPSG 統一，EPSG:4326）
      → LandUseClassification：土地利用分類（ML 推論）
      → ChangeDetection：時間序列變化偵測（新建建物、綠地減少）
      → InfraAssessment：基礎設施劣化評估（道路、橋梁、LAS 點雲）
      → RiskMapping：災害風險地圖生成（洪水、地震、山崩）
      → ReportGeneration：都市規劃報告生成（Bedrock Nova Lite）
```

### 目標資料

| 資料格式 | 說明 | 典型大小 |
|-----------|------|-----------|
| GeoTIFF | 航空照片·衛星影像 | 100 MB – 10 GB |
| Shapefile (.shp) | 向量資料（道路、建物、地塊） | 1 – 500 MB |
| GeoJSON | 輕量向量資料 | 1 KB – 100 MB |
| LAS / LAZ | LiDAR 點雲（地形·建物 3D） | 100 MB – 5 GB |
| GeoPackage (.gpkg) | OGC 標準 GIS 資料庫 | 10 MB – 2 GB |

### AWS 服務

| 服務 | 用途 |
|---------|------|
| FSx for ONTAP | GIS 資料的持久化儲存（依部門 NTFS ACL） |
| S3 Access Points | 從無伺服器元件存取資料 |
| Step Functions | 工作流程編排 |
| Lambda | 前處理、座標轉換、中繼資料擷取 |
| SageMaker (Batch Transform) | 土地利用分類、變化偵測 ML 推論（選用） |
| Amazon Rekognition | 從航空照片進行物體偵測（建物、車輛） |
| Amazon Bedrock Nova Lite | 日文都市規劃報告生成 |
| DynamoDB | 時間序列土地利用歷史、變化偵測 |
| SNS | 異常偵測警示 |
| CloudWatch | 可觀測性 |

### Public Sector 適配性

- **INSPIRE 指令支援**（EU 地理空間資料基礎設施）
- **OGC 標準合規**：WMS, WFS, WCS, GeoPackage
- **開放資料**：處理結果可發布至面向市民的入口網站
- **災害應對**：即時受災狀況映射
- **資料主權**：自治體資料在區域內完成閉環

### 應用情境

| 情境 | 輸入資料 | 輸出 |
|---------|-----------|------|
| 都市綠化監控 | 衛星影像（時間序列） | 綠地面積變化報告 |
| 非法傾倒偵測 | 無人機影像 | 警示 + 位置資訊 |
| 道路劣化評估 | 車載攝影機影像 | 修復優先度地圖 |
| 洪水風險評估 | LiDAR + 降雨資料 | 淹水預測地圖 |
| 建築審查支援 | 航空照片 + 建築申請 | 差異偵測報告 |

## 已驗證的畫面（截圖）

### 1. GIS 資料儲存（透過 S3 Access Point）

從自治體 GIS 負責人視角看到的分析對象資料的配置確認畫面。
在 `gis/YYYY/MM/` 前綴下配置 GeoTIFF / Shapefile / LAS。

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     內容：S3 AP 的 gis/ 前綴清單，檔案格式混合
     遮罩：帳戶 ID、S3 AP ARN、源自真實座標的檔名 -->
![UC17：GIS 資料儲存確認](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Bedrock 生成的都市規劃報告（Markdown 顯示）

**UC17 的核心功能**：整合土地利用分布·變化偵測·風險評估，
由 Bedrock Nova Lite 面向自治體負責人自動生成日文報告。

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     內容：在 S3 主控台渲染顯示 reports/*.md
     實際樣本內容：
       ### 面向自治體負責人的所見報告
       #### 都市規劃上的關注點
       根據 GIS 資料，市內的土地利用分布穩定……
       #### 應優先的對策方案
       1. 強化洪水對策 …… 2. 強化地震對策 …… 3. 強化斜坡崩塌對策 ……
     遮罩：帳戶 ID、自治體名稱（僅顯示樣本名稱） -->
![UC17：Bedrock 生成報告](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. 災害風險地圖 JSON

將洪水·地震·山崩 3 種風險評分按 CRITICAL / HIGH / MEDIUM / LOW
4 個等級判定。

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     內容：risk-maps/*.json 的格式化檢視（強調 flood, earthquake, landslide 的 level）
     遮罩：帳戶 ID -->
![UC17：災害風險地圖](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. 土地利用分布（JSON）

從 Rekognition / SageMaker 推論結果導出的土地利用類別分布。
residential / commercial / forest / water / road 等的比例。

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     內容：landuse/*.json 的內容（residential: 0.5, forest: 0.3 等）
     遮罩：帳戶 ID -->
![UC17：土地利用分布](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. 時間序列變化視覺化（DynamoDB Explorer）

`fsxn-uc17-demo-landuse-history` 資料表。依 area_id 將過去的土地利用分布與
目前值比較，計算 change_magnitude。

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     內容：在 DynamoDB Explorer 中 landuse-history 資料表的時間序列項目
     遮罩：帳戶 ID、area_id -->
![UC17：時間序列變化資料表](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
透過自動化地理空間分析（CRS 正規化·土地利用分類·災害風險映射），支援都市規劃的決策。

### Metrics
| 指標 | 目標值（範例） |
|-----------|------------|
| 已處理資料集數 / 執行 | > 100 files |
| CRS 正規化成功率 | > 95% |
| 土地利用分類精度 | > 80% |
| 風險地圖生成時間 | < 10 分鐘 |
| 成本 / 執行 | < $10 |
| Human Review 對象率 | < 20%（分類不確定區域） |

### Measurement Method
Step Functions 執行歷史、Bedrock 分析報告、Rekognition 偵測結果、S3 輸出 GeoJSON、CloudWatch Metrics。

## 部署

### 事前驗證

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一次性部署

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### 手動部署

```bash
# 前提：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=apac.amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**重要**：請在 Bedrock 主控台啟用 `apac.amazon.nova-lite-v1:0` 的模型存取權限。

## 目錄結構

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS 正規化（EPSG:4326）
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ 點雲分析
│   ├── risk_mapping/handler.py           # 洪水/地震/山崩風險
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## AWS 文件連結

| 服務 | 文件 |
|---------|------------|
| FSx for ONTAP | [使用者指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [開發人員指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [開發人員指南](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [開發人員指南](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [使用者指南](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework 對應

| 支柱 | 對應 |
|----|------|
| 卓越營運 | X-Ray、EMF、土地利用變化追蹤、resilience 測試 |
| 安全性 | 最小權限 IAM、KMS、依部門 NTFS ACL、INSPIRE 合規 |
| 可靠性 | Step Functions Retry/Catch、CRS 正規化、resilience 測試 |
| 效能效率 | GeoTIFF 分塊、SageMaker Batch Transform |
| 成本最佳化 | 無伺服器、SageMaker Spot、DynamoDB 時間序列 |
| 永續性 | 差分變化偵測、OGC 標準合規 |





---

## 成本估算（每月概算）

> **備註**：以下為 ap-northeast-1 區域的概算，實際成本因使用量而異。最新價格請於 [AWS Pricing Calculator](https://calculator.aws/) 確認。

### 無伺服器元件（按量計費）

| 服務 | 單價 | 預計使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 函式 × 20 datasets/日 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/日 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/日 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/執行 | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/查詢 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/日 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |

### 固定成本（FSx for ONTAP — 假設既有環境）

| 元件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共用既有環境) |
| S3 Access Point | 無額外費用（僅 S3 API 費用） |

### 合計概算

| 組態 | 每月概算 |
|------|---------|
| 最小組態（每日 1 次執行） | ~$5-15 |
| 標準組態（每小時執行） | ~$15-50 |
| 大規模組態（高頻 + 警示） | ~$50-150 |

> **Governance Caveat**：成本估算為概算，非保證值。實際帳單因使用模式、資料量與區域而異。

---

## 本機測試

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
# 前提：需要 AWS SAM CLI。sam build 會自動打包程式碼與共用層。
sam build

# 本機執行 Discovery Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 附環境變數覆寫
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 單元測試

```bash
python3 -m pytest tests/ -v
```

詳情請參閱 [本機測試快速入門](../docs/local-testing-quick-start.md)。

---

## 輸出樣本 (Output Sample)

地理空間資料分析管線的輸出範例：

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **備註**：以上為樣本輸出，實際值因環境·輸入資料而異。基準數值為 sizing reference，而非 service limit。

---

## Governance Note

> 本模式提供技術架構指導。並非法律·合規·法規建議。組織應諮詢合格的專業人士。

---

## S3AP Compatibility

關於 S3 Access Points for FSx for ONTAP 的相容性限制、疑難排解與觸發模式，請參閱 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
