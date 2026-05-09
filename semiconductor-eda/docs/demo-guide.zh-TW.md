# EDA 設計檔案驗證 — 演示指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本指南定義了面向半導體設計工程師的技術演示。演示展示設計檔案（GDS/OASIS）的自動品質驗證工作流程，體現簡化投片前設計審查的價值。

**演示核心訊息**：將設計工程師以往手動執行的跨 IP 模組品質檢查，透過自動化工作流程在數分鐘內完成，並透過 AI 生成的設計審查報告實現即時行動。

**預計時長**：3～5 分鐘（含旁白的螢幕錄製影片）

---

## Target Audience & Persona

### Primary Audience：EDA 最終使用者（設計工程師）

| 項目 | 詳情 |
|------|------|
| **職位** | Physical Design Engineer / DRC Engineer / Design Lead |
| **日常工作** | 佈局設計、DRC 執行、IP 模組整合、投片準備 |
| **挑戰** | 跨多個 IP 模組全面了解品質狀況耗時較長 |
| **工具環境** | Calibre、Virtuoso、IC Compiler、Innovus 等 EDA 工具 |
| **期望成果** | 儘早發現設計品質問題，確保投片進度 |

### Persona：田中先生（Physical Design Lead）

- 在大規模 SoC 專案中管理 40 個以上的 IP 模組
- 需要在投片前 2 週對所有模組進行品質審查
- 逐一檢查各模組的 GDS/OASIS 檔案不切實際
- 「希望一目了然地掌握所有模組的品質概況」

---

## Demo Scenario: Pre-tapeout Quality Review

### 情境概述

在投片前品質審查階段，設計負責人對多個 IP 模組（40 個以上檔案）執行自動品質驗證，並根據 AI 生成的審查報告決定後續行動。

### 整體工作流程

```
設計檔案群        自動驗證          分析結果           AI 審查
(GDS/OASIS)    →   工作流程   →   統計彙總    →    報告生成
                    觸發           (Athena SQL)     (自然語言)
```

### 演示展示的價值

1. **時間縮短**：將手動需要數天的橫向審查在數分鐘內完成
2. **完整性**：無遺漏地驗證所有 IP 模組
3. **定量判斷**：透過統計異常值檢測（IQR 方法）進行客觀品質評估
4. **可操作性**：AI 提出具體的建議措施

---

## Storyboard（5 個部分 / 3～5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**畫面**：設計專案的檔案列表（40 個以上 GDS/OASIS 檔案）

**旁白要點**：
> 投片前 2 週。需要確認 40 個以上 IP 模組的設計品質。
> 用 EDA 工具逐一開啟每個檔案進行檢查不切實際。
> 單元數異常、邊界框異常值、命名規則違規——需要一種橫向檢測這些問題的方法。

**Key Visual**：
- 設計檔案目錄結構（.gds、.gds2、.oas、.oasis）
- 「手動審查：預計 3～5 天」文字疊加

---

### Section 2: Workflow Trigger（0:45–1:30）

**畫面**：設計工程師觸發品質驗證工作流程的操作

**旁白要點**：
> 達到設計里程碑後，啟動品質驗證工作流程。
> 只需指定目標目錄，所有設計檔案的自動驗證即開始。

**Key Visual**：
- 工作流程執行畫面（Step Functions 主控台）
- 輸入參數：目標磁碟區路徑、檔案篩選器（.gds/.oasis）
- 執行開始確認

**工程師操作**：
```
目標：/vol/eda_designs/ 下的所有設計檔案
篩選器：.gds、.gds2、.oas、.oasis
執行：啟動品質驗證工作流程
```

---

### Section 3: Automated Analysis（1:30–2:30）

**畫面**：工作流程執行中的進度顯示

**旁白要點**：
> 工作流程自動執行以下操作：
> 1. 設計檔案的偵測和列表化
> 2. 從各檔案標頭提取中繼資料（library_name、cell_count、bounding_box、units）
> 3. 對提取資料進行統計分析（SQL 查詢）
> 4. AI 生成設計審查報告
>
> 即使是大容量 GDS 檔案（數 GB），由於只讀取標頭（64KB），處理速度也很快。

