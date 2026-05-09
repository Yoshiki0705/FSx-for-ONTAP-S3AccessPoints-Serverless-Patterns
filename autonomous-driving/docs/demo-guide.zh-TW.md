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
| Lambda (Python 3.13) | 感測器資料品質驗證、場景分類、目錄產生 |
| Lambda SnapStart | 冷啟動減少（`EnableSnapStart=true` 可選啟用） |
| SageMaker (4-way routing) | 推論（Batch / Serverless / Provisioned / Inference Components） |
| SageMaker Inference Components | 真正的 scale-to-zero（`EnableInferenceComponents=true`） |
| Amazon Bedrock | 場景分類 / 標註建議 |
| Amazon Athena | 中繼資料搜尋與彙總 |
| CloudFormation Guard Hooks | 部署時安全策略強制 |

### 本機測試 (Phase 6A)

```bash
# 使用 SAM CLI 進行本機測試
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

---

*本文件是技術演示影片的製作指南。*
