# 自动驾驶数据预处理流水线 -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本演示展示自动驾驶传感器数据的预处理与标注流水线。自动分类大规模驾驶数据并生成训练数据集。

**核心信息**: 自动预处理大规模驾驶传感器数据，生成可直接用于 AI 训练的标注数据集。

**预计时间**: 3–5 min

---

## Workflow

```
传感器数据采集 → 格式转换 → 帧分类 → 标注生成 → 数据集报告
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> 问题提出：大规模驾驶数据的手动预处理是瓶颈

### Section 2 (0:45–1:30)
> 数据上传：放置传感器日志文件启动流水线

### Section 3 (1:30–2:30)
> 预处理与分类：自动格式转换和 AI 驱动帧分类

### Section 4 (2:30–3:45)
> 标注结果：查看生成的标签数据和质量统计

### Section 5 (3:45–5:00)
> 数据集报告：训练就绪报告及质量指标

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | 工作流编排 |
| Lambda (Python 3.13) | 传感器数据质量验证、场景分类、目录生成 |
| Lambda SnapStart | 冷启动减少（`EnableSnapStart=true` 可选启用） |
| SageMaker (4-way routing) | 推理（Batch / Serverless / Provisioned / Inference Components） |
| SageMaker Inference Components | 真正的 scale-to-zero（`EnableInferenceComponents=true`） |
| Amazon Bedrock | 场景分类 / 标注建议 |
| Amazon Athena | 元数据搜索与聚合 |
| CloudFormation Guard Hooks | 部署时安全策略强制 |

### 本地测试 (Phase 6A)

```bash
# 使用 SAM CLI 进行本地测试
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

---

*本文档是技术演示视频的制作指南。*
