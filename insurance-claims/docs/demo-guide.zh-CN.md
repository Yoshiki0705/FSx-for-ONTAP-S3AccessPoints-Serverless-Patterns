# 事故照片损害评估·保险金报告 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了从事故照片进行损害评估和保险理赔报告自动生成的流程。通过图像分析进行损害评估和 AI 报告生成，提高评估流程的效率。

**演示核心信息**：AI 自动分析事故照片，即时生成损害程度评估和保险理赔报告。

**预计时间**：3〜5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 损害评估负责人 / 理赔调查员 |
| **日常业务** | 确认事故照片、损害评估、保险金额计算、报告制作 |
| **课题** | 需要快速处理大量理赔案件 |
| **期待成果** | 加快评估流程并确保一致性 |

### Persona: 小林（损害评估负责人）

- 每月处理 100+ 件保险理赔
- 从照片判断损害程度并制作报告
- "希望自动化初步评估，专注于复杂案件"

---

## Demo Scenario: 汽车事故的损害评估

### 工作流程全貌

```
事故照片         图像分析        损害评估          理赔报告
(多张)      →   损伤检测    →   程度判定    →    AI 生成
                 部位识别        金额估算
```

---

## Storyboard（5 个部分 / 3〜5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 每月 100 件以上的保险理赔。每个案件需要确认多张事故照片，评估损害程度并制作报告。手动处理无法跟上进度。

**Key Visual**: 保险理赔案件列表、事故照片样本

### Section 2: Photo Upload（0:45–1:30）

**解说要点**:
> 上传事故照片后，自动评估流程启动。按案件单位处理。

**Key Visual**: 照片上传 → 工作流程自动启动

### Section 3: Damage Detection（1:30–2:30）

**解说要点**:
> AI 分析照片并检测损伤位置。识别损伤类型（凹陷、划痕、破损）和部位（保险杠、车门、挡泥板等）。

**Key Visual**: 损伤检测结果、部位映射

### Section 4: Assessment（2:30–3:45）

**解说要点**:
> 评估损伤程度，判断修理/更换并计算概算金额。还与过去的类似案件进行比较。

**Key Visual**: 损害评估结果表、金额估算

### Section 5: Claims Report（3:45–5:00）

**解说要点**:
> AI 自动生成保险理赔报告。包含损害摘要、估算金额、推荐对应措施。评估负责人只需确认和批准。

**Key Visual**: AI 生成理赔报告（损害摘要 + 金额估算）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 理赔案件列表 | Section 1 |
| 2 | 照片上传·流程启动 | Section 2 |
| 3 | 损伤检测结果 | Section 3 |
| 4 | 损害评估·金额估算 | Section 4 |
| 5 | 保险理赔报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "每月 100 件理赔手动评估已达极限" |
| Upload | 0:45–1:30 | "上传照片即可开始自动评估" |
| Detection | 1:30–2:30 | "AI 自动检测损伤位置和类型" |
| Assessment | 2:30–3:45 | "自动估算损害程度和修理金额" |
| Report | 3:45–5:00 | "自动生成理赔报告，仅需确认和批准" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 轻微损伤照片（5 件） | 基本评估演示 |
| 2 | 中度损伤照片（3 件） | 评估精度演示 |
| 3 | 严重损伤照片（2 件） | 全损判定演示 |

---

## Timeline

### 1 周内可完成

| 任务 | 所需时间 |
|--------|---------|
| 准备样本照片数据 | 2 小时 |
| 确认流程执行 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 制作解说稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 从视频中检测损伤
- 与修理厂报价自动对照
- 欺诈理赔检测

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流程编排 |
| Lambda (Image Analyzer) | 通过 Bedrock/Rekognition 进行损伤检测 |
| Lambda (Damage Assessor) | 损害程度评估·金额估算 |
| Lambda (Report Generator) | 通过 Bedrock 生成理赔报告 |
| Amazon Athena | 参考·比较过去案件数据 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| 图像分析精度不足 | 使用预先分析的结果 |
| Bedrock 延迟 | 显示预先生成的报告 |

---

*本文档是技术演示视频的制作指南。*

---

## 已验证的 UI/UX 截图（2026-05-10 AWS 验证）

与 Phase 7 相同方针，拍摄**保险评估负责人在日常业务中实际使用的 UI/UX 画面**。
排除面向技术人员的画面（Step Functions 图表等）。

### 输出目标选择：标准 S3 vs FSxN S3AP

UC14 在 2026-05-10 的更新中支持了 `OutputDestination` 参数。
通过**将 AI 成果物写回同一 FSx 卷**，理赔处理负责人可以
在理赔案件的目录结构内查看损害评估 JSON、OCR 结果、理赔报告
（"no data movement" 模式，从 PII 保护角度也有利）。

```bash
# STANDARD_S3 模式（默认，与以往相同）
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP 模式（将 AI 成果物写回 FSx ONTAP 卷）
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 规格上的限制和解决方法请参考[项目 README 的"AWS 规格上的限制和解决方法"
部分](../../README.md#aws-仕様上の制約と回避策)。

### 1. 保险理赔报告 — 面向评估负责人的摘要

整合了事故照片 Rekognition 分析 + 报价单 Textract OCR + 评估推荐判定的报告。
判定 `MANUAL_REVIEW` + 置信度 75%，负责人审查无法自动化的项目。

<!-- SCREENSHOT: uc14-claims-report.png
     内容: 保险理赔报告（理赔 ID、损害摘要、报价相关性、推荐判定）
            + Rekognition 检测标签列表 + Textract OCR 结果
     掩码: 账户 ID、存储桶名称 -->
![UC14: 保险理赔报告](../../docs/screenshots/masked/uc14-demo/uc14-claims-report.png)

### 2. S3 输出存储桶 — 评估产物概览

评估负责人确认每个理赔案件的产物的画面。
`assessments/` (Rekognition 分析) + `estimates/` (Textract OCR) + `reports/` (整合报告)。

<!-- SCREENSHOT: uc14-s3-output-bucket.png
     内容: S3 控制台中的 assessments/, estimates/, reports/ 前缀
     掩码: 账户 ID -->
![UC14: S3 输出存储桶](../../docs/screenshots/masked/uc14-demo/uc14-s3-output-bucket.png)

### 实测值（2026-05-10 AWS 部署验证）

- **Step Functions 执行**: SUCCEEDED
- **Rekognition**: 在事故照片中检测到 `Maroon` 90.79%、`Business Card` 84.51% 等
- **Textract**: 通过跨区域 us-east-1 从报价单 PDF 中 OCR 提取 `Total: 1270.00 USD` 等
- **生成产物**: assessments/*.json, estimates/*.json, reports/*.txt
- **实际堆栈**: `fsxn-insurance-claims-demo`（ap-northeast-1，2026-05-10 验证时）
