# 事故照片損害評估與理賠報告 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | 繁體中文 | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示基於事故照片的損害評估與自動理賠報告產生流程。AI 分析照片中的損傷程度並自動產生理賠報告。

**核心訊息**: AI 自動分析事故照片中的損傷，即時產生理賠報告並縮短處理時間。

**預計時間**: 3–5 min

---

## Workflow

```
事故照片上傳 → 損傷區域偵測 → 嚴重程度評估 → 費用估算 → 理賠報告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 問題提出：基於事故照片的手動損害評估耗時長

### Section 2 (0:45–1:30)
> 照片上傳：放置事故現場照片啟動評估

### Section 3 (1:30–2:30)
> AI 損傷分析：自動偵測損傷區域並分類嚴重程度

### Section 4 (2:30–3:45)
> 評估結果：各損傷部位費用估算和綜合評估

### Section 5 (3:45–5:00)
> 理賠報告：自動產生的理賠報告及處理建議

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流程編排 |
| Lambda (Damage Detector) | AI 驅動損傷區域偵測 |
| Lambda (Severity Assessor) | 損傷嚴重程度評估 |
| Lambda (Cost Estimator) | 維修費用估算 |
| Amazon Athena | 理賠歷史彙總分析 |

---

*本文件是技術演示影片的製作指南。*
