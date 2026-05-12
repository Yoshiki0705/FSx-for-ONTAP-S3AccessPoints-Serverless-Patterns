# BIM 模型變更檢測・安全合規性 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示 BIM 模型的變更檢測與安全合規檢查管線。自動偵測設計變更，並驗證是否符合建築標準。

**示範核心訊息**：自動追蹤 BIM 模型的變更，即時偵測安全標準違規。縮短設計審查週期。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | BIM 管理員 / 結構設計工程師 |
| **日常業務** | BIM 模型管理、設計變更審查、合規確認 |
| **課題** | 追蹤多個團隊的設計變更並確認標準符合性相當困難 |
| **期待成果** | 變更自動偵測與安全標準檢查的效率化 |

### Persona：木村先生（BIM 管理員）

- 大規模建設專案中有 20+ 個設計團隊並行作業
- 需要確認每日的設計變更是否影響安全標準
- 「希望有變更時能自動執行安全檢查」

---

## Demo Scenario：設計變更的自動偵測與安全驗證

### 工作流程全貌

```
BIM 模型更新     變更偵測        合規檢查         審查報告
(IFC/RVT)    →   差異分析    →   規則比對     →    AI 生成
                  要素比較        安全標準檢查
```

---

## Storyboard（5 個章節 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 大規模專案中有 20 個團隊並行更新 BIM 模型。手動確認變更是否違反安全標準已無法跟上進度。

**Key Visual**：BIM 模型檔案清單、多個團隊的更新歷程

### Section 2: Change Detection（0:45–1:30）

**旁白要旨**：
> 偵測模型檔案的更新，自動分析與前版本的差異。識別變更的要素（結構構件、設備配置等）。

**Key Visual**：變更偵測觸發、差異分析開始

### Section 3: Compliance Check（1:30–2:30）

**旁白要旨**：
> 對變更的要素自動比對安全標準規則。驗證耐震標準、防火區劃、避難路徑等的符合性。

**Key Visual**：規則比對處理中、檢查項目清單

### Section 4: Results Analysis（2:30–3:45）

**旁白要旨**：
> 確認驗證結果。列表顯示違規項目、影響範圍、重要度。

**Key Visual**：違規偵測結果表格、依重要度分類

### Section 5: Review Report（3:45–5:00）

**旁白要旨**：
> AI 生成設計審查報告。提示違規詳情、修正方案、受影響的其他設計要素。

**Key Visual**：AI 生成審查報告

---

## Screen Capture Plan

| # | 畫面 | 章節 |
|---|------|-----------|
| 1 | BIM 模型檔案清單 | Section 1 |
| 2 | 變更偵測・差異顯示 | Section 2 |
| 3 | 合規檢查進度 | Section 3 |
| 4 | 違規偵測結果 | Section 4 |
| 5 | AI 審查報告 | Section 5 |

---

## Narration Outline

| 章節 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「並行作業的變更追蹤與安全確認無法跟上進度」 |
| Detection | 0:45–1:30 | 「自動偵測模型更新並分析差異」 |
| Compliance | 1:30–2:30 | 「自動比對安全標準規則」 |
| Results | 2:30–3:45 | 「即時掌握違規項目與影響範圍」 |
| Report | 3:45–5:00 | 「AI 提示修正方案與影響分析」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 基準 BIM 模型（IFC 格式） | 比較來源 |
| 2 | 變更後模型（含結構變更） | 差異偵測示範 |
| 3 | 安全標準違規模型（3 件） | 合規示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 準備範例 BIM 資料 | 3 小時 |
| 確認管線執行 | 2 小時 |
| 取得畫面截圖 | 2 小時 |
| 撰寫旁白稿 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 3D 視覺化整合
- 即時變更通知
- 施工階段的一致性檢查

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (Change Detector) | BIM 模型差異分析 |
| Lambda (Compliance Checker) | 安全標準規則比對 |
| Lambda (Report Generator) | 透過 Bedrock 生成審查報告 |
| Amazon Athena | 變更歷程・違規資料的彙總 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| IFC 解析失敗 | 使用預先分析的資料 |
| 規則比對延遲 | 顯示預先驗證的結果 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：可透過 OutputDestination 選擇（Pattern B）

UC10 construction-bim 在 2026-05-10 的更新中支援了 `OutputDestination` 參數
（參照 `docs/output-destination-patterns.md`）。

**對象工作負載**：建設 BIM / 圖面 OCR / 安全合規檢查

**2 種模式**：

### STANDARD_S3（預設，與以往相同）
建立新的 S3 儲存貯體（`${AWS::StackName}-output-${AWS::AccountId}`），
並將 AI 成果物寫入其中。

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必要參數)
```

### FSXN_S3AP（"no data movement" 模式）
透過 FSxN S3 Access Point 將 AI 成果物寫回與原始資料**相同的 FSx ONTAP 磁碟區**。
SMB/NFS 使用者可在業務使用的目錄結構內直接瀏覽 AI 成果物。
不會建立標準 S3 儲存貯體。

```bash
aws cloudformation deploy \
  --template-file construction-bim/template-deploy.yaml \
  --stack-name fsxn-construction-bim-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必要參數)
```

**注意事項**：

- 強烈建議指定 `S3AccessPointName`（同時以 Alias 格式和 ARN 格式授予 IAM 權限）
- 超過 5GB 的物件無法透過 FSxN S3AP 處理（AWS 規格），必須使用分段上傳
- AWS 規格上的限制請參照
  [專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範採用相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 執行**：Phase 1-6 已確認（參照根目錄 README）
- 📸 **UI/UX 重新截圖**：✅ 2026-05-10 重新部署驗證時已截圖（確認 UC10 Step Functions 圖表、Lambda 執行成功）
- 🔄 **重現方法**：參照本文件末尾的「截圖指南」

### 2026-05-10 重新部署驗證時截圖（以 UI/UX 為中心）

#### UC10 Step Functions Graph view（SUCCEEDED）

![UC10 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc10-demo/uc10-stepfunctions-graph.png)

Step Functions Graph view 以顏色視覺化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

![UC10 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc10-demo/step-functions-graph-succeeded.png)

![UC10 Step Functions Graph（放大顯示 — 各步驟詳情）](../../docs/screenshots/masked/uc10-demo/step-functions-graph-zoomed.png)

### 重新驗證時的 UI/UX 對象畫面（建議截圖清單）

- S3 輸出儲存貯體（drawings-ocr/、bim-metadata/、safety-reports/）
- Textract 圖面 OCR 結果（跨區域）
- BIM 版本差異報告
- Bedrock 安全合規檢查

### 截圖指南

1. **事前準備**：
   - 執行 `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件（共用 VPC/S3 AP 是否存在）
   - 執行 `UC=construction-bim bash scripts/package_generic_uc.sh` 打包 Lambda
   - 執行 `bash scripts/deploy_generic_ucs.sh UC10` 進行部署

2. **配置範例資料**：
   - 透過 S3 AP Alias 將範例檔案上傳至 `drawings/` 前綴
   - 啟動 Step Functions `fsxn-construction-bim-demo-workflow`（輸入 `{}`）

3. **截圖**（關閉 CloudShell・終端機，將瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-construction-bim-demo-output-<account>` 的概覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 的格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**：
   - 執行 `python3 scripts/mask_uc_demos.py construction-bim-demo` 進行自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - 執行 `bash scripts/cleanup_generic_ucs.sh UC10` 進行刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
