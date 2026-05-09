# BIM 模型變更偵測與安全合規檢查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示 BIM 模型變更偵測與安全合規自動檢查流程。設計變更時自動偵測安全標準違規。

**核心訊息**: BIM 模型變更時自動偵測安全違規，在設計階段提前消除風險。

**預計時間**: 3–5 min

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
