# IoT 传感器异常检测·质量检查 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了从制造生产线的 IoT 传感器数据中自动检测异常并生成质量检查报告的工作流程。

**演示核心信息**：自动检测传感器数据的异常模式，实现质量问题的早期发现和预防性维护。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 制造部门经理 / 质量管理工程师 |
| **日常业务** | 生产线监控、质量检查、设备维护计划 |
| **课题** | 传感器数据异常被遗漏，不良品流入后续工序 |
| **期待成果** | 异常的早期检测和质量趋势的可视化 |

### Persona: 铃木先生（质量管理工程师）

- 监控 5 条制造生产线的 100+ 个传感器
- 基于阈值的警报误报较多，容易遗漏真正的异常
- "希望只检测统计上显著的异常"

---

## Demo Scenario: 传感器异常检测批量分析

### 工作流程全貌

```
传感器数据      数据收集       异常检测          质量报告
(CSV/Parquet)  →   预处理     →   统计分析    →    AI 生成
                   标准化          (离群值检测)
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 制造生产线的 100+ 个传感器每天生成大量数据。简单的阈值警报误报较多，存在遗漏真正异常的风险。

**Key Visual**: 传感器数据的时间序列图、警报过多的情况

### Section 2: Data Ingestion（0:45–1:30）

**解说要点**:
> 传感器数据积累到文件服务器后，自动启动分析管道。

**Key Visual**: 数据文件放置 → 工作流启动

### Section 3: Anomaly Detection（1:30–2:30）

**解说要点**:
> 使用统计方法（移动平均、标准差、IQR）计算每个传感器的异常分数。同时执行多个传感器的相关性分析。

**Key Visual**: 异常检测算法执行中、异常分数热图

### Section 4: Quality Inspection（2:30–3:45）

**解说要点**:
> 从质量检查的角度分析检测到的异常。识别哪条生产线的哪个工序发生了问题。

**Key Visual**: Athena 查询结果 — 按生产线・工序的异常分布

### Section 5: Report & Action（3:45–5:00）

**解说要点**:
> AI 生成质量检查报告。提示异常的根本原因候选和推荐对应措施。

**Key Visual**: AI 生成质量报告（异常摘要 + 推荐措施）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 传感器数据文件列表 | Section 1 |
| 2 | 工作流启动画面 | Section 2 |
| 3 | 异常检测处理进度 | Section 3 |
| 4 | 异常分布查询结果 | Section 4 |
| 5 | AI 质量检查报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "阈值警报会遗漏真正的异常" |
| Ingestion | 0:45–1:30 | "数据积累后自动开始分析" |
| Detection | 1:30–2:30 | "使用统计方法仅检测显著异常" |
| Inspection | 2:30–3:45 | "在生产线・工序级别识别问题位置" |
| Report | 3:45–5:00 | "AI 提示根本原因候选和对应措施" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 正常传感器数据（5 条生产线 × 7 天） | 基线 |
| 2 | 温度异常数据（2 件） | 异常检测演示 |
| 3 | 振动异常数据（3 件） | 相关性分析演示 |
| 4 | 质量下降模式（1 件） | 报告生成演示 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 生成样本传感器数据 | 3 小时 |
| 管道执行确认 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 创建解说稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 实时流式分析
- 预防性维护计划自动生成
- 数字孪生联动

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (Data Preprocessor) | 传感器数据标准化・预处理 |
| Lambda (Anomaly Detector) | 统计异常检测 |
| Lambda (Report Generator) | 通过 Bedrock 生成质量报告 |
| Amazon Athena | 异常数据的汇总・分析 |

### 后备方案

| 场景 | 对应 |
|---------|------|
| 数据量不足 | 使用预生成数据 |
| 检测精度不足 | 显示参数调整后的结果 |

---

*本文档是技术演示视频的制作指南。*

---

## 关于输出目标：FSxN S3 Access Point (Pattern A)

UC3 manufacturing-analytics 归类为 **Pattern A: Native S3AP Output**
（参见 `docs/output-destination-patterns.md`）。

**设计**：传感器数据分析结果、异常检测报告、图像检查结果全部通过 FSxN S3 Access Point
写回到与原始传感器 CSV 和检查图像**相同的 FSx ONTAP 卷**。不创建标准 S3 存储桶
（"no data movement" 模式）。

**CloudFormation 参数**:
- `S3AccessPointAlias`: 用于读取输入数据的 S3 AP Alias
- `S3AccessPointOutputAlias`: 用于写入输出的 S3 AP Alias（可与输入相同）

**部署示例**:
```bash
aws cloudformation deploy \
  --template-file manufacturing-analytics/template-deploy.yaml \
  --stack-name fsxn-manufacturing-analytics-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必需参数)
```

**SMB/NFS 用户视角**:
```
/vol/sensors/
  ├── 2026/05/line_A/sensor_001.csv    # 原始传感器数据
  └── analysis/2026/05/                 # AI 异常检测结果（同一卷内）
      └── line_A_report.json
```

关于 AWS 规格限制，请参考
[项目 README 的 "AWS 仕様上の制約と回避策" 部分](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已验证的 UI/UX 截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 画面**为对象。技术人员视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ✅ **E2E 执行**: Phase 1-6 已确认（参见根 README）
- 📸 **UI/UX 重新拍摄**: ✅ 2026-05-10 重新部署验证时已拍摄 （确认 UC3 Step Functions 图、Lambda 执行成功）
- 🔄 **重现方法**: 参考本文档末尾的"拍摄指南"

### 2026-05-10 重新部署验证时拍摄（以 UI/UX 为中心）

#### UC3 Step Functions Graph view（SUCCEEDED）

![UC3 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc3-demo/uc3-stepfunctions-graph.png)

Step Functions Graph view 是用颜色可视化各 Lambda / Parallel / Map 状态执行情况的
最终用户最重要画面。

### 现有截图（来自 Phase 1-6 的相关部分）

![UC3 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc3-demo/step-functions-graph-succeeded.png)

![UC3 Step Functions Graph（展开显示）](../../docs/screenshots/masked/uc3-demo/step-functions-graph-expanded.png)

![UC3 Step Functions Graph（缩放显示 — 各步骤详细）](../../docs/screenshots/masked/uc3-demo/step-functions-graph-zoomed.png)

### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- S3 输出存储桶（metrics/、anomalies/、reports/）
- Athena 查询结果（IoT 传感器异常检测）
- Rekognition 质量检查图像标签
- 制造质量摘要报告

### 拍摄指南

1. **事前准备**:
   - 使用 `bash scripts/verify_phase7_prerequisites.sh` 确认前提（共享 VPC/S3 AP 是否存在）
   - 使用 `UC=manufacturing-analytics bash scripts/package_generic_uc.sh` 打包 Lambda
   - 使用 `bash scripts/deploy_generic_ucs.sh UC3` 部署

2. **放置样本数据**:
   - 通过 S3 AP Alias 将样本文件上传到 `sensors/` 前缀
   - 启动 Step Functions `fsxn-manufacturing-analytics-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell・终端，浏览器右上角的用户名涂黑）:
   - S3 输出存储桶 `fsxn-manufacturing-analytics-demo-output-<account>` 的概览
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **遮罩处理**:
   - 使用 `python3 scripts/mask_uc_demos.py manufacturing-analytics-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外遮罩（如需要）

5. **清理**:
   - 使用 `bash scripts/cleanup_generic_ucs.sh UC3` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规格）
