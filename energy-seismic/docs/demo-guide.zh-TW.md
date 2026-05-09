# 測井異常偵測與合規報告 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示測井資料的異常偵測與合規報告流程。從感測器資料中自動偵測異常模式並產生合規報告。

**核心訊息**: 自動偵測測井資料中的異常模式，即時產生合規報告。

**預計時間**: 3–5 min

---

## Workflow

```
測井資料收集 → 訊號前處理 → 異常偵測 → 法規比對 → 合規報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：從大量測井資料中手動查找異常效率低下

### Section 2 (0:45–1:30)
> 資料上傳：放置測井日誌檔案啟動分析

### Section 3 (1:30–2:30)
> 異常偵測：AI 驅動模式分析自動檢出異常區間

### Section 4 (2:30–3:45)
> 結果確認：檢出的異常清單及嚴重程度分類

### Section 5 (3:45–5:00)
> 合規報告：法規標準對照結果及改善建議

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Signal Processor) | 測井訊號前處理 |
| Lambda (Anomaly Detector) | AI 驅動異常偵測 |
| Lambda (Compliance Checker) | 法規標準對照 |
| Amazon Athena | 異常歷史彙總分析 |

---

*本文件是技術演示影片的製作指南。*
