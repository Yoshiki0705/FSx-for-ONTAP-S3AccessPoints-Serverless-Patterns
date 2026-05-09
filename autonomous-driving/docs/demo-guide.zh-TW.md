# 自動駕駛資料前處理流程 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示自動駕駛感測器資料的前處理與標註流程。自動分類大規模駕駛資料並產生訓練資料集。

**核心訊息**: 自動前處理大規模駕駛感測器資料，產生可直接用於 AI 訓練的標註資料集。

**預計時間**: 3–5 min

---

## Workflow

```
感測器資料收集 → 格式轉換 → 影格分類 → 標註產生 → 資料集報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：大規模駕駛資料的手動前處理是瓶頸

### Section 2 (0:45–1:30)
> 資料上傳：放置感測器日誌檔案啟動流程

### Section 3 (1:30–2:30)
> 前處理與分類：自動格式轉換和 AI 驅動影格分類

### Section 4 (2:30–3:45)
> 標註結果：查看產生的標籤資料和品質統計

### Section 5 (3:45–5:00)
> 資料集報告：訓練就緒報告及品質指標

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Format Converter) | 感測器資料格式轉換 |
| Lambda (Frame Classifier) | AI 驅動影格分類 |
| Lambda (Annotation Generator) | 標註自動產生 |
| Amazon Athena | 資料集統計分析 |

---

*本文件是技術演示影片的製作指南。*
