# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

一种无侵入式收集并分析由 **SIOS LifeKeeper** 构建的高可用 (HA) 集群日志与故障转移事件的无服务器模式，数据通过 **Amazon FSx for NetApp ONTAP** 的 S3 Access Points 采集。

借助 Amazon Bedrock (Nova Pro) 提供的**根因分析 (Root Cause Analysis)** 与**集群健康评分**，实现故障转移的快速原因定位与征兆检测。

---

## 设想场景

在企业环境中，SAP、Oracle 及核心业务应用由 SIOS LifeKeeper 进行 HA 保护，并使用 FSx for ONTAP Multi-AZ 作为共享存储。

**挑战**：
- 故障转移发生时的根因定位耗时较长
- LifeKeeper 日志分析多为手工作业，依赖个人经验
- 在 HA 集群节点上添加监控代理会增加故障点
- 存储层 (FSx for ONTAP) 与应用层 (LifeKeeper) 的故障区分困难

**解决方案**：
使用 FSx for ONTAP S3 Access Points，将 LifeKeeper 写入的日志**无侵入式**地由无服务器分析管道处理。通过 AI 自动分析降低运维负担。

---

## SIOS LifeKeeper + FSx for ONTAP 组合

### 架构中的定位

| 层 | 职责 | HA 提供范围 |
|---------|------|------------|
| 存储 | FSx for ONTAP Multi-AZ | 数据可用性、AZ 冗余、自动故障转移 |
| 应用 | SIOS LifeKeeper | VIP 控制、服务监控、自动恢复 |
| 分析（本模式） | S3 AP + 无服务器 + Bedrock | 无侵入式日志分析、AI 根因分析 |

### 什么是 SIOS LifeKeeper

由 SIOS Technology 公司提供的面向 Linux/Windows 的 HA 集群软件。在 AWS 上实现关键任务应用的高可用性。

**主要特性**：
- 应用感知型 Recovery Kit（直接监控 SAP S/4HANA、Oracle、NFS、IP 等）
- 跨 AZ 故障转移（单一区域内 2 个 AZ）
- VIP 管理（Elastic IP / Secondary IP）
- 通过通信路径冗余防止脑裂
- 作为 AWS Partner Solution 正式提供

**实绩**：Astro Malaysia 公司在 SAP + Oracle on AWS 环境中采用 SIOS LifeKeeper，实现了 99.99% 的可用性。

### FSx for ONTAP 共享磁盘支持 (V10 及以后)

自 LifeKeeper V10.0.1 起，可将 FSx for ONTAP 作为共享磁盘直接保护。以往仅支持 DataKeeper（块复制），新增共享磁盘配置后可实现更简单的 HA 架构。

| 协议 | 所需的 Recovery Kit | 备注 |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | 在 AWS 上使用 FSx for ONTAP 时必需 |
| NFS | NAS Recovery Kit | 标准的 NFS 共享磁盘配置 |

> SIOS bcblog 的验证文章 (2026-05-08) 确认，在 RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) 的配置下切换 (switchover) 可正常工作。

### FSx for ONTAP 带来的价值

- **Multi-AZ 共享存储**：可从 LifeKeeper 的两个节点通过 NFS/iSCSI 访问
- **自动存储故障转移**：自动处理存储层的 AZ 故障
- **Snapshot**：保全故障转移前后的数据状态
- **S3 Access Points**：用于日志分析的无侵入式数据访问路径
- **多协议**：从单个卷同时提供 SMB + NFS + iSCSI + S3 API，避免数据重复保存
- **云原生**：可从 AWS Management Console 直接开始使用（无需额外许可证）

