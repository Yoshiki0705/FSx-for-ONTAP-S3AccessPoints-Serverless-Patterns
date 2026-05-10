# 合同·发票自动处理 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了合同和发票的自动处理管道。结合OCR文本提取和实体提取，从非结构化文档自动生成结构化数据。

**核心信息**: 自动数字化纸质合同和发票，即时提取和结构化金额、日期、供应商等关键信息。

**预计时间**: 3–5 min

---

## 输出目标: FSxN S3 Access Point (Pattern A)

该 UC 属于 **Pattern A: Native S3AP Output**
(参见 `docs/output-destination-patterns.md`)。

**设计**: 所有 AI/ML 工件通过 FSxN S3 Access Point 写回到与源数据**同一的 FSx ONTAP 卷**。
不创建单独的标准 S3 存储桶 ("no data movement" 模式)。

**CloudFormation 参数**:
- `S3AccessPointAlias`: 输入用 S3 AP Alias
- `S3AccessPointOutputAlias`: 输出用 S3 AP Alias (可以与输入相同)

AWS 规格约束和解决方案请参阅
[README.zh-CN.md — AWS 规格约束](../../README.zh-CN.md#aws-规格约束及解决方案)。

---
## Workflow



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题陈述：每月手动处理200+张发票已达极限

### Section 2 (0:45–1:30)
> 文档上传：文件放置即自动开始处理

### Section 3 (1:30–2:30)
> OCR与提取：OCR + AI进行文档分类和字段提取

### Section 4 (2:30–3:45)
> 结构化输出：即时可用的结构化数据

### Section 5 (3:45–5:00)
> 验证与报告：置信度评估明确需人工确认的项目

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (OCR Processor) | Textract文档文本提取 |
| Lambda (Entity Extractor) | Bedrock实体提取 |
| Lambda (Classifier) | 文档类型分类 |
| Amazon Athena | 提取数据聚合分析 |

---

*本文档是技术演示视频的制作指南。*
