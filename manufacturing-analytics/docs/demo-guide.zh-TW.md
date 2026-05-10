# IoT 感測器異常檢測・品質檢查 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示了從製造產線的 IoT 感測器資料中自動偵測異常，並生成品質檢查報告的工作流程。

**示範的核心訊息**：自動偵測感測器資料的異常模式，實現品質問題的早期發現與預防性維護。

**預計時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 製造部門經理 / 品質管理工程師 |
| **日常業務** | 生產線監控、品質檢查、設備維護計劃 |
| **課題** | 遺漏感測器資料異常，導致不良品流入後續工序 |
| **期待成果** | 異常的早期偵測與品質趨勢的可視化 |

### Persona：鈴木先生（品質管理工程師）

- 監控 5 條製造產線的 100+ 個感測器
- 基於閾值的警報誤報率高，容易遺漏真正的異常
- 「希望只偵測統計上顯著的異常」

---

## Demo Scenario：感測器異常偵測批次分析

### 工作流程全貌

```
感測器資料      資料收集       異常偵測          品質報告
(CSV/Parquet)  →   前處理     →   統計分析    →    AI 生成
                   正規化          (離群值偵測)
```

---

## Storyboard（5 個章節 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 製造產線的 100+ 個感測器每天產生大量資料。單純的閾值警報誤報率高，存在遺漏真正異常的風險。

**Key Visual**：感測器資料的時間序列圖表、警報過多的情況

### Section 2: Data Ingestion（0:45–1:30）

**旁白要旨**：
> 當感測器資料累積到檔案伺服器時，會自動啟動分析管線。

**Key Visual**：資料檔案配置 → 工作流程啟動

### Section 3: Anomaly Detection（1:30–2:30）

**旁白要旨**：
> 使用統計方法（移動平均、標準差、IQR）計算各感測器的異常分數。同時執行多個感測器的相關性分析。

**Key Visual**：異常偵測演算法執行中、異常分數的熱圖

### Section 4: Quality Inspection（2:30–3:45）

**旁白要旨**：
> 從品質檢查的角度分析偵測到的異常。識別哪條產線的哪個工序發生問題。

**Key Visual**：Athena 查詢結果 — 按產線別、工序別的異常分布

### Section 5: Report & Action（3:45–5:00）

**旁白要旨**：
> AI 生成品質檢查報告。提出異常的根本原因候選與建議對應措施。

**Key Visual**：AI 生成品質報告（異常摘要 + 建議行動）

---

## Screen Capture Plan

| # | 畫面 | 章節 |
|---|------|-----------|
| 1 | 感測器資料檔案清單 | Section 1 |
| 2 | 工作流程啟動畫面 | Section 2 |
| 3 | 異常偵測處理進度 | Section 3 |
| 4 | 異常分布查詢結果 | Section 4 |
| 5 | AI 品質檢查報告 | Section 5 |

---

## Narration Outline

| 章節 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「閾值警報會遺漏真正的異常」 |
| Ingestion | 0:45–1:30 | 「資料累積後自動開始分析」 |
| Detection | 1:30–2:30 | 「使用統計方法僅偵測顯著異常」 |
| Inspection | 2:30–3:45 | 「在產線・工序層級識別問題位置」 |
| Report | 3:45–5:00 | 「AI 提出根本原因候選與對應策略」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 正常感測器資料（5 條產線 × 7 天份） | 基準線 |
| 2 | 溫度異常資料（2 件） | 異常偵測示範 |
| 3 | 振動異常資料（3 件） | 相關性分析示範 |
| 4 | 品質下降模式（1 件） | 報告生成示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 生成範例感測器資料 | 3 小時 |
| 確認管線執行 | 2 小時 |
| 取得畫面截圖 | 2 小時 |
| 撰寫旁白稿 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 即時串流分析
- 自動生成預防性維護排程
- 數位孿生整合

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (Data Preprocessor) | 感測器資料正規化・前處理 |
| Lambda (Anomaly Detector) | 統計異常偵測 |
| Lambda (Report Generator) | 透過 Bedrock 生成品質報告 |
| Amazon Athena | 異常資料的彙總・分析 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| 資料量不足 | 使用預先生成的資料 |
| 偵測精度不足 | 顯示已調整參數的結果 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 關於輸出目的地：FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics 歸類為 **Pattern A: Native S3AP Output**
（參照 `docs/output-destination-patterns.md`）。

