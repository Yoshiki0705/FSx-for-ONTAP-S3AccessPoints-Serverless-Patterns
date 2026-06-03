# UC22: 运输与铁路 — 设备检查图像分析 / 维护报告管理

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **文档**: [架构图](docs/architecture.zh-CN.md) | [演示指南](docs/demo-guide.zh-CN.md)

## 概述

利用 FSx for ONTAP S3 Access Points，从铁路基础设施检查图像中检测劣化指标，分类严重程度，并自动生成维护优先级排名的无服务器工作流。**安全关键基础设施（桥梁、信号设备、轨道接头）使用更低的检测阈值，并要求人工审核。**

## Success Metrics

| 指标 | 目标值 |
|------|--------|
| 缺陷检测率（标准） | ≥ 85% |
| 缺陷检测率（安全关键） | ≥ 95% |
| 严重程度分类准确率 | ≥ 80% |
| 假阴性率（安全关键） | < 5% |

## 治理说明

> 本模式提供技术架构指导。AI 检测结果不是最终判断，需要合格工程师确认。

## ⚠️ 性能注意事项

- FSx for ONTAP 的吞吐量容量在 **NFS/SMB/S3 AP 之间共享**。使用 MapConcurrency=10 进行并行处理时可能影响同一卷上的其他工作负载。
- 进行大规模批量处理时，请检查 FSx ONTAP 的 Throughput Capacity (MBps) 并相应调整 MapConcurrency。
- 建议：在生产环境中从 MapConcurrency=5 开始，监控 CloudWatch 指标 (ThroughputUtilization)，然后逐步增加。

> **S3 AP NetworkOrigin 注意**: Discovery Lambda 部署在 VPC 内。如果 S3 Access Point 的 NetworkOrigin 为 `Internet`，则无法通过 S3 Gateway VPC Endpoint 访问（请求不会路由到 FSx 数据平面）。请使用 VPC-origin S3 AP 或配置 NAT Gateway 访问。详见 [S3AP 兼容性说明](../docs/s3ap-compatibility-notes.md)。

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