**Key Visual**：
- 工作流程各步驟依次完成的過程
- 平行處理（Map State）顯示多個檔案同時處理
- 處理時間：約 2～3 分鐘（40 個檔案的情況）

---

### Section 4: Results Review（2:30–3:45）

**畫面**：Athena SQL 查詢結果和統計摘要

**旁白要點**：
> 分析結果可以用 SQL 自由查詢。
> 例如，可以進行「顯示邊界框異常大的單元」等即席分析。

**Key Visual — Athena 查詢範例**：
```sql
-- 邊界框異常值檢測
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — 查詢結果**：

| file_key | library_name | width | height | 判定 |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | 異常值 |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | 異常值 |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | 異常值 |

---

### Section 5: Actionable Insights（3:45–5:00）

**畫面**：AI 生成的設計審查報告

**旁白要點**：
> AI 解讀統計分析結果，自動生成面向設計工程師的審查報告。
> 包含風險評估、具體建議措施和按優先順序排列的行動項目。
> 基於此報告，可以在投片前審查會議上立即開始討論。

**Key Visual — AI 審查報告（摘錄）**：

```markdown
# 設計審查報告

## 風險評估：Medium

## 檢測事項摘要
- 邊界框異常值：3 項
- 命名規則違規：2 項
- 無效檔案：2 項

