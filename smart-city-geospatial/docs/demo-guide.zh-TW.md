# UC17 示範腳本（30 分鐘場次）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## 前提

- AWS 帳戶、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Bedrock Nova Lite v1:0 模型已啟用

## 時間軸

### 0:00 - 0:05 簡介（5 分鐘）

- 地方政府的挑戰：都市規劃、災害應變、基礎設施維護中 GIS 資料應用增加
- 傳統挑戰：GIS 分析以 ArcGIS / QGIS 等專業軟體為中心
- 提案：FSxN S3AP + 無伺服器自動化

### 0:05 - 0:10 架構（5 分鐘）

- CRS 正規化的重要性（混合的資料來源）
- 透過 Bedrock 生成都市規劃報告
- 風險模型（洪水、地震、土石流）的計算公式

### 0:10 - 0:15 部署（5 分鐘）

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-uc17-demo \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### 0:15 - 0:22 執行處理（7 分鐘）

```bash
# 上傳範例航空照片（仙台市的一區）
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# 執行 Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

確認結果：
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json`（CRS 資訊）
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json`（土地利用分布）
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json`（災害風險分數）
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md`（Bedrock 生成報告）

### 0:22 - 0:27 風險地圖解說（5 分鐘）

- 在 DynamoDB `landuse-history` 表格中確認時間序列變化
- 顯示 Bedrock 生成報告的 Markdown
- 洪水、地震、土石流風險分數的視覺化

### 0:27 - 0:30 總結（3 分鐘）

- 與 Amazon Location Service 的整合可能性
- 正式運作時的點雲處理（LAS Layer 部署）
- 下一步：MapServer 整合、市民入口網站

## 常見問題與解答

**Q. CRS 轉換實際上會執行嗎？**  
A. 僅在 rasterio / pyproj Layer 配置時執行。透過 `PYPROJ_AVAILABLE` 檢查進行後備處理。

**Q. Bedrock 模型的選擇標準？**  
A. Nova Lite 在成本/精度平衡方面表現良好。如需長文建議使用 Claude Sonnet。
A. Nova Lite 在日文報告生成方面具有高成本效益。Claude 3 Haiku 是優先考慮精度時的替代方案。

---

## 關於輸出目的地：可透過 OutputDestination 選擇（Pattern B）

UC17 smart-city-geospatial 在 2026-05-11 的更新中支援了 `OutputDestination` 參數
（參考 `docs/output-destination-patterns.md`）。

**目標工作負載**：CRS 正規化中繼資料 / 土地利用分類 / 基礎設施評估 / 風險地圖 / Bedrock 生成報告

**兩種模式**：

### STANDARD_S3（預設，與傳統相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果寫入其中。Discovery Lambda 的 manifest 僅寫入 S3 Access Point
（與傳統相同）。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必要參數)
```

### FSXN_S3AP（"no data movement" 模式）
將 CRS 正規化中繼資料、土地利用分類結果、基礎設施評估、風險地圖、Bedrock 生成的
都市規劃報告（Markdown）透過 FSxN S3 Access Point 寫回與原始 GIS 資料
**相同的 FSx ONTAP 磁碟區**。
都市規劃負責人可以在 SMB/NFS 的現有目錄結構中直接參考 AI 成果。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必要參數)
```

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時以 Alias 格式和 ARN 格式授予 IAM 權限）
- 超過 5GB 的物件在 FSxN S3AP 中不可行（AWS 規格），必須使用多部分上傳
- ChangeDetection Lambda 僅使用 DynamoDB，因此不受 `OutputDestination` 影響
- Bedrock 報告以 Markdown（`text/markdown; charset=utf-8`）格式寫出，因此可在 SMB/NFS
  用戶端的文字編輯器中直接檢視
- AWS 規格上的限制請參考
  [專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 驗證**：SUCCEEDED（Phase 7 Extended Round, commit b77fc3b）
- 📸 **UI/UX 拍攝**：✅ 完成（Phase 8 Theme D, commit d7ebabd）

### 現有螢幕截圖（Phase 7 驗證時）

![Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc17-demo/step-functions-graph-succeeded.png)

![S3 輸出儲存貯體](../../docs/screenshots/masked/uc17-demo/s3-output-bucket.png)

![DynamoDB landuse_history 表格](../../docs/screenshots/masked/uc17-demo/dynamodb-landuse-history-table.png)
### 重新驗證時的 UI/UX 目標畫面（建議拍攝清單）

- S3 輸出儲存貯體（tiles/、land-use/、change-detection/、risk-maps/、reports/）
- Bedrock 生成的都市規劃報告（Markdown 預覽）
- DynamoDB landuse_history 表格（土地利用分類歷史）
- 風險地圖 JSON 預覽（CRITICAL/HIGH/MEDIUM/LOW 分類）
- FSx ONTAP 磁碟區上的 AI 成果（FSXN_S3AP 模式時 — 可透過 SMB/NFS 檢視的 Markdown 報告）

### 拍攝指南

1. **事前準備**：
   - 使用 `bash scripts/verify_phase7_prerequisites.sh` 確認前提（共用 VPC/S3 AP 是否存在）
   - 使用 `UC=smart-city-geospatial bash scripts/package_generic_uc.sh` 打包 Lambda
   - 使用 `bash scripts/deploy_generic_ucs.sh UC17` 部署

2. **配置範例資料**：
   - 透過 S3 AP Alias 將範例 GeoTIFF 上傳至 `gis/` 前綴
   - 啟動 Step Functions `fsxn-smart-city-geospatial-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell、終端機，將瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-smart-city-geospatial-demo-output-<account>` 的概覽
   - Bedrock 報告 Markdown 的瀏覽器預覽
   - DynamoDB landuse_history 表格的項目清單
   - 風險地圖 JSON 的結構確認

4. **遮罩處理**：
   - 使用 `python3 scripts/mask_uc_demos.py smart-city-geospatial-demo` 自動遮罩
   - 根據 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - 使用 `bash scripts/cleanup_generic_ucs.sh UC17` 刪除
   - VPC Lambda ENI 釋放需要 15-30 分鐘（AWS 規格）
