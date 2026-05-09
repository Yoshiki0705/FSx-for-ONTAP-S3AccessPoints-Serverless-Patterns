# VFX算圖品質檢查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了VFX算圖輸出的品質檢查管線。透過自動影格驗證實現偽影和錯誤影格的早期偵測。

**核心訊息**: 自動驗證大量算圖影格，即時偵測品質問題並加速重新算圖決策。

**預計時間**: 3-5 min

---

## Workflow

```
算圖輸出(EXR/PNG) -> 影格分析/中繼資料擷取 -> 品質判定/異常偵測 -> QC報告(按鏡頭)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 問題陳述：數千影格的目視檢查不切實際

### Section 2 (0:45-1:30)
> 管線觸發：算圖完成自動啟動QC

### Section 3 (1:30-2:30)
> 影格分析：像素統計定量評估影格品質

### Section 4 (2:30-3:45)
> 品質評估：自動分類和識別問題影格

### Section 5 (3:45-5:00)
> QC報告：即時支援重新算圖決策

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Frame Analyzer) | 影格中繼資料/像素統計擷取 |
| Lambda (Quality Checker) | 統計品質判定 |
| Lambda (Report Generator) | 透過Bedrock產生QC報告 |
| Amazon Athena | 影格統計彙總分析 |

---

*本文件是技術演示影片的製作指南。*
