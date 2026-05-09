# BIM 模型变更检测与安全合规检查 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示 BIM 模型变更检测与安全合规自动检查流水线。设计变更时自动检测安全标准违规。

**核心信息**: BIM 模型变更时自动检测安全违规，在设计阶段提前消除风险。

**预计时间**: 3–5 min

---

## Workflow

```
BIM 文件上传 → 变更检测 → 安全规范匹配 → 违规检出 → 合规报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：每次设计变更都手动安全审查效率低下

### Section 2 (0:45–1:30)
> BIM 上传：放置变更模型文件启动检查

### Section 3 (1:30–2:30)
> 变更检测与规范匹配：自动 diff 分析和安全标准对照

### Section 4 (2:30–3:45)
> 违规确认：检出的安全违规列表及严重程度

### Section 5 (3:45–5:00)
> 合规报告：包含整改建议的综合报告生成

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Change Detector) | BIM 模型变更检测 |
| Lambda (Rule Matcher) | 安全规范匹配引擎 |
| Lambda (Report Generator) | 合规报告生成 |
| Amazon Athena | 违规历史聚合分析 |

---

*本文档是技术演示视频的制作指南。*
