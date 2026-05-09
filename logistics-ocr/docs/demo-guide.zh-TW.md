# 出貨單 OCR 與庫存分析 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示出貨單的 OCR 處理與庫存分析流程。自動數位化紙本出貨單，即時掌握庫存狀況。

**核心訊息**: 自動 OCR 處理出貨單，即時更新庫存資料並提升物流效率。

**預計時間**: 3–5 min

---

## Workflow

```
出貨單掃描上傳 → OCR 文字擷取 → 欄位解析 → 庫存更新 → 分析報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：紙本出貨單的手動輸入容易出錯且耗時

### Section 2 (0:45–1:30)
> 出貨單上傳：放置掃描出貨單影像啟動處理

### Section 3 (1:30–2:30)
> OCR 與解析：文字擷取和結構化資料轉換

### Section 4 (2:30–3:45)
> 庫存更新：基於擷取資料即時更新庫存

### Section 5 (3:45–5:00)
> 分析報告：物流現況儀表板及異常偵測告警

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (OCR Engine) | 出貨單文字擷取 |
| Lambda (Field Parser) | 結構化資料解析 |
| Lambda (Inventory Updater) | 庫存資料更新 |
| Amazon Athena | 物流統計分析 |

---

*本文件是技術演示影片的製作指南。*
