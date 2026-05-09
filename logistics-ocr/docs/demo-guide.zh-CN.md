# 运单 OCR 与库存分析 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示运单的 OCR 处理与库存分析流水线。自动数字化纸质运单，实时掌握库存状况。

**核心信息**: 自动 OCR 处理运单，实时更新库存数据并提升物流效率。

**预计时间**: 3–5 min

---

## Workflow

```
运单扫描上传 → OCR 文本提取 → 字段解析 → 库存更新 → 分析报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：纸质运单的手动录入容易出错且耗时

### Section 2 (0:45–1:30)
> 运单上传：放置扫描运单图像启动处理

### Section 3 (1:30–2:30)
> OCR 与解析：文本提取和结构化数据转换

### Section 4 (2:30–3:45)
> 库存更新：基于提取数据实时更新库存

### Section 5 (3:45–5:00)
> 分析报告：物流现状仪表板及异常检测告警

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (OCR Engine) | 运单文本提取 |
| Lambda (Field Parser) | 结构化数据解析 |
| Lambda (Inventory Updater) | 库存数据更新 |
| Amazon Athena | 物流统计分析 |

---

*本文档是技术演示视频的制作指南。*
