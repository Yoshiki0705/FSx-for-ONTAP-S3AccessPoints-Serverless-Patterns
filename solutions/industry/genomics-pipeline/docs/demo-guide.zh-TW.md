# 定序品質控制與變異統計 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示次世代定序（NGS）資料的品質管理與變異統計管線。自動驗證定序品質，並統計、報告變異呼叫結果。

**示範核心訊息**：自動化定序資料的 QC，即時生成變異統計報告。確保分析的可靠性。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 生物資訊學家 / 基因體分析研究員 |
| **日常業務** | 定序資料 QC、變異呼叫、結果解讀 |
| **挑戰** | 手動確認大量樣本的 QC 非常耗時 |
| **期望成果** | QC 自動化與變異統計的效率化 |

### Persona：加藤先生（生物資訊學家）

- 每週處理 100+ 樣本的定序資料
- 需要早期偵測不符合 QC 標準的樣本
- 「希望只將通過 QC 的樣本自動送至下游分析」

---

## Demo Scenario：定序批次 QC

### 工作流程全貌

```
FASTQ/BAM 檔案    QC 分析        品質判定         變異統計
(100+ 樣本)  →   指標      →   Pass/Fail   →   報告生成
                     計算            篩選
```

---

## Storyboard（5 個章節 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 每週 100 個以上的定序資料樣本。品質不良的樣本若混入下游分析，會降低整體結果的可靠性。

**Key Visual**：定序資料檔案清單

### Section 2: Pipeline Trigger（0:45–1:30）

**旁白要旨**：
> 定序執行完成後，QC 管線自動啟動。並行處理所有樣本。

**Key Visual**：工作流程啟動、樣本清單

### Section 3: QC Metrics（1:30–2:30）

**旁白要旨**：
> 計算各樣本的 QC 指標：讀取數、Q30 率、對應率、覆蓋深度、重複率。

**Key Visual**：QC 指標計算處理中、指標清單

### Section 4: Quality Filtering（2:30–3:45）

**旁白要旨**：
> 根據 QC 標準判定 Pass/Fail。分類 Fail 樣本的原因（低品質讀取、低覆蓋率等）。

**Key Visual**：Pass/Fail 判定結果、Fail 原因分類

### Section 5: Variant Summary（3:45–5:00）

**旁白要旨**：
> 統計通過 QC 樣本的變異呼叫結果。樣本間比較、變異分布、生成 AI 摘要報告。

**Key Visual**：變異統計報告（統計摘要 + AI 解讀）

---

## Screen Capture Plan

| # | 畫面 | 章節 |
|---|------|-----------|
| 1 | 定序資料清單 | Section 1 |
| 2 | 管線啟動畫面 | Section 2 |
| 3 | QC 指標結果 | Section 3 |
| 4 | Pass/Fail 判定結果 | Section 4 |
| 5 | 變異統計報告 | Section 5 |

---

## Narration Outline

| 章節 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「低品質樣本的混入會損害整體分析的可靠性」 |
| Trigger | 0:45–1:30 | 「執行完成後自動開始 QC」 |
| Metrics | 1:30–2:30 | 「計算所有樣本的主要 QC 指標」 |
| Filtering | 2:30–3:45 | 「根據標準自動判定 Pass/Fail」 |
| Summary | 3:45–5:00 | 「即時生成變異統計與 AI 摘要」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 高品質 FASTQ 指標（20 個樣本） | 基準線 |
| 2 | 低品質樣本（Q30 < 80%，3 件） | Fail 偵測示範 |
| 3 | 低覆蓋率樣本（2 件） | 分類示範 |
| 4 | 變異呼叫結果（VCF 摘要） | 統計示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 樣本 QC 資料準備 | 3 小時 |
| 管線執行確認 | 2 小時 |
| 畫面擷取取得 | 2 小時 |
| 旁白稿撰寫 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 即時定序監控
- 臨床報告自動生成
- 多組學整合分析

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (QC Calculator) | 定序 QC 指標計算 |
| Lambda (Quality Filter) | Pass/Fail 判定・分類 |
| Lambda (Variant Aggregator) | 變異統計 |
| Lambda (Report Generator) | 透過 Bedrock 生成摘要報告 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| 大容量資料處理延遲 | 以子集執行 |
| Bedrock 延遲 | 顯示預先生成的報告 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 已驗證的 UI/UX 螢幕截圖

Phase 7 UC15/16/17 與 UC6/11/14 的示範採用相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）集中於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 執行**：Phase 1-6 已確認（參考根目錄 README）
- 📸 **UI/UX 重新拍攝**：✅ 2026-05-10 重新部署驗證時已拍攝（UC7 Step Functions 圖表、Lambda 執行成功已確認）
- 📸 **UI/UX 拍攝 (Phase 8 Theme D)**：✅ SUCCEEDED 拍攝完成（commit 2b958db — IAM S3AP 修正後重新部署，3:03 所有步驟成功）
- 🔄 **重現方法**：參考本文件末尾的「拍攝指南」

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC7 Step Functions Graph view（SUCCEEDED）

![UC7 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

Step Functions Graph view 以顏色視覺化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

#### UC7 Step Functions Graph（SUCCEEDED — Phase 8 Theme D 重新拍攝）

![UC7 Step Functions Graph（SUCCEEDED）](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

IAM S3AP 修正後重新部署。所有步驟 SUCCEEDED（3:03）。

#### UC7 Step Functions Graph（放大顯示 — 各步驟詳細）

![UC7 Step Functions Graph（放大顯示）](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

#### UC7 Comprehend Medical 基因體分析結果（Cross-Region us-east-1）

![UC7 Comprehend Medical 基因體分析結果（Cross-Region us-east-1）](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### 重新驗證時的 UI/UX 目標畫面（建議拍攝清單）

- S3 輸出儲存貯體（fastq-qc/、variant-summary/、entities/）
- Athena 查詢結果（變異頻率統計）
- Comprehend Medical 醫學實體（Genes, Diseases, Mutations）
- Bedrock 生成的研究報告

### 拍攝指南

1. **事前準備**：
   - `bash scripts/verify_phase7_prerequisites.sh` 確認前提（共用 VPC/S3 AP 是否存在）
   - `UC=genomics-pipeline bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC7` 部署

2. **樣本資料配置**：
   - 透過 S3 AP Alias 將樣本檔案上傳至 `fastq/` 前綴
   - 啟動 Step Functions `fsxn-genomics-pipeline-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-genomics-pipeline-demo-output-<account>` 的俯瞰
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**：
   - `python3 scripts/mask_uc_demos.py genomics-pipeline-demo` 自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如需要）

5. **清理**：
   - `bash scripts/cleanup_generic_ucs.sh UC7` 刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
