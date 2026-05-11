# UC16 示範腳本（30 分鐘場次）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## 前提

- AWS 帳戶、ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- 部署 `government-archives/template-deploy.yaml`（使用 `OpenSearchMode=none` 以降低成本）

## 時間軸

### 0:00 - 0:05 簡介（5 分鐘）

- 使用案例：地方政府・行政的公文書管理數位化
- FOIA / 資訊公開請求的法定期限（20 個工作日）的負荷
- 挑戰：PII 檢測・遮蔽需要手動處理數小時

### 0:05 - 0:10 架構（5 分鐘）

- Textract + Comprehend + Bedrock 的組合
- OpenSearch 的 3 種模式（none / serverless / managed）
- NARA GRS 保存期限的自動管理

### 0:10 - 0:15 部署（5 分鐘）

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 執行處理（7 分鐘）

```bash
# サンプル PDF（機密情報含む）アップロード
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

確認結果：
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt`（原始文字）
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json`（分類結果）
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json`（PII 檢測）
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt`（遮蔽版本）
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json`（sidecar）

### 0:22 - 0:27 FOIA 期限追蹤（5 分鐘）

```bash
# FOIA 請求登録
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda 手動実行
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

確認 SNS 通知郵件。

### 0:27 - 0:30 總結（3 分鐘）

- 啟用 OpenSearch（使用 `serverless` 進行正式搜尋）的路徑
- 遷移至 GovCloud（FedRAMP High 要求）
- 下一步：使用 Bedrock 代理程式生成互動式 FOIA 回應

## 常見問題與解答

**Q. 能否對應日本的資訊公開法（30 天）？**  
A. 修改 `REMINDER_DAYS_BEFORE` 和 20 個工作日的硬編碼即可對應（將美國聯邦假日改為日本假日）。

**Q. 原文 PII 儲存在哪裡？**  
A. 不會儲存在任何地方。`pii-entities/*.json` 僅包含 SHA-256 hash，`redaction-metadata/*.json` 也僅包含 hash + offset。還原需要從原文重新執行。

**Q. 如何降低 OpenSearch Serverless 的成本？**  
A. 最低 2 OCU = 每月約 $350。建議在非正式環境中停止。
A. 使用 `OpenSearchMode=none` 跳過，或使用 `OpenSearchMode=managed` + `t3.small.search × 1` 可降至每月約 $25。

---

## 關於輸出目的地：可透過 OutputDestination 選擇（Pattern B）

UC16 government-archives 在 2026-05-11 的更新中支援了 `OutputDestination` 參數
（參考 `docs/output-destination-patterns.md`）。

**目標工作負載**：OCR 文字 / 文件分類 / PII 檢測 / 遮蔽 / OpenSearch 前段文件

**2 種模式**：

### STANDARD_S3（預設，與以往相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果物寫入其中。Discovery Lambda 的 manifest 僅寫入 S3 Access Point
（與以往相同）。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" 模式）
OCR 文字、分類結果、PII 檢測結果、遮蔽後文件、遮蔽中繼資料透過 FSxN S3 Access Point
寫回與原始文件**相同的 FSx ONTAP 磁碟區**。
公文書負責人可以在 SMB/NFS 的現有目錄結構中直接參考 AI 成果物。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**鏈式結構的讀取**：

UC16 採用鏈式結構，後段 Lambda 會讀取前段的成果物（OCR → Classification →
EntityExtraction → Redaction → IndexGeneration），因此 `shared/output_writer.py` 的
`get_bytes/get_text/get_json` 會從與寫入目的地相同的 destination 讀取。
這使得在 `OutputDestination=FSXN_S3AP` 時也能從 FSxN S3 Access Point 讀取，
整個鏈式處理可以在一致的 destination 中運作。

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時允許 Alias 格式和 ARN 格式的 IAM 權限）
- 超過 5GB 的物件無法使用 FSxN S3AP（AWS 規格），必須使用多部分上傳
- ComplianceCheck Lambda 僅使用 DynamoDB，因此不受 `OutputDestination` 影響
- FoiaDeadlineReminder Lambda 僅使用 DynamoDB + SNS，因此不受影響
- OpenSearch 索引由 `OpenSearchMode` 參數另行管理（與 `OutputDestination` 獨立）
- AWS 規格上的限制請參考
  [專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 截圖

遵循與 Phase 7 UC15/16/17 和 UC6/11/14 演示相同的方針，以**最終使用者在日常工作中
實際看到的 UI/UX 介面**為對象。
技術人員視圖（Step Functions 圖表、CloudFormation 堆疊事件等）
統一整理在 `docs/verification-results-*.md` 中。

### 本用例的驗證狀態

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX 截圖**: ✅ 完成 (Phase 8 Theme D, commit d7ebabd)

### 現有截圖

![Step Functions 圖表視圖 (SUCCEEDED)](../../docs/screenshots/masked/uc16-demo/step-functions-graph-succeeded.png)

![S3 輸出桶](../../docs/screenshots/masked/uc16-demo/s3-output-bucket.png)

![DynamoDB retention 表](../../docs/screenshots/masked/uc16-demo/dynamodb-retention-table.png)
### 重新驗證時的 UI/UX 目標介面（推薦截圖清單）

- S3 輸出桶 (ocr-results/, classified/, redacted/, compliance/)
- Textract OCR 結果 JSON (跨區域 us-east-1)
- 脫敏文件預覽
- DynamoDB retention 表 (FOIA 截止日期管理)
- FOIA 提醒 SNS 郵件通知
- OpenSearch 索引 (OpenSearchMode 啟用時)
- FSx ONTAP 卷 AI 產物 (FSXN_S3AP 模式)

### 截圖指南

1. **準備工作**: 執行 `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件
2. **樣本資料**: 透過 S3 AP Alias 上傳樣本檔案，然後啟動 Step Functions 工作流程
3. **截圖**（關閉 CloudShell/終端，遮蓋瀏覽器右上角使用者名稱）
4. **遮蓋處理**: 執行 `python3 scripts/mask_uc_demos.py <uc-dir>` 進行自動 OCR 遮蓋
5. **清理**: 執行 `bash scripts/cleanup_generic_ucs.sh <UC>` 刪除堆疊
