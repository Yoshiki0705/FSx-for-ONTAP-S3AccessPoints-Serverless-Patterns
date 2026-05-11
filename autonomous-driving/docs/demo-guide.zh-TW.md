# 行駛數據前處理・標註 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示了自動駕駛開發中行駛數據的前處理與標註流程。自動分類大量感測器數據、進行品質檢查，並高效建構訓練資料集。

**示範核心訊息**：自動化行駛數據的品質驗證與元數據附加，加速 AI 訓練用資料集的建構。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 資料工程師 / ML 工程師 |
| **日常業務** | 行駛數據管理、標註、訓練資料集建構 |
| **課題** | 無法從大量行駛數據中有效率地提取有用場景 |
| **期待成果** | 自動化數據品質驗證與場景分類的效率化 |

### Persona：伊藤先生（資料工程師）

- 每天累積 TB 級的行駛數據
- 相機・LiDAR・雷達的同步確認需手動進行
- 「希望能自動將高品質數據送入訓練流程」

---

## Demo Scenario：行駛數據批次前處理

### 工作流程全貌

```
行駛數據        數據驗證       場景分類        資料集
(ROS bag等)  →   品質檢查  →  元數據     →   目錄生成
                  同步確認        附加 (AI)
```

---

## Storyboard（5 個章節 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 每天累積 TB 級的行駛數據。品質不良的數據（感測器缺失、同步偏移）混雜其中，手動篩選不切實際。

**Key Visual**：行駛數據資料夾結構、數據量的視覺化

### Section 2: Pipeline Trigger（0:45–1:30）

**旁白要旨**：
> 當新的行駛數據上傳時，前處理流程自動啟動。

**Key Visual**：數據上傳 → 工作流程自動啟動

### Section 3: Quality Validation（1:30–2:30）

**旁白要旨**：
> 感測器數據的完整性檢查：自動偵測影格缺失、時間戳記同步、數據損壞。

**Key Visual**：品質檢查結果 — 各感測器的健全性分數

### Section 4: Scene Classification（2:30–3:45）

**旁白要旨**：
> AI 自動分類場景：交叉路口、高速公路、惡劣天氣、夜間等。作為元數據附加。

**Key Visual**：場景分類結果表格、各類別分布

### Section 5: Dataset Catalog（3:45–5:00）

**旁白要旨**：
> 自動生成品質驗證完成數據的目錄。可作為依場景條件搜尋的資料集使用。

**Key Visual**：資料集目錄、搜尋介面

---

## Screen Capture Plan

| # | 畫面 | 章節 |
|---|------|-----------|
| 1 | 行駛數據資料夾結構 | Section 1 |
| 2 | 流程啟動畫面 | Section 2 |
| 3 | 品質檢查結果 | Section 3 |
| 4 | 場景分類結果 | Section 4 |
| 5 | 資料集目錄 | Section 5 |

---

## Narration Outline

| 章節 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「從 TB 級數據中手動篩選有用場景是不可能的」 |
| Trigger | 0:45–1:30 | 「上傳後自動開始前處理」 |
| Validation | 1:30–2:30 | 「自動偵測感測器缺失・同步偏移」 |
| Classification | 2:30–3:45 | 「AI 自動分類場景並附加元數據」 |
| Catalog | 3:45–5:00 | 「自動生成可搜尋的資料集目錄」 |

---

## Sample Data Requirements

| # | 數據 | 用途 |
|---|--------|------|
| 1 | 正常行駛數據（5 個工作階段） | 基準線 |
| 2 | 影格缺失數據（2 件） | 品質檢查示範 |
| 3 | 多樣場景數據（交叉路口、高速、夜間） | 分類示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 準備範例行駛數據 | 3 小時 |
| 確認流程執行 | 2 小時 |
| 取得畫面截圖 | 2 小時 |
| 撰寫旁白稿 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 3D 標註自動生成
- 透過主動學習進行數據選擇
- 數據版本控制整合

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (Python 3.13) | 感測器數據品質驗證、場景分類、目錄生成 |
| Lambda SnapStart | 減少冷啟動（透過 `EnableSnapStart=true` 選擇加入） |
| SageMaker (4-way routing) | 推論（Batch / Serverless / Provisioned / Inference Components） |
| SageMaker Inference Components | 真正的 scale-to-zero（`EnableInferenceComponents=true`） |
| Amazon Bedrock | 場景分類・標註建議 |
| Amazon Athena | 元數據搜尋・彙總 |
| CloudFormation Guard Hooks | 部署時強制執行安全政策 |

### 本機測試 (Phase 6A)

```bash
# SAM CLI 本機測試
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### 備援方案

| 情境 | 對應 |
|---------|------|
| 大容量數據處理延遲 | 以子集執行 |
| 分類精度不足 | 顯示預先分類完成的結果 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：可透過 OutputDestination 選擇 (Pattern B)

UC9 autonomous-driving 在 2026-05-10 的更新中支援了 `OutputDestination` 參數
（參考 `docs/output-destination-patterns.md`）。

**目標工作負載**：ADAS / 自動駕駛數據（影格提取、點雲 QC、標註、推論）

**2 種模式**：

### STANDARD_S3（預設，與以往相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果物寫入其中。

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必要參數)
```

### FSXN_S3AP（"no data movement" 模式）
透過 FSxN S3 Access Point 將 AI 成果物寫回與原始數據**相同的 FSx ONTAP 磁碟區**。
SMB/NFS 使用者可在業務使用的目錄結構內直接瀏覽 AI 成果物。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必要參數)
```

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時以 Alias 格式和 ARN 格式授予 IAM 權限）
- 超過 5GB 的物件無法透過 FSxN S3AP 處理（AWS 規格），必須使用多部分上傳
- AWS 規格上的限制請參考
  [專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ⚠️ **E2E 驗證**：僅部分功能（生產環境建議進行額外驗證）
- 📸 **UI/UX 重新截圖**：未實施

### 現有螢幕截圖（Phase 1-6 相關部分）

![UC9 Step Functions 圖表視圖 (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### 重新驗證時的 UI/UX 目標畫面（建議拍攝清單）

- S3 輸出儲存貯體（keyframes/、annotations/、qc/）
- Rekognition 關鍵影格物件偵測結果
- LiDAR 點雲品質檢查摘要
- COCO 相容標註 JSON

### 拍攝指南

1. **事前準備**：
   - 以 `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件（共用 VPC/S3 AP 是否存在）
   - 以 `UC=autonomous-driving bash scripts/package_generic_uc.sh` 打包 Lambda
   - 以 `bash scripts/deploy_generic_ucs.sh UC9` 部署

2. **配置範例數據**：
   - 透過 S3 AP Alias 將範例檔案上傳至 `footage/` 前綴
   - 啟動 Step Functions `fsxn-autonomous-driving-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，瀏覽器右上角的使用者名稱需遮蔽）：
   - S3 輸出儲存貯體 `fsxn-autonomous-driving-demo-output-<account>` 的概覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**：
   - 以 `python3 scripts/mask_uc_demos.py autonomous-driving-demo` 自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - 以 `bash scripts/cleanup_generic_ucs.sh UC9` 刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
