# 测序 QC·变异集计 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了下一代测序（NGS）数据的质量管理和变异汇总流程。自动验证测序质量，并汇总和报告变异调用结果。

**演示核心信息**：自动化测序数据的 QC，即时生成变异汇总报告。确保分析的可靠性。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 生物信息学家 / 基因组分析研究员 |
| **日常工作** | 测序数据 QC、变异调用、结果解释 |
| **挑战** | 手动确认大量样本的 QC 非常耗时 |
| **期望成果** | QC 自动化和变异汇总的效率提升 |

### Persona: 加藤（生物信息学家）

- 每周处理 100+ 样本的测序数据
- 需要早期检测不符合 QC 标准的样本
- "希望自动将通过 QC 的样本发送到下游分析"

---

## Demo Scenario: 测序批次 QC

### 工作流程全貌

```
FASTQ/BAM 文件    QC 分析        质量判定         变异汇总
(100+ 样本)  →   指标计算  →   Pass/Fail   →   报告生成
                               过滤
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**旁白要点**:
> 每周 100 个以上的测序数据样本。如果质量差的样本混入下游分析，会降低整体结果的可靠性。

**Key Visual**: 测序数据文件列表

### Section 2: Pipeline Trigger（0:45–1:30）

**旁白要点**:
> 测序运行完成后，QC 流程自动启动。并行处理所有样本。

**Key Visual**: 工作流启动、样本列表

### Section 3: QC Metrics（1:30–2:30）

**旁白要点**:
> 计算每个样本的 QC 指标：读取数、Q30 率、映射率、覆盖深度、重复率。

**Key Visual**: QC 指标计算处理中、指标列表

### Section 4: Quality Filtering（2:30–3:45）

**旁白要点**:
> 根据 QC 标准判定 Pass/Fail。对 Fail 样本的原因进行分类（低质量读取、低覆盖度等）。

**Key Visual**: Pass/Fail 判定结果、Fail 原因分类

### Section 5: Variant Summary（3:45–5:00）

**旁白要点**:
> 汇总通过 QC 样本的变异调用结果。生成样本间比较、变异分布、AI 摘要报告。

**Key Visual**: 变异汇总报告（统计摘要 + AI 解释）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 测序数据列表 | Section 1 |
| 2 | 流程启动画面 | Section 2 |
| 3 | QC 指标结果 | Section 3 |
| 4 | Pass/Fail 判定结果 | Section 4 |
| 5 | 变异汇总报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "低质量样本的混入会损害整体分析的可靠性" |
| Trigger | 0:45–1:30 | "运行完成后自动开始 QC" |
| Metrics | 1:30–2:30 | "为所有样本计算主要 QC 指标" |
| Filtering | 2:30–3:45 | "根据标准自动判定 Pass/Fail" |
| Summary | 3:45–5:00 | "即时生成变异汇总和 AI 摘要" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 高质量 FASTQ 指标（20 个样本） | 基线 |
| 2 | 低质量样本（Q30 < 80%，3 个） | Fail 检测演示 |
| 3 | 低覆盖度样本（2 个） | 分类演示 |
| 4 | 变异调用结果（VCF 摘要） | 汇总演示 |

---

## Timeline

### 1 周内可实现

| 任务 | 所需时间 |
|--------|---------|
| 样本 QC 数据准备 | 3 小时 |
| 流程执行确认 | 2 小时 |
| 屏幕截图获取 | 2 小时 |
| 旁白脚本创建 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 实时测序监控
- 临床报告自动生成
- 多组学整合分析

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (QC Calculator) | 测序 QC 指标计算 |
| Lambda (Quality Filter) | Pass/Fail 判定·分类 |
| Lambda (Variant Aggregator) | 变异汇总 |
| Lambda (Report Generator) | 通过 Bedrock 生成摘要报告 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| 大容量数据处理延迟 | 使用子集执行 |
| Bedrock 延迟 | 显示预生成报告 |

---

*本文档是技术演示视频的制作指南。*

---

## 已验证的 UI/UX 截图

Phase 7 UC15/16/17 与 UC6/11/14 的演示采用相同方针，以**最终用户在日常工作中实际
看到的 UI/UX 画面**为对象。面向技术人员的视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ✅ **E2E 执行**: Phase 1-6 已确认（参见根 README）
- 📸 **UI/UX 重新拍摄**: ✅ 2026-05-10 重新部署验证时已拍摄（确认 UC7 Step Functions 图、Lambda 执行成功）
- 📸 **UI/UX 截图 (Phase 8 Theme D)**: ✅ SUCCEEDED 截图完成 (commit 2b958db — IAM S3AP 修复后重新部署, 3:03 全步骤成功)
- 🔄 **重现方法**: 参见本文档末尾的"拍摄指南"

### 2026-05-10 重新部署验证时拍摄（以 UI/UX 为中心）

#### UC7 Step Functions Graph view（SUCCEEDED）

![UC7 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc7-demo/uc7-stepfunctions-graph.png)

#### UC7 Step Functions 图表 (工作流结构 — Phase 8 Theme D)

![UC7 Step Functions 图表 (SUCCEEDED)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-succeeded.png)

![UC7 Step Functions Graph (zoomed)](../../docs/screenshots/masked/uc7-demo/step-functions-graph-zoomed.png)


Step Functions Graph view 通过颜色可视化各 Lambda / Parallel / Map 状态的执行情况，
是最终用户最重要的画面。

### 现有截图（来自 Phase 1-6 的相关部分）

#### UC7 Comprehend Medical 基因组学分析结果（跨区域 us-east-1）

![UC7 Comprehend Medical 基因组学分析结果（跨区域 us-east-1）](../../docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis-fullpage.png)


### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- S3 输出存储桶（fastq-qc/、variant-summary/、entities/）
- Athena 查询结果（变异频率汇总）
- Comprehend Medical 医学实体（Genes, Diseases, Mutations）
- Bedrock 生成的研究报告

### 拍摄指南

1. **事前准备**:
   - `bash scripts/verify_phase7_prerequisites.sh` 确认前提条件（共享 VPC/S3 AP 是否存在）
   - `UC=genomics-pipeline bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC7` 部署

2. **样本数据配置**:
   - 通过 S3 AP Alias 将样本文件上传到 `fastq/` 前缀
   - 启动 Step Functions `fsxn-genomics-pipeline-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell·终端，浏览器右上角的用户名涂黑）:
   - S3 输出存储桶 `fsxn-genomics-pipeline-demo-output-<account>` 的概览
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **掩码处理**:
   - `python3 scripts/mask_uc_demos.py genomics-pipeline-demo` 自动掩码
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外掩码（如需要）

5. **清理**:
   - `bash scripts/cleanup_generic_ucs.sh UC7` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
