# BIM 模型變更偵測與安全合規檢查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示 BIM 模型變更偵測與安全合規自動檢查流程。設計變更時自動偵測安全標準違規。

**核心訊息**: BIM 模型變更時自動偵測安全違規，在設計階段提前消除風險。

**預計時間**: 3–5 min

---

## 輸出目標: 透過 OutputDestination 選擇 (Pattern B)

此 UC 支援 `OutputDestination` 參數 (2026-05-10 更新,
請參閱 `docs/output-destination-patterns.md`)。

**兩種模式**:

- **STANDARD_S3** (預設): AI 產物進入新的 S3 儲存貯體
- **FSXN_S3AP** ("no data movement"): AI 產物透過 S3 Access Point 返回相同的
  FSx ONTAP 磁碟區, SMB/NFS 使用者可在現有目錄結構中檢視

```bash
# FSXN_S3AP 模式
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 規格約束與解決方案請參閱
[README.zh-TW.md — AWS 規格約束](../../README.zh-TW.md#aws-規格約束及解決方案)。

---
## Workflow

```
BIM 檔案上傳 → 變更偵測 → 安全規範比對 → 違規檢出 → 合規報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：每次設計變更都手動安全審查效率低下

### Section 2 (0:45–1:30)
> BIM 上傳：放置變更模型檔案啟動檢查

### Section 3 (1:30–2:30)
> 變更偵測與規範比對：自動 diff 分析和安全標準對照

### Section 4 (2:30–3:45)
> 違規確認：檢出的安全違規清單及嚴重程度

### Section 5 (3:45–5:00)
> 合規報告：包含改善建議的綜合報告產生

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Change Detector) | BIM 模型變更偵測 |
| Lambda (Rule Matcher) | 安全規範比對引擎 |
| Lambda (Report Generator) | 合規報告產生 |
| Amazon Athena | 違規歷史彙總分析 |

---

*本文件是技術演示影片的製作指南。*
