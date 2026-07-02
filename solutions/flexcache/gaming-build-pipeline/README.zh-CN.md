# Gaming Build Pipeline — 资产质量检查与日志分析

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

面向游戏开发的自动资产质量检查和构建日志分析管道。利用 FlexCache 实现全球工作室资产共享和 CI/CD 管道集成。

## 解决的问题

| 问题 | 解决方案 |
|------|----------|
| 手动纹理/资产质量审查 | 基于 Rekognition 的自动质量检查 |
| 大型团队的构建日志分析 | AI 驱动的日志模式分析（Bedrock） |
| 向全球工作室分发资产缓慢 | FlexCache 全球资产交付 |
| 质量问题发现过晚 | 构建管道中的自动质量门控 |

## 支持的游戏引擎

| 引擎 | 资产格式 | 检查项目 |
|------|----------|----------|
| Unreal Engine 5 | .uasset, .umap | 纹理分辨率、LOD 设置 |
| Unity | .prefab, .asset | 网格顶点数、材质引用 |
| Godot | .tscn, .tres | 场景结构、资源引用 |

## FlexCache 的作用

- **全球资产交付**: 主工作室 → 区域工作室
- **构建缓存**: CI/CD 管道快速资产读取
- **版本管理**: 资产版本间增量交付

## 成功指标

| 指标 | 目标 |
|------|------|
| 每次执行检查的资产数 | > 1,000 |
| 质量检查通过率 | > 90% |
| 构建日志问题检测率 | 100%（已知模式） |
| 每资产处理时间 | < 2 秒 |
| Human Review 比率 | < 5%（严重质量不合格） |

---

## 部署

使用 AWS SAM CLI 部署（请将占位符替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-gaming-build-pipeline \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **注意**: `template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 如需使用原生 `aws cloudformation deploy` 部署，请改用 `template-deploy.yaml`（需要预先打包 Lambda zip 文件并上传到 S3 存储桶）。

## Governance Note

> 本模式提供技术架构指导。不构成法律、合规或监管建议。组织应咨询合格的专业人员。
