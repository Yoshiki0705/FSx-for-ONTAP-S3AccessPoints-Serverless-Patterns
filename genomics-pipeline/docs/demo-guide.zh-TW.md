# 定序 QC 與變異彙總 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示基因體定序資料的品質管控（QC）與變異彙總流程。自動驗證大量定序結果並產生變異統計。

**核心訊息**: 自動驗證定序資料品質並彙總變異，讓研究人員專注於分析。

**預計時間**: 3–5 min

---

## Workflow

```
FASTQ 上傳 → QC 驗證 → 變異呼叫 → 統計彙總 → QC 報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：大量定序資料的手動 QC 耗時費力

### Section 2 (0:45–1:30)
> 資料上傳：放置 FASTQ 檔案啟動流程

### Section 3 (1:30–2:30)
> QC 與變異分析：自動品質驗證和變異呼叫執行

### Section 4 (2:30–3:45)
> 結果確認：查看 QC 指標和變異統計

### Section 5 (3:45–5:00)
> QC 報告：綜合品質報告及後續分析建議

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (QC Validator) | 定序品質驗證 |
| Lambda (Variant Caller) | 變異呼叫執行 |
| Lambda (Stats Aggregator) | 變異統計彙總 |
| Amazon Athena | QC 指標分析 |

---

*本文件是技術演示影片的製作指南。*