## 建議措施（按優先順序）
1. [High] 調查 2 個無效檔案的原因
2. [Medium] 考慮 analog_frontend.oas 的佈局最佳化
3. [Low] 統一命名規則（block-a-io → block_a_io）
```

**結尾**：
> 以往手動需要數天的橫向審查，現在數分鐘即可完成。
> 設計工程師可以專注於確認分析結果和決定行動方案。

---

## Screen Capture Plan

### 所需螢幕截圖列表

| # | 畫面 | 部分 | 備註 |
|---|------|------|------|
| 1 | 設計檔案目錄列表 | Section 1 | FSx ONTAP 上的檔案結構 |
| 2 | 工作流程執行開始畫面 | Section 2 | Step Functions 主控台 |
| 3 | 工作流程執行中（Map State 平行處理） | Section 3 | 可見進度狀態 |
| 4 | 工作流程完成畫面 | Section 3 | 所有步驟成功 |
| 5 | Athena 查詢編輯器 + 結果 | Section 4 | 異常值檢測查詢 |
| 6 | 中繼資料 JSON 輸出範例 | Section 4 | 1 個檔案的提取結果 |
| 7 | AI 設計審查報告全文 | Section 5 | Markdown 渲染顯示 |
| 8 | SNS 通知郵件 | Section 5 | 報告完成通知 |

### 截圖步驟

1. 在演示環境中放置範例資料
2. 手動執行工作流程，在每個步驟進行螢幕截圖
3. 在 Athena 主控台執行查詢並截取結果
4. 從 S3 下載生成的報告並顯示

---

## Narration Outline

### 語調與風格

- **視角**：設計工程師（田中先生）的第一人稱視角
- **語調**：務實、問題解決型
- **語言**：日語（可選英文字幕）
- **語速**：緩慢清晰（技術演示）

### 旁白結構

| 部分 | 時間 | 關鍵訊息 |
|------|------|---------|
| Problem | 0:00–0:45 | 「投片前需要確認 40 個以上模組的品質。手動來不及」 |
| Trigger | 0:45–1:30 | 「設計里程碑後只需啟動工作流程」 |
| Analysis | 1:30–2:30 | 「標頭解析 → 中繼資料提取 → 統計分析自動進行」 |
| Results | 2:30–3:45 | 「用 SQL 自由查詢。立即定位異常值」 |
| Insights | 3:45–5:00 | 「AI 報告提出優先順序行動。直接對接審查會議」 |

---

## Sample Data Requirements

### 所需範例資料

| # | 檔案 | 格式 | 用途 |
|---|------|------|------|
| 1 | `top_chip_v3.gds` | GDSII | 主晶片（大規模，1000+ 單元） |
| 2 | `block_a_io.gds2` | GDSII | I/O 模組（正常資料） |
| 3 | `memory_ctrl.oasis` | OASIS | 記憶體控制器（正常資料） |
| 4 | `analog_frontend.oas` | OASIS | 類比模組（異常值：大 BB） |
| 5 | `test_block_debug.gds` | GDSII | 除錯用（異常值：高度異常） |
| 6 | `legacy_io_v1.gds2` | GDSII | 舊版模組（異常值：寬度·高度） |
| 7 | `block-a-io.gds2` | GDSII | 命名規則違規範例 |
| 8 | `TOP CHIP (copy).gds` | GDSII | 命名規則違規範例 |

### 範例資料生成方針

- **最小配置**：8 個檔案（上述列表）涵蓋演示的所有情境
- **建議配置**：40 個以上檔案（提高統計分析的說服力）
- **生成方法**：用 Python 腳本生成具有有效 GDSII/OASIS 標頭的測試檔案
- **大小**：由於只進行標頭解析，每個檔案約 100KB 即可

### 現有演示環境確認事項

- [ ] 範例資料是否已放置在 FSx ONTAP 磁碟區上
- [ ] S3 Access Point 是否已設定
- [ ] Glue Data Catalog 資料表定義是否存在
- [ ] Athena 工作群組是否可用

---

## Timeline

### 1 週內可達成

| # | 任務 | 所需時間 | 前提條件 |
|---|------|---------|---------|
| 1 | 範例資料生成（8 個檔案） | 2 小時 | Python 環境 |
| 2 | 演示環境中工作流程執行確認 | 2 小時 | 已部署環境 |
| 3 | 螢幕截圖取得（8 個畫面） | 3 小時 | 任務 2 完成後 |
| 4 | 旁白腳本定稿 | 2 小時 | 任務 3 完成後 |
| 5 | 影片編輯（截圖 + 旁白） | 4 小時 | 任務 3、4 完成後 |
| 6 | 審查與修改 | 2 小時 | 任務 5 完成後 |
| **合計** | | **15 小時** | |

### 前提條件（1 週達成所需）

- Step Functions 工作流程已部署且正常運作
- Lambda 函式（Discovery、MetadataExtraction、DrcAggregation、ReportGeneration）已驗證
- Athena 資料表和查詢可執行
- Bedrock 模型存取已啟用

### Future Enhancements（未來擴展）

| # | 擴展項目 | 概述 | 優先順序 |
|---|---------|------|---------|
| 1 | DRC 工具整合 | 直接匯入 Calibre/Pegasus 的 DRC 結果檔案 | High |
| 2 | 互動式儀表板 | 透過 QuickSight 實現設計品質儀表板 | Medium |
| 3 | Slack/Teams 通知 | 審查報告完成時發送聊天通知 | Medium |
| 4 | 差異審查 | 自動偵測並報告與上次執行的差異 | High |
| 5 | 自訂規則定義 | 可設定專案特定的品質規則 | Medium |
| 6 | 多語言報告 | 支援英語/日語/中文的報告生成 | Low |
| 7 | CI/CD 整合 | 作為設計流程中的自動品質閘道嵌入 | High |
| 8 | 大規模資料支援 | 1000 個以上檔案的平行處理最佳化 | Medium |

---

## Technical Notes（演示製作者用）

### 使用元件（僅現有實作）

| 元件 | 角色 |
|------|------|
| Step Functions | 整體工作流程編排 |
| Lambda (Discovery) | 設計檔案偵測和列表化 |
| Lambda (MetadataExtraction) | GDSII/OASIS 標頭解析和中繼資料提取 |
| Lambda (DrcAggregation) | 透過 Athena SQL 執行統計分析 |
| Lambda (ReportGeneration) | 透過 Bedrock 生成 AI 審查報告 |
| Amazon Athena | 對中繼資料的 SQL 查詢 |
| Amazon Bedrock | 自然語言報告生成（Nova Lite / Claude） |

### 演示執行時的備援方案

| 情境 | 應對 |
|------|------|
| 工作流程執行失敗 | 使用預先錄製的執行畫面 |
| Bedrock 回應延遲 | 顯示預先生成的報告 |
| Athena 查詢逾時 | 顯示預先取得的結果 CSV |
| 網路故障 | 所有畫面預先截取並製作為影片 |

---

*本文件作為技術演示影片的製作指南而建立。*
