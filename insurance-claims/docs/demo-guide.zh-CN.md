# 事故照片损害评估与理赔报告 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示基于事故照片的损害评估与自动理赔报告生成流水线。AI 分析照片中的损伤程度并自动生成理赔报告。

**核心信息**: AI 自动分析事故照片中的损伤，即时生成理赔报告并缩短处理时间。

**预计时间**: 3–5 min

---

## Workflow

```
事故照片上传 → 损伤区域检测 → 严重程度评估 → 费用估算 → 理赔报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：基于事故照片的手动损害评估耗时长

### Section 2 (0:45–1:30)
> 照片上传：放置事故现场照片启动评估

### Section 3 (1:30–2:30)
> AI 损伤分析：自动检测损伤区域并分类严重程度

### Section 4 (2:30–3:45)
> 评估结果：各损伤部位费用估算和综合评估

### Section 5 (3:45–5:00)
> 理赔报告：自动生成的理赔报告及处理建议

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Damage Detector) | AI 驱动损伤区域检测 |
| Lambda (Severity Assessor) | 损伤严重程度评估 |
| Lambda (Cost Estimator) | 维修费用估算 |
| Amazon Athena | 理赔历史聚合分析 |

---

*本文档是技术演示视频的制作指南。*
