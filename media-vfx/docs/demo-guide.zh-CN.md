# VFX 渲染质量检查 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了 VFX 渲染输出的质量检查流水线。通过自动验证渲染帧，可以早期检测伪影和错误帧。

**演示核心信息**：自动验证大量渲染帧，即时检测质量问题。加快重新渲染的决策速度。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | VFX 总监 / 渲染 TD |
| **日常业务** | 渲染作业管理、质量确认、镜头审批 |
| **课题** | 目视确认数千帧需要耗费大量时间 |
| **期待成果** | 自动检测问题帧并加快重新渲染决策 |

### Persona：中村（VFX 总监）

- 1 个项目有 50+ 个镜头，每个镜头 100～500 帧
- 渲染完成后的质量确认成为瓶颈
- "希望自动检测黑帧、过度噪点、纹理缺失"

---

## Demo Scenario：渲染批次质量验证

### 工作流程全貌

```
渲染输出          帧分析        质量判定          QC 报告
(EXR/PNG)     →   元数据    →   异常检测    →    按镜头
                   提取             (统计分析)        汇总
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 从渲染农场输出的数千帧。目视确认黑帧、噪点、纹理缺失等问题是不现实的。

**Key Visual**：渲染输出文件夹（大量 EXR 文件）

### Section 2: Pipeline Trigger（0:45–1:30）

**解说要点**:
> 渲染作业完成后，质量检查流水线自动启动。按镜头单位并行处理。

**Key Visual**：工作流启动、镜头列表

### Section 3: Frame Analysis（1:30–2:30）

**解说要点**:
> 计算每帧的像素统计（平均亮度、方差、直方图）。同时检查帧间一致性。

**Key Visual**：帧分析处理中、像素统计图表

### Section 4: Quality Assessment（2:30–3:45）

**解说要点**:
> 检测统计异常值，识别问题帧。对黑帧（亮度为零）、过度噪点（方差异常）等进行分类。

**Key Visual**：问题帧列表、按类别分类

### Section 5: QC Report（3:45–5:00）

**解说要点**:
> 生成按镜头的 QC 报告。提供需要重新渲染的帧范围和推测原因。

**Key Visual**：AI 生成 QC 报告（按镜头汇总 + 推荐对应）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 渲染输出文件夹 | Section 1 |
| 2 | 流水线启动画面 | Section 2 |
| 3 | 帧分析进度 | Section 3 |
| 4 | 问题帧检测结果 | Section 4 |
| 5 | QC 报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "目视确认数千帧是不现实的" |
| Trigger | 0:45–1:30 | "渲染完成后自动开始 QC" |
| Analysis | 1:30–2:30 | "通过像素统计定量评估帧质量" |
| Assessment | 2:30–3:45 | "自动分类和识别问题帧" |
| Report | 3:45–5:00 | "即时支持重新渲染决策" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 正常帧（100 张） | 基准线 |
| 2 | 黑帧（3 张） | 异常检测演示 |
| 3 | 过度噪点帧（5 张） | 质量判定演示 |
| 4 | 纹理缺失帧（2 张） | 分类演示 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 准备样本帧数据 | 3 小时 |
| 确认流水线执行 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 创建解说稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 通过深度学习检测伪影
- 渲染农场联动（自动重新渲染）
- 镜头跟踪系统集成

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (Frame Analyzer) | 帧元数据和像素统计提取 |
| Lambda (Quality Checker) | 统计质量判定 |
| Lambda (Report Generator) | 通过 Bedrock 生成 QC 报告 |
| Amazon Athena | 帧统计的汇总分析 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| 大容量帧处理延迟 | 切换到缩略图分析 |
| Bedrock 延迟 | 显示预生成报告 |

---

*本文档是技术演示视频的制作指南。*

---

## 关于输出目标：FSxN S3 Access Point (Pattern A)

UC4 media-vfx 归类为 **Pattern A: Native S3AP Output**
（参见 `docs/output-destination-patterns.md`）。

**设计**：渲染元数据、帧质量评估全部通过 FSxN S3 Access Point 写回到
与原始渲染资产**相同的 FSx ONTAP 卷**。不会创建标准 S3 存储桶
（"no data movement" 模式）。

**CloudFormation 参数**:
- `S3AccessPointAlias`：用于读取输入数据的 S3 AP Alias
- `S3AccessPointOutputAlias`：用于写入输出的 S3 AP Alias（可与输入相同）

**部署示例**:
```bash
aws cloudformation deploy \
  --template-file media-vfx/template-deploy.yaml \
  --stack-name fsxn-media-vfx-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必需参数)
```

**从 SMB/NFS 用户角度的视图**:
```
/vol/renders/
  ├── shot_001/frame_0001.exr         # 原始渲染帧
  └── qc/shot_001/                     # 帧质量评估（同一卷内）
      └── frame_0001_qc.json
```

关于 AWS 规范限制，请参阅
[项目 README 的 "AWS 仕様上の制約と回避策" 部分](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已验证的 UI/UX 截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 画面**为对象。技术人员视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ⚠️ **E2E 验证**：仅部分功能（生产环境建议追加验证）
- 📸 **UI/UX 拍摄**：✅ SFN Graph 完成（Phase 8 Theme D, commit 3c90042）

### 现有截图（来自 Phase 1-6 的相关部分）

![UC4 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc4-demo/step-functions-graph-succeeded.png)

![UC4 Step Functions Graph（放大显示 — 各步骤详细）](../../docs/screenshots/masked/uc4-demo/step-functions-graph-zoomed.png)

### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- （重新验证时定义）

### 拍摄指南

1. **事前准备**:
   - 使用 `bash scripts/verify_phase7_prerequisites.sh` 确认前提（共享 VPC/S3 AP 是否存在）
   - 使用 `UC=media-vfx bash scripts/package_generic_uc.sh` 打包 Lambda
   - 使用 `bash scripts/deploy_generic_ucs.sh UC4` 部署

2. **配置样本数据**:
   - 通过 S3 AP Alias 将样本文件上传到 `renders/` 前缀
   - 启动 Step Functions `fsxn-media-vfx-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell 和终端，浏览器右上角的用户名涂黑）:
   - S3 输出存储桶 `fsxn-media-vfx-demo-output-<account>` 的概览
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **掩码处理**:
   - 使用 `python3 scripts/mask_uc_demos.py media-vfx-demo` 自动掩码
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外掩码（如需要）

5. **清理**:
   - 使用 `bash scripts/cleanup_generic_ucs.sh UC4` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
