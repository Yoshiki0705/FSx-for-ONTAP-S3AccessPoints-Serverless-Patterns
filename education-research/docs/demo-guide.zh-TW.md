# 論文分類與引用網路分析 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示學術論文的自動分類與引用網路分析流程。對大量論文按主題分類並視覺化引用關係。

**核心訊息**: 透過 AI 自動分類大量學術論文並分析引用網路，即時掌握研究趨勢。

**預計時間**: 3–5 min

---

## Workflow

```
論文上傳 → 中繼資料擷取 → AI 主題分類 → 引用網路建構 → 分析報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：手動分類數千篇論文並釐清關係不切實際

### Section 2 (0:45–1:30)
> 論文上傳：放置 PDF 檔案啟動分析流程

### Section 3 (1:30–2:30)
> AI 分類與網路建構：主題自動分類和引用關係擷取

### Section 4 (2:30–3:45)
> 分析結果：主題聚類和核心論文識別

### Section 5 (3:45–5:00)
> 研究趨勢報告：領域趨勢分析及推薦論文清單

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (PDF Parser) | 論文中繼資料擷取 |
| Lambda (Topic Classifier) | AI 驅動主題分類 |
| Lambda (Citation Analyzer) | 引用網路建構 |
| Amazon Athena | 研究趨勢彙總分析 |

---

*本文件是技術演示影片的製作指南。*