**設計**：感測器資料解析結果、異常偵測報告、影像檢查結果全部透過 FSxN S3 Access Point
寫回與原始感測器 CSV 和檢查影像**相同的 FSx ONTAP 磁碟區**。不會建立標準 S3 儲存貯體
（"no data movement" 模式）。

**CloudFormation 參數**：
- `S3AccessPointAlias`：用於讀取輸入資料的 S3 AP Alias
- `S3AccessPointOutputAlias`：用於寫入輸出的 S3 AP Alias（可與輸入相同）

**部署範例**：
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必要參數)
```

**從 SMB/NFS 使用者的視角**：
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # 原始感測器資料
  └── analysis/2026/05/                 # AI 異常偵測結果（同一磁碟區內）
      └── line_A_report.json
```

關於 AWS 規格上的限制，請參照
[專案 README 的「AWS 規格上的限制與因應對策」章節](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已驗證的 UI/UX 螢幕截圖

與 Phase 7 UC15/16/17 和 UC6/11/14 的示範採用相同方針，以**終端使用者在日常業務中實際
看到的 UI/UX 畫面**為對象。技術人員視圖（Step Functions 圖表、CloudFormation
堆疊事件等）彙整於 `docs/verification-results-*.md`。

### 此使用案例的驗證狀態

- ✅ **E2E 執行**：Phase 1-6 已確認（參照根目錄 README）
- 📸 **UI/UX 重新拍攝**：✅ 2026-05-10 重新部署驗證時已拍攝（確認 UC3 Step Functions 圖表、Lambda 執行成功）
- 🔄 **重現方法**：參照本文件末尾的「拍攝指南」

### 2026-05-10 重新部署驗證時拍攝（以 UI/UX 為中心）

#### UC3 Step Functions Graph view（SUCCEEDED）

![UC3 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view 以顏色可視化各 Lambda / Parallel / Map 狀態的執行狀況，
是終端使用者最重要的畫面。

### 既有螢幕截圖（來自 Phase 1-6 的相關部分）

*（無相關內容。重新驗證時請新拍攝）*

### 重新驗證時的 UI/UX 目標畫面（建議拍攝清單）

- S3 輸出儲存貯體（metrics/、anomalies/、reports/）
- Athena 查詢結果（IoT 感測器異常偵測）
- Rekognition 品質檢查影像標籤
- 製造品質摘要報告

### 拍攝指南

1. **事前準備**：
   - 執行 `bash scripts/verify_phase7_prerequisites.sh` 確認前提條件（共用 VPC/S3 AP 是否存在）
   - 執行 `UC=manufacturing-analytics bash scripts/package_generic_uc.sh` 打包 Lambda
   - 執行 `bash scripts/deploy_generic_ucs.sh UC3` 進行部署

2. **配置範例資料**：
   - 透過 S3 AP Alias 將範例檔案上傳至 `sensors/` 前綴
   - 啟動 Step Functions `fsxn-manufacturing-analytics-demo-workflow`（輸入 `{}`）

3. **拍攝**（關閉 CloudShell・終端機，將瀏覽器右上角的使用者名稱塗黑）：
   - S3 輸出儲存貯體 `fsxn-manufacturing-analytics-demo-output-<account>` 的總覽
   - AI/ML 輸出 JSON 的預覽（參考 `build/preview_*.html` 格式）
   - SNS 電子郵件通知（如適用）

4. **遮罩處理**：
   - 執行 `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo` 進行自動遮罩
   - 依照 `docs/screenshots/MASK_GUIDE.md` 進行額外遮罩（如有需要）

5. **清理**：
   - 執行 `bash scripts/cleanup_generic_ucs.sh UC3` 進行刪除
   - VPC Lambda ENI 釋放需 15-30 分鐘（AWS 規格）
