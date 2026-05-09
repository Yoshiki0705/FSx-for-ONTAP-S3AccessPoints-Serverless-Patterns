# DICOM 匿名化工作流 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示医学影像（DICOM）文件的自动匿名化流水线。通过移除患者身份信息，实现安全的研究数据共享。

**核心信息**: 自动移除 DICOM 文件中的患者信息，在合规前提下安全共享研究数据。

**预计时间**: 3–5 min

---

## Workflow

```
DICOM 上传 → 元数据提取 → PHI 检测 → 匿名化处理 → 验证报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：研究数据共享时必须遵守患者隐私保护法规

### Section 2 (0:45–1:30)
> 文件上传：放置 DICOM 文件即可启动自动处理

### Section 3 (1:30–2:30)
> PHI 检测与匿名化：AI 驱动的隐私信息检测与自动脱敏

### Section 4 (2:30–3:45)
> 结果确认：查看匿名化完成文件及处理统计

### Section 5 (3:45–5:00)
> 验证报告：生成合规验证报告并批准数据共享

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (DICOM Parser) | DICOM 元数据提取 |
| Lambda (PHI Detector) | AI 驱动隐私信息检测 |
| Lambda (Anonymizer) | 匿名化处理执行 |
| Amazon Athena | 处理结果聚合分析 |

---

*本文档是技术演示视频的制作指南。*
