# Life Sciences Research — 数据分类与元数据提取

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

生命科学研究数据（显微镜图像、序列数据、研究论文）的自动分类和元数据提取管道。利用 FlexCache 实现多站点研究数据共享。

## 解决的问题

| 问题 | 解决方案 |
|------|----------|
| 文件服务器上未整理的研究数据 | 按数据类型自动分类 |
| 手动元数据编目 | AI 驱动的元数据提取 |
| 远程研究站点数据访问缓慢 | FlexCache 多站点共享 |
| 难以找到相关数据集 | 可搜索的元数据目录 |

## 支持的数据格式

| 类别 | 格式 | 描述 |
|------|------|------|
| 显微镜图像 | .tiff, .nd2, .czi | 荧光、共聚焦、电子显微镜 |
| 序列数据 | .fastq, .bam, .vcf | NGS 测序结果 |
| 研究论文 | .pdf | 文献、方案、报告 |
| 结构数据 | .pdb, .cif | 蛋白质结构 |

## FlexCache 的作用

- **多站点共享**: 总部 → 各研究站点
- **大型数据集**: 缓存显微镜图像（数百 GB）
- **协作**: 多个团队并行分析同一数据集

## 成功指标

| 指标 | 目标 |
|------|------|
| 每次执行分类的文件数 | > 500 文件 |
| 分类准确率 | > 85% |
| 元数据提取成功率 | > 90% |
| 每文件处理时间 | < 5 秒 |
| Human Review 比率 | < 10%（低置信度分类） |

---

## 部署

使用 AWS SAM CLI 部署（请将占位符替换为您的环境值）：

```bash
# 前提条件：需要 AWS SAM CLI。'sam build' 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-life-sciences-research \
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
