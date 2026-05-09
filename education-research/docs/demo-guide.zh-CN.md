# 论文分类与引用网络分析 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示学术论文的自动分类与引用网络分析流水线。对大量论文按主题分类并可视化引用关系。

**核心信息**: 通过 AI 自动分类大量学术论文并分析引用网络，即时掌握研究趋势。

**预计时间**: 3–5 min

---

## Workflow

```
论文上传 → 元数据提取 → AI 主题分类 → 引用网络构建 → 分析报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：手动分类数千篇论文并理清关系不现实

### Section 2 (0:45–1:30)
> 论文上传：放置 PDF 文件启动分析流水线

### Section 3 (1:30–2:30)
> AI 分类与网络构建：主题自动分类和引用关系提取

### Section 4 (2:30–3:45)
> 分析结果：主题聚类和核心论文识别

### Section 5 (3:45–5:00)
> 研究趋势报告：领域趋势分析及推荐论文列表

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (PDF Parser) | 论文元数据提取 |
| Lambda (Topic Classifier) | AI 驱动主题分类 |
| Lambda (Citation Analyzer) | 引用网络构建 |
| Amazon Athena | 研究趋势聚合分析 |

---

*本文档是技术演示视频的制作指南。*
