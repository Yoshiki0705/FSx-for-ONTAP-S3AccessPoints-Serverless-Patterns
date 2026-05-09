# 商品圖片標籤與目錄中繼資料產生 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示商品圖片的自動標籤與目錄中繼資料產生流程。AI 分析商品照片自動產生屬性標籤和描述。

**核心訊息**: AI 自動從商品圖片中擷取屬性，即時產生目錄中繼資料並加速商品上架。

**預計時間**: 3–5 min

---

## Workflow

```
商品圖片上傳 → 視覺分析 → 屬性標籤 → 描述產生 → 目錄報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：數千商品的手動標籤和描述撰寫是瓶頸

### Section 2 (0:45–1:30)
> 圖片上傳：放置商品照片啟動處理

### Section 3 (1:30–2:30)
> AI 分析與標籤：視覺 AI 自動擷取顏色、材質、類別等

### Section 4 (2:30–3:45)
> 中繼資料產生：自動產生商品描述和搜尋關鍵字

### Section 5 (3:45–5:00)
> 目錄報告：處理完成統計及品質驗證結果

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Image Analyzer) | AI 驅動視覺分析 |
| Lambda (Tag Generator) | 屬性標籤產生 |
| Lambda (Description Writer) | 商品描述自動產生 |
| Amazon Athena | 目錄統計分析 |

---

*本文件是技術演示影片的製作指南。*
