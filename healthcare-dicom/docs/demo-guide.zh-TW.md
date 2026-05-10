# DICOM 匿名化工作流程 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示醫學影像（DICOM）檔案的自動匿名化流程。透過移除病患識別資訊，實現安全的研究資料共享。

**核心訊息**: 自動移除 DICOM 檔案中的病患資訊，在合規前提下安全共享研究資料。

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

```
DICOM 上傳 → 中繼資料擷取 → PHI 偵測 → 匿名化處理 → 驗證報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：研究資料共享時必須遵守病患隱私保護法規

### Section 2 (0:45–1:30)
> 檔案上傳：放置 DICOM 檔案即可啟動自動處理

### Section 3 (1:30–2:30)
> PHI 偵測與匿名化：AI 驅動的隱私資訊偵測與自動遮蔽

### Section 4 (2:30–3:45)
> 結果確認：查看匿名化完成檔案及處理統計

### Section 5 (3:45–5:00)
> 驗證報告：產生合規驗證報告並核准資料共享

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (DICOM Parser) | DICOM 中繼資料擷取 |
| Lambda (PHI Detector) | AI 驅動隱私資訊偵測 |
| Lambda (Anonymizer) | 匿名化處理執行 |
| Amazon Athena | 處理結果彙總分析 |

---

*本文件是技術演示影片的製作指南。*