> “不是将数据复制到 S3 后再使用，而是能够通过 S3 API 直接利用 FSx for ONTAP 上的数据，这是一大优势” — 摘自 [SIOS bcblog 访谈文章](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### 公开参考资料

| 资料 | 发布方 | URL |
|------|--------|-----|
| 利用 SIOS LifeKeeper 与 Amazon FSx for NetApp ONTAP 的高可用解决方案 | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| 基于 NetApp ONTAP 与 LifeKeeper 的高可用设计 | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| 将 Amazon FSx for NetApp ONTAP 用作 LifeKeeper 的共享磁盘 | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## 功能

### Discovery Lambda
- 通过 FSx for ONTAP S3 AP 检出 LifeKeeper 日志文件
- 分类为故障转移事件 / 健康检查 / 配置变更 / Recovery Kit 日志
- 自动评估重要度（CRITICAL / HIGH / MEDIUM / LOW）

### Processing Lambda
- 检出 LifeKeeper 资源状态迁移（ISP→OSF、ISS→ISP 等）
- 通过 Bedrock (Nova Pro) 进行根因分析
- 计算集群健康评分（0-100 分）
- 区分存储层与应用层的故障

### Report Lambda
- 生成 Markdown 健康报告
- 基于重要度阈值发送 SNS 故障转移告警
- 附带 LifeKeeper 命令（`lcdstatus`、通信路径确认）的建议操作

---

## 部署

### 前提条件

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP 文件系统 + S3 Access Point（DemoMode=true 时无需）
- 已启用 Bedrock 模型访问（Amazon Nova Pro）

### 快速部署

```bash
# 以 DemoMode 部署 (无需 FSx for ONTAP)
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **注意**：`template.yaml` 用于 SAM CLI（`sam build` + `sam deploy`）。
> 若使用 `aws cloudformation deploy` 命令直接部署，请改用 `template-deploy.yaml`（需要事先打包 Lambda zip 文件并上传至 S3）。

### 生产部署

```bash
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### 参数

| 参数 | 默认值 | 说明 |
|-----------|-----------|------|
| S3AccessPointAlias | (必填) | FSx for ONTAP S3 AP 别名 |
| DemoMode | false | 启用演示模式 |
| ScheduleExpression | rate(5 minutes) | 监控间隔 |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | apac.amazon.nova-pro-v1:0 | 分析用 Bedrock 模型 |
| FailoverAlertSeverity | CRITICAL | SNS 告警最低重要度 |
| ClusterName | lifekeeper-cluster | LifeKeeper 集群名称 |
| OutputDestination | STANDARD_S3 | 报告输出目标 |
| LogRetentionInDays | 90 | CloudWatch Logs 保留期限 |

---

## 测试

```bash
# 单元测试
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# DemoMode 下的端到端测试
# (事先在演示用 S3 存储桶中放置示例日志)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## 健康评分

| 评分 | 级别 | 含义 | 建议操作 |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | 正常 | 查看定期报告 |
| 70-89 | WARNING | 注意 | 确认通信路径、存储 I/O |
| 50-69 | DEGRADED | 劣化 | 用 LifeKeeper GUI/CLI 确认状态，监控 FSx for ONTAP |
| 0-49 | CRITICAL | 危险 | 立即响应。用 `lcdstatus` + ONTAP 管理 CLI 确认状态 |

---

## 目录结构

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM 模板
├── samconfig.toml.example     # 部署配置示例
├── README.md                  # 本文档 (日语)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper 日志检出
│   ├── processing/
│   │   └── handler.py         # Bedrock 根因分析
│   └── report/
│       └── handler.py         # 报告生成、告警
├── statemachine/
│   └── workflow.asl.json      # Step Functions 定义
├── docs/
│   ├── architecture.md        # 架构详情
│   └── demo-guide.md          # 演示指南 (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # 单元测试
```

---

## 相关模式

| 模式 | 关联性 |
|---------|--------|
| `solutions/sap/erp-adjacent/` | 受 LifeKeeper 保护的 SAP 环境的 IDoc/批处理 |
| `solutions/event-driven/fpolicy/` | 通过 FPolicy 事件驱动的即时日志检测 |
| `solutions/flexcache/anycast-dr/` | 多区域 DR 配置的参考 |

---

## Governance Note

本模式旨在为 HA 集群的**运维监控提供辅助**，请注意以下几点：

- AI 分析结果为运维判断的**参考信息**，不执行自动故障转移控制或恢复操作
- LifeKeeper 的配置变更必须通过 LifeKeeper GUI/CLI 进行
- 故障转移判断应委托给 LifeKeeper 自身的健康检查机制
- 本模式是以 **Human-in-the-loop** 为前提的设计

---

## Performance Considerations

- **监控间隔**：5 分钟间隔下会产生最多 5 分钟的检测延迟。若需要即时性，可通过 `TriggerMode=HYBRID` 并用 FPolicy 事件驱动
- **日志大小**：当日志文件数量庞大时，用 `MaxFilesPerExecution` 控制批大小
- **Bedrock 成本**：在故障转移频发的环境中，需注意 Bedrock 调用成本。用 `FailoverAlertSeverity` 缩小分析对象
- **S3 AP 吞吐量**：FSx for ONTAP S3 AP 共享整个文件系统的带宽。为避免大量日志读取影响业务 I/O，也可考虑基于 Snapshot 的读取

---

## License

MIT
