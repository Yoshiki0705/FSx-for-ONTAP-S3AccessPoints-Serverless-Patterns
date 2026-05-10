# IoT感測器異常偵測與品質檢查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了從製造線IoT感測器資料中自動偵測異常並產生品質檢查報告的工作流程。

**核心訊息**: 自動偵測感測器資料中的異常模式，實現品質問題的早期發現和預防性維護。

**預計時間**: 3-5 min

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

```
感測器資料(CSV/Parquet) -> 前處理/標準化 -> 異常偵測/統計分析 -> 品質報告(AI)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 問題陳述：閾值告警無法捕捉真正的異常

### Section 2 (0:45-1:30)
> 資料採集：資料累積自動啟動分析

### Section 3 (1:30-2:30)
> 異常偵測：統計方法僅偵測顯著異常

### Section 4 (2:30-3:45)
> 品質檢查：在產線/工序級別定位問題區域

### Section 5 (3:45-5:00)
> 報告與行動：AI提出根本原因候選和對策

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Data Preprocessor) | 感測器資料標準化 |
| Lambda (Anomaly Detector) | 統計異常偵測 |
| Lambda (Report Generator) | 透過Bedrock產生品質報告 |
| Amazon Athena | 異常資料彙總分析 |

---

*本文件是技術演示影片的製作指南。*
