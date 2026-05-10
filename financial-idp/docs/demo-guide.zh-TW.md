# 合約·發票自動處理 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了合約和發票的自動處理管線。結合OCR文字擷取和實體擷取，從非結構化文件自動產生結構化資料。

**核心訊息**: 自動數位化紙本合約和發票，即時擷取和結構化金額、日期、供應商等關鍵資訊。

**預計時間**: 3–5 min

---

## 輸出目標: FSxN S3 Access Point (Pattern A)

此 UC 屬於 **Pattern A: Native S3AP Output**
(請參閱 `docs/output-destination-patterns.md`)。

**設計**: 所有 AI/ML 產物透過 FSxN S3 Access Point 寫回與來源資料**相同的 FSx ONTAP 磁碟區**。
不建立獨立的標準 S3 儲存貯體 ("no data movement" 模式)。

**CloudFormation 參數**:
- `S3AccessPointAlias`: 輸入用 S3 AP Alias
- `S3AccessPointOutputAlias`: 輸出用 S3 AP Alias (可以與輸入相同)

AWS 規格約束與解決方案請參閱
[README.zh-TW.md — AWS 規格約束](../../README.zh-TW.md#aws-規格約束及解決方案)。

---
## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題陳述：每月手動處理200+張發票已達極限

### Section 2 (0:45–1:30)
> 文件上傳：檔案放置即自動開始處理

### Section 3 (1:30–2:30)
> OCR與擷取：OCR + AI進行文件分類和欄位擷取

### Section 4 (2:30–3:45)
> 結構化輸出：即時可用的結構化資料

### Section 5 (3:45–5:00)
> 驗證與報告：信賴度評估明確需人工確認的項目

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (OCR Processor) | Textract文件文字擷取 |
| Lambda (Entity Extractor) | Bedrock實體擷取 |
| Lambda (Classifier) | 文件類型分類 |
| Amazon Athena | 擷取資料彙總分析 |

---

*本文件是技術演示影片的製作指南。*
