# UC21: 农业与食品 — 农田航拍图像分析 / 溯源文档管理

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

利用 FSx for ONTAP S3 Access Points，分析农田无人机/航拍图像以监测作物健康状况，并自动化溯源文档的结构化数据提取和批次分类的无服务器工作流。

### 主要功能

- 通过 S3 AP 自动检测 GeoTIFF/JPEG 图像（含 GPS 元数据，最大 500MB）
- Rekognition + Bedrock 植被指数分析和异常分类（置信度 ≥ 0.70）
- Textract + Comprehend 溯源文档提取和批次分类（置信度 ≥ 0.80）

## Success Metrics

| 指标 | 目标值 |
|------|--------|
| 作物异常检测准确率 | ≥ 70% |
| 溯源分类率 | ≥ 80% |
| 地理位置验证率 | ≥ 90% |

## 治理说明

> 本模式提供技术架构指导，不构成法律、合规或监管建议。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。使用 MapConcurrency=10 进行并行处理时可能影响同一卷上的其他工作负载。
- 进行大规模批量处理时，请检查 FSx for ONTAP 的 Throughput Capacity (MBps) 并相应调整 MapConcurrency。
- 建议：在生产环境中从 MapConcurrency=5 开始，监控 CloudWatch 指标 (ThroughputUtilization)，然后逐步增加。

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（请求不会路由到 FSx 数据平面）。请使用 VPC-origin S3 AP 或配置 NAT Gateway 访问。详见 [S3AP 兼容性说明](../docs/s3ap-compatibility-notes.md)。

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
