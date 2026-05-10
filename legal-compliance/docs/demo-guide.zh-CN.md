# 文件服务器权限审计 — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示了自动检测文件服务器过度访问权限的审计工作流。分析NTFS ACL，识别违反最小权限原则的条目，并自动生成合规报告。

**核心信息**: 将需要数周的文件服务器权限审计自动化，即时可视化过度权限风险。

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
> 问题陈述：手动审计数千个文件夹的权限不切实际

### Section 2 (0:45–1:30)
> 工作流触发：指定目标卷并启动审计

### Section 3 (1:30–2:30)
> ACL分析：自动收集ACL并检测策略违规

### Section 4 (2:30–3:45)
> 结果审查：即时掌握违规数量和风险等级

### Section 5 (3:45–5:00)
> 合规报告：自动生成包含优先级操作的审计报告

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (ACL Collector) | NTFS ACL元数据收集 |
| Lambda (Policy Checker) | 策略违规规则匹配 |
| Lambda (Report Generator) | 通过Bedrock生成审计报告 |
| Amazon Athena | 违规数据SQL分析 |

---

*本文档是技术演示视频的制作指南。*
