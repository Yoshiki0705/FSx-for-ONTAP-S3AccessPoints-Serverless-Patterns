# 商品图片标签与目录元数据生成 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示商品图片的自动标签与目录元数据生成流水线。AI 分析商品照片自动生成属性标签和描述。

**核心信息**: AI 自动从商品图片中提取属性，即时生成目录元数据并加速商品上架。

**预计时间**: 3–5 min

---

## 输出目标: 通过 OutputDestination 选择 (Pattern B)

该 UC 支持 `OutputDestination` 参数 (2026-05-10 更新,
参见 `docs/output-destination-patterns.md`)。

**两种模式**:

- **STANDARD_S3** (默认): AI 工件进入新的 S3 存储桶
- **FSXN_S3AP** ("no data movement"): AI 工件通过 S3 Access Point 返回同一的
  FSx ONTAP 卷, SMB/NFS 用户可在现有目录结构中查看

```bash
# FSXN_S3AP 模式
--parameter-overrides OutputDestination=FSXN_S3AP OutputS3APPrefix=ai-outputs/
```

AWS 规格约束和解决方案请参阅
[README.zh-CN.md — AWS 规格约束](../../README.zh-CN.md#aws-规格约束及解决方案)。

---
## Workflow

```
商品图片上传 → 视觉分析 → 属性标签 → 描述生成 → 目录报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：数千商品的手动标签和描述编写是瓶颈

### Section 2 (0:45–1:30)
> 图片上传：放置商品照片启动处理

### Section 3 (1:30–2:30)
> AI 分析与标签：视觉 AI 自动提取颜色、材质、类别等

### Section 4 (2:30–3:45)
> 元数据生成：自动生成商品描述和搜索关键词

### Section 5 (3:45–5:00)
> 目录报告：处理完成统计及质量验证结果

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Image Analyzer) | AI 驱动视觉分析 |
| Lambda (Tag Generator) | 属性标签生成 |
| Lambda (Description Writer) | 商品描述自动生成 |
| Amazon Athena | 目录统计分析 |

---

*本文档是技术演示视频的制作指南。*
