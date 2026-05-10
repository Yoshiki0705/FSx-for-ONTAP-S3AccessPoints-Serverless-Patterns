# VFX渲染质量检查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了VFX渲染输出的质量检查管道。通过自动帧验证实现伪影和错误帧的早期检测。

**核心信息**: 自动验证大量渲染帧，即时检测质量问题并加速重新渲染决策。

**预计时间**: 3-5 min

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

```
渲染输出(EXR/PNG) -> 帧分析/元数据提取 -> 质量判定/异常检测 -> QC报告(按镜头)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> 问题陈述：数千帧的目视检查不切实际

### Section 2 (0:45-1:30)
> 管道触发：渲染完成自动启动QC

### Section 3 (1:30-2:30)
> 帧分析：像素统计定量评估帧质量

### Section 4 (2:30-3:45)
> 质量评估：自动分类和识别问题帧

### Section 5 (3:45-5:00)
> QC报告：即时支持重新渲染决策

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Frame Analyzer) | 帧元数据/像素统计提取 |
| Lambda (Quality Checker) | 统计质量判定 |
| Lambda (Report Generator) | 通过Bedrock生成QC报告 |
| Amazon Athena | 帧统计聚合分析 |

---

*本文档是技术演示视频的制作指南。*
