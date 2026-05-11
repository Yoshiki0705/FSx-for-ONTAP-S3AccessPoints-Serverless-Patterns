# 论文分类·引用网络分析 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了学术论文的自动分类和引用网络分析流水线。从大量论文 PDF 中提取元数据，可视化研究趋势。

**演示的核心信息**：通过自动分类论文集合并分析引用关系，即时掌握研究领域的全貌和重要论文。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 研究人员 / 图书馆信息学专家 / 研究管理员 |
| **日常业务** | 文献调查、研究动向分析、论文管理 |
| **课题** | 无法从大量论文中高效发现相关研究 |
| **期待的成果** | 研究领域的映射和重要论文的自动识别 |

### Persona: 渡边先生（研究人员）

- 正在进行新研究主题的文献调研
- 收集了 500+ 篇论文的 PDF，但无法掌握全貌
- "希望按领域自动分类，并识别引用量多的重要论文"

---

## Demo Scenario: 文献集合的自动分析

### 工作流程全貌

```
论文 PDF 群       元数据提取     分类·分析        可视化报告
(500+ 件)    →   标题/作者  →  主题分类  →   网络
                  引用信息          引用解析          地图生成
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**旁白要旨**:
> 收集了 500 多篇论文 PDF。希望掌握按领域的分布、重要论文、研究趋势，但不可能全部阅读。

**Key Visual**: 论文 PDF 文件列表（大量）

### Section 2: Metadata Extraction（0:45–1:30）

**旁白要旨**:
> 从各论文 PDF 中自动提取标题、作者、摘要、引用列表。

**Key Visual**: 元数据提取处理、提取结果样本

### Section 3: Classification（1:30–2:30）

**旁白要旨**:
> AI 分析摘要，自动分类研究主题。通过聚类形成相关论文组。

**Key Visual**: 主题分类结果、按类别的论文数

### Section 4: Citation Analysis（2:30–3:45）

**旁白要旨**:
> 分析引用关系，识别被引用数多的重要论文。分析引用网络的结构。

**Key Visual**: 引用网络统计、重要论文排名

### Section 5: Research Map（3:45–5:00）

**旁白要旨**:
> AI 生成研究领域全貌的摘要报告。展示趋势、空白、未来研究方向。

**Key Visual**: 研究地图报告（趋势分析 + 推荐文献）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 论文 PDF 集合 | Section 1 |
| 2 | 元数据提取结果 | Section 2 |
| 3 | 主题分类结果 | Section 3 |
| 4 | 引用网络统计 | Section 4 |
| 5 | 研究地图报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "希望掌握 500 篇论文的全貌" |
| Extraction | 0:45–1:30 | "从 PDF 自动提取元数据" |
| Classification | 1:30–2:30 | "AI 按主题自动分类" |
| Citation | 2:30–3:45 | "通过引用网络识别重要论文" |
| Map | 3:45–5:00 | "可视化研究领域的全貌和趋势" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 论文 PDF（30 件、3 个领域） | 主要处理对象 |
| 2 | 引用关系数据（包含相互引用） | 网络分析演示 |
| 3 | 高被引论文（5 件） | 重要论文识别演示 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 准备样本论文数据 | 3 小时 |
| 确认流水线执行 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 创建旁白稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 交互式引用网络可视化
- 论文推荐系统
- 定期自动分类新论文

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (PDF Parser) | 论文 PDF 元数据提取 |
| Lambda (Classifier) | 通过 Bedrock 进行主题分类 |
| Lambda (Citation Analyzer) | 引用网络构建·分析 |
| Amazon Athena | 元数据汇总·检索 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| PDF 解析失败 | 使用预先提取的数据 |
| 分类精度不足 | 显示预先分类的结果 |

---

*本文档是技术演示用演示视频的制作指南。*

---

## 已验证的 UI/UX 截图

Phase 7 UC15/16/17 与 UC6/11/14 的演示采用相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 画面**为对象。面向技术人员的视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ✅ **E2E 执行**: Phase 1-6 已确认（参考根 README）
- 📸 **UI/UX 重新拍摄**: ✅ 2026-05-10 重新部署验证时已拍摄 （UC13 Step Functions 图、Lambda 执行成功已确认）
- 🔄 **重现方法**: 参考本文档末尾的"拍摄指南"

### 2026-05-10 重新部署验证时拍摄（以 UI/UX 为中心）

#### UC13 Step Functions Graph view（SUCCEEDED）

![UC13 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc13-demo/uc13-stepfunctions-graph.png)

Step Functions Graph view 是用颜色可视化各 Lambda / Parallel / Map 状态执行状况的
最终用户最重要画面。

### 现有截图（来自 Phase 1-6 的相关部分）

![UC13 Step Functions 图表视图 (SUCCEEDED)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-succeeded.png)

![UC13 Step Functions 图表 (整体概览)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-overview.png)

![UC13 Step Functions 图表 (缩放 — 各步骤详细)](../../docs/screenshots/masked/uc13-demo/step-functions-graph-zoomed.png)

### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- S3 输出存储桶（papers-ocr/、citations/、reports/）
- Textract 论文 OCR 结果（跨区域）
- Comprehend 实体检测（作者、引用、关键词）
- 研究网络分析报告

### 拍摄指南

1. **事前准备**:
   - `bash scripts/verify_phase7_prerequisites.sh` 确认前提（共享 VPC/S3 AP 有无）
   - `UC=education-research bash scripts/package_generic_uc.sh` 打包 Lambda
   - `bash scripts/deploy_generic_ucs.sh UC13` 部署

2. **放置样本数据**:
   - 通过 S3 AP Alias 将样本文件上传到 `papers/` 前缀
   - 启动 Step Functions `fsxn-education-research-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell·终端，浏览器右上角的用户名涂黑）:
   - S3 输出存储桶 `fsxn-education-research-demo-output-<account>` 的俯瞰
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 的格式）
   - SNS 邮件通知（如适用）

4. **遮罩处理**:
   - `python3 scripts/mask_uc_demos.py education-research-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外遮罩（如需要）

5. **清理**:
   - `bash scripts/cleanup_generic_ucs.sh UC13` 删除
   - VPC Lambda ENI 释放需 15-30 分钟（AWS 规格）
