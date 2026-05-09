# 测序 QC 与变异聚合 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示基因组测序数据的质量控制（QC）与变异聚合流水线。自动验证大量测序结果并生成变异统计。

**核心信息**: 自动验证测序数据质量并聚合变异，让研究人员专注于分析。

**预计时间**: 3–5 min

---

## Workflow

```
FASTQ 上传 → QC 验证 → 变异调用 → 统计聚合 → QC 报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：大量测序数据的手动 QC 耗时费力

### Section 2 (0:45–1:30)
> 数据上传：放置 FASTQ 文件启动流水线

### Section 3 (1:30–2:30)
> QC 与变异分析：自动质量验证和变异调用执行

### Section 4 (2:30–3:45)
> 结果确认：查看 QC 指标和变异统计

### Section 5 (3:45–5:00)
> QC 报告：综合质量报告及后续分析建议

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (QC Validator) | 测序质量验证 |
| Lambda (Variant Caller) | 变异调用执行 |
| Lambda (Stats Aggregator) | 变异统计聚合 |
| Amazon Athena | QC 指标分析 |

---

*本文档是技术演示视频的制作指南。*
