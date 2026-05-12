# 商品圖像標籤與目錄元數據生成 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻譯由 Amazon Bedrock Claude 產生。歡迎對翻譯品質提出改進建議。

## Executive Summary

本示範展示商品圖片自動標記與目錄元資料生成管線。透過 AI 圖片分析自動提取商品屬性，建構可搜尋的目錄。

**示範核心訊息**：AI 從商品圖片自動提取屬性（顏色、材質、類別等），即時生成目錄元資料。

**預估時間**：3〜5 分鐘

---

## Target Audience & Persona

| 項目 | 詳細 |
|------|------|
| **職位** | 電商網站營運者 / 目錄管理者 / 商品企劃負責人 |
| **日常業務** | 商品登錄、圖片管理、目錄更新 |
| **課題** | 新商品的屬性輸入與標記耗時 |
| **期待成果** | 商品登錄自動化與搜尋性提升 |

### Persona：吉田先生（電商目錄管理者）

- 每週登錄 200+ 件新商品
- 每件商品需手動輸入 10+ 個屬性標籤
- 「希望只要上傳商品圖片就能自動生成標籤」

---

## Demo Scenario：新商品批次登錄

### 工作流程全貌

```
商品圖片          圖片分析        屬性提取          目錄更新
(JPEG/PNG)   →   AI 分析    →   標籤生成    →    元資料
                  物件偵測        類別分類          登錄
```

---

## Storyboard（5 個段落 / 3〜5 分鐘）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**：
> 每週 200 件以上的新商品。每件商品需手動輸入顏色、材質、類別、風格等標籤，工作量龐大。也會發生輸入錯誤或不一致的情況。

**Key Visual**：商品圖片資料夾、手動標籤輸入畫面

### Section 2: Image Upload（0:45–1:30）

**旁白要旨**：
> 只要將商品圖片放置到資料夾，自動標記管線就會啟動。

**Key Visual**：圖片上傳 → 工作流程自動啟動

### Section 3: AI Analysis（1:30–2:30）

**旁白要旨**：
> AI 分析每張圖片，自動判定商品類別、顏色、材質、圖案、風格。同時提取多個屬性。

**Key Visual**：圖片分析處理中、屬性提取結果

### Section 4: Tag Generation（2:30–3:45）

**旁白要旨**：
> 將提取的屬性轉換為標準化標籤。確保與既有標籤體系的一致性。

**Key Visual**：生成標籤清單、依類別分布

### Section 5: Catalog Update（3:45–5:00）

**旁白要旨**：
> 元資料自動登錄至目錄。有助於提升搜尋性與商品推薦精準度。生成處理摘要報告。

**Key Visual**：目錄更新結果、AI 摘要報告

---

## Screen Capture Plan

| # | 畫面 | 段落 |
|---|------|-----------|
| 1 | 商品圖片資料夾 | Section 1 |
| 2 | 管線啟動畫面 | Section 2 |
| 3 | AI 圖片分析結果 | Section 3 |
| 4 | 標籤生成結果清單 | Section 4 |
| 5 | 目錄更新摘要 | Section 5 |

---

## Narration Outline

| 段落 | 時間 | 關鍵訊息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | 「每週 200 件的手動標記工作量龐大」 |
| Upload | 0:45–1:30 | 「只要放置圖片就開始自動標記」 |
| Analysis | 1:30–2:30 | 「AI 自動判定顏色、材質、類別」 |
| Tags | 2:30–3:45 | 「自動生成標準化標籤」 |
| Catalog | 3:45–5:00 | 「自動登錄至目錄，提升搜尋性」 |

---

## Sample Data Requirements

| # | 資料 | 用途 |
|---|--------|------|
| 1 | 服飾商品圖片（10 張） | 主要處理對象 |
| 2 | 家具商品圖片（5 張） | 類別分類示範 |
| 3 | 配件圖片（5 張） | 多屬性提取示範 |
| 4 | 既有標籤體系主檔 | 標準化示範 |

---

## Timeline

### 1 週內可達成

| 任務 | 所需時間 |
|--------|---------|
| 準備範例商品圖片 | 2 小時 |
| 確認管線執行 | 2 小時 |
| 取得畫面截圖 | 2 小時 |
| 撰寫旁白稿 | 2 小時 |
| 影片編輯 | 4 小時 |

### Future Enhancements

- 相似商品搜尋
- 自動商品說明文生成
- 趨勢分析整合

---

## Technical Notes

| 元件 | 角色 |
|--------------|------|
| Step Functions | 工作流程編排 |
| Lambda (Image Analyzer) | 透過 Bedrock/Rekognition 進行圖片分析 |
| Lambda (Tag Generator) | 屬性標籤生成與標準化 |
| Lambda (Catalog Updater) | 目錄元資料登錄 |
| Lambda (Report Generator) | 處理摘要報告生成 |

### 備援方案

| 情境 | 對應 |
|---------|------|
| 圖片分析精準度不足 | 使用預先分析結果 |
| Bedrock 延遲 | 顯示預先生成標籤 |

---

*本文件為技術簡報用示範影片的製作指南。*

---

## 已驗證的 UI/UX 截圖（2026-05-10 AWS 驗證）

與 Phase 7 相同方針，拍攝 **電商負責人在日常業務中實際使用的 UI/UX 畫面**。
排除技術人員用畫面（Step Functions 圖表等）。

### 輸出目的地選擇：標準 S3 vs FSxN S3AP

UC11 在 2026-05-10 的更新中支援 `OutputDestination` 參數。
**將 AI 成果寫回同一 FSx 磁碟區**，讓 SMB/NFS 使用者能在
商品圖片的目錄結構內瀏覽自動生成的標籤 JSON
（"no data movement" 模式）。

```bash
# STANDARD_S3 模式（預設，與以往相同）
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP 模式（將 AI 成果寫回 FSx ONTAP 磁碟區）
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 規格限制與因應對策請參閱[專案 README 的「AWS 規格限制與因應對策」
段落](../../README.md#aws-仕様上の制約と回避策)。

### 1. 商品圖片自動標記結果

電商管理者在新商品登錄時收到的 AI 分析結果。Rekognition 從實際圖片偵測到 7 個標籤
（`Oval` 99.93%、`Food`、`Furniture`、`Table`、`Sweets`、`Cocoa`、`Dessert`）。

<!-- SCREENSHOT: uc11-product-tags.png
     內容：商品圖片 + AI 偵測標籤清單（含信賴度）
     遮罩：帳戶 ID、儲存貯體名稱 -->
![UC11：商品標籤](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. S3 輸出儲存貯體 — 標籤與品質檢查結果總覽

電商營運負責人確認批次處理結果的畫面。
在 `tags/` 與 `quality/` 兩個前綴下，為每件商品生成 JSON。

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     內容：S3 主控台顯示 tags/、quality/ 前綴
     遮罩：帳戶 ID -->
![UC11：S3 輸出儲存貯體](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### 實測值（2026-05-10 AWS 部署驗證）

- **Step Functions 執行**：SUCCEEDED，並行處理 4 張商品圖片
- **Rekognition**：從實際圖片偵測到 7 個標籤（最高信賴度 99.93%）
- **生成 JSON**：tags/*.json (~750 bytes)、quality/*.json (~420 bytes)
- **實際堆疊**：`fsxn-retail-catalog-demo`（ap-northeast-1，2026-05-10 驗證時）
