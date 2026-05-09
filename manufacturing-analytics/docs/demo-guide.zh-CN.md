# IoT传感器异常检测与质量检查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了从制造线IoT传感器数据中自动检测异常并生成质量检查报告的工作流。

**核心信息**: 自动检测传感器数据中的异常模式，实现质量问题的早期发现和预防性维护。

**预计时间**: 3-5 min

---

## Workflow

```
传感器数据(CSV/Parquet) -> 预处理/标准化 -> 异常检测/统计分析 -> 质量报告(AI)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 问题陈述：阈值告警无法捕捉真正的异常

### Section 2 (0:45-1:30)
> 数据采集：数据积累自动启动分析

### Section 3 (1:30-2:30)
> 异常检测：统计方法仅检测显著异常

### Section 4 (2:30-3:45)
> 质量检查：在产线/工序级别定位问题区域

### Section 5 (3:45-5:00)
> 报告与行动：AI提出根本原因候选和对策

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Data Preprocessor) | 传感器数据标准化 |
| Lambda (Anomaly Detector) | 统计异常检测 |
| Lambda (Report Generator) | 通过Bedrock生成质量报告 |
| Amazon Athena | 异常数据聚合分析 |

---

*本文档是技术演示视频的制作指南。*
