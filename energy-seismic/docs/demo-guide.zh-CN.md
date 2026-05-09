# 测井异常检测与合规报告 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示测井数据的异常检测与合规报告流水线。从传感器数据中自动检测异常模式并生成合规报告。

**核心信息**: 自动检测测井数据中的异常模式，即时生成合规报告。

**预计时间**: 3–5 min

---

## Workflow

```
测井数据采集 → 信号预处理 → 异常检测 → 法规匹配 → 合规报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：从大量测井数据中手动查找异常效率低下

### Section 2 (0:45–1:30)
> 数据上传：放置测井日志文件启动分析

### Section 3 (1:30–2:30)
> 异常检测：AI 驱动模式分析自动检出异常区间

### Section 4 (2:30–3:45)
> 结果确认：检出的异常列表及严重程度分类

### Section 5 (3:45–5:00)
> 合规报告：法规标准对照结果及整改建议

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Signal Processor) | 测井信号预处理 |
| Lambda (Anomaly Detector) | AI 驱动异常检测 |
| Lambda (Compliance Checker) | 法规标准对照 |
| Amazon Athena | 异常历史聚合分析 |

---

*本文档是技术演示视频的制作指南。*
