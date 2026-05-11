# UC15 示範腳本（30 分鐘場次）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## 前提

- AWS 帳戶、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- 已部署 `defense-satellite/template-deploy.yaml`（`EnableSageMaker=false`）

## 時間軸

### 0:00 - 0:05 簡介（5 分鐘）

- 使用案例背景：衛星影像資料的增加（Sentinel、Landsat、商用 SAR）
- 傳統 NAS 的挑戰：基於複製的工作流程耗時且成本高
- FSxN S3AP 的優勢：零複製、NTFS ACL 聯動、無伺服器處理

### 0:05 - 0:10 架構說明（5 分鐘）

- 使用 Mermaid 圖介紹 Step Functions 工作流程
- 根據影像大小切換 Rekognition / SageMaker 的邏輯
- 基於 geohash 的變化檢測機制

### 0:10 - 0:15 現場部署（5 分鐘）

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-uc15-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:20 範例影像處理（5 分鐘）

```bash
# サンプル GeoTIFF アップロード
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- 在 AWS 主控台展示 Step Functions 圖形（Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration）
- 確認執行至 SUCCEEDED 的時間（通常 2-3 分鐘）

### 0:20 - 0:25 結果確認（5 分鐘）

- 展示 S3 輸出儲存貯體的階層結構：
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- 在 CloudWatch Logs 確認 EMF 指標
- 在 DynamoDB `change-history` 資料表查看變化檢測歷史記錄

### 0:25 - 0:30 Q&A + 總結（5 分鐘）

- 公共部門法規遵循（DoD CC SRG、CSfC、FedRAMP）
- GovCloud 遷移路徑（使用相同範本從 `ap-northeast-1` → `us-gov-west-1`）
- 成本最佳化（SageMaker Endpoint 僅在實際營運時啟用）
- 下一步：多衛星供應商整合、Sentinel-1/2 Hub 連接

## 常見問題與解答

**Q. SAR 資料（Sentinel-1 的 HDF5）如何處理？**  
A. Discovery Lambda 會分類為 `image_type=sar`，Tiling 可實作 HDF5 解析器（rasterio 或 h5py）。Object Detection 需要專用的 SAR 分析模型（SageMaker）。

**Q. 影像大小閾值（5MB）的依據？**  
A. Rekognition DetectLabels API 的 Bytes 參數上限。透過 S3 可達 15MB。原型採用 Bytes 路徑。

**Q. 變化檢測的精度如何？**  
A. 目前實作是基於 bbox 面積的簡易比較。正式營運建議使用 SageMaker 的語義分割。

---

## 關於輸出目的地：可透過 OutputDestination 選擇（Pattern B）

UC15 defense-satellite 在 2026-05-11 的更新中支援了 `OutputDestination` 參數
（參閱 `docs/output-destination-patterns.md`）。

**目標工作負載**：衛星影像切片 / 物體檢測 / Geo enrichment

**兩種模式**：

### STANDARD_S3（預設，與以往相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果寫入該處。Discovery Lambda 的 manifest 僅寫入 S3 Access Point
（與以往相同）。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" 模式）
將切片 metadata、物體檢測 JSON、Geo enrichment 完成的檢測結果，透過 FSxN S3 Access Point
寫回與原始衛星影像**相同的 FSx ONTAP 磁碟區**。
分析人員可以在 SMB/NFS 的現有目錄結構中直接參照 AI 成果。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時以 Alias 格式和 ARN 格式授予 IAM 權限）
- 超過 5GB 的物件無法透過 FSxN S3AP 處理（AWS 規格限制），必須使用多部分上傳
- ChangeDetection Lambda 僅使用 DynamoDB，因此不受 `OutputDestination` 影響
- AlertGeneration Lambda 僅使用 SNS，因此不受 `OutputDestination` 影響
- AWS 規格限制請參閱
  [專案 README 的「AWS 規格限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 截圖

遵循與 Phase 7 UC15/16/17 和 UC6/11/14 演示相同的方針，以**最終使用者在日常工作中
實際看到的 UI/UX 介面**為對象。
技術人員視圖（Step Functions 圖表、CloudFormation 堆疊事件等）
統一整理在 `docs/verification-results-*.md` 中。

### 本用例的驗證狀態

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX**: Not yet captured

### 現有截圖

![UC15 Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc15-demo/uc15-stepfunctions-graph.png)

### 重新驗證時的 UI/UX 目標介面（推薦截圖清單）

- S3 輸出桶 (detections/, geo-enriched/, alerts/)
- Rekognition 衛星影像目標偵測結果 JSON
- GeoEnrichment 座標標記偵測結果
- SNS 告警通知郵件
- FSx ONTAP 卷 AI 產物 (FSXN_S3AP 模式)

### 截圖指南

1. **準備工作**: 執行 `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件
2. **樣本資料**: 透過 S3 AP Alias 上傳樣本檔案，然後啟動 Step Functions 工作流程
3. **截圖**（關閉 CloudShell/終端，遮蓋瀏覽器右上角使用者名稱）
4. **遮蓋處理**: 執行 `python3 scripts/mask_uc_demos.py <uc-dir>` 進行自動 OCR 遮蓋
5. **清理**: 執行 `bash scripts/cleanup_generic_ucs.sh <UC>` 刪除堆疊
