# Automotive CAE — 仿真结果分析

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

## 概述

汽车 CAE（计算机辅助工程）仿真结果的自动分析管道。通过 S3 Access Points 从 FSx for ONTAP 读取求解器输出（LS-DYNA、STAR-CCM+、Nastran 等），自动化质量检查、统计汇总和报告生成。

## 解决的问题

| 问题 | 解决方案 |
|------|----------|
| 仿真结果的人工审查 | 自动质量检查 + AI 摘要 |
| 分散在文件服务器上的求解器输出 | 通过 S3 AP 集中发现 |
| 缺乏跨仿真分析 | Athena/Glue 集成进行趋势分析 |
| HPC 集群数据访问缓慢 | 计算节点附近的 FlexCache 快速读取 |

## 支持的求解器

| 求解器 | 输出格式 | 提取指标 |
|--------|----------|----------|
| LS-DYNA | d3plot, binout | 能量、位移、应力 |
| STAR-CCM+ | .sim, .csv | 流速、压力、温度 |
| Nastran | .op2, .f06 | 模态频率、应力 |
| Abaqus | .odb | 位移、应力、应变 |
| OpenFOAM | postProcessing/ | 残差、力系数 |

## 成功指标

| 指标 | 目标 |
|------|------|
| 每次执行处理的求解器输出 | > 50 文件 |
| 质量检查通过率 | > 85% |
| 报告生成时间 | < 3 分钟 |
| 每次执行成本 | < $5 |
| Human Review 比率 | < 15%（质量不合格案例） |

---

## Governance Note

> 本模式提供技术架构指导。不构成法律、合规或监管建议。组织应咨询合格的专业人员。
