# 商品图像标签和目录元数据生成 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了商品图像自动标签和目录元数据生成流水线。通过 AI 图像分析自动提取商品属性，构建可搜索的目录。

**演示核心信息**：AI 从商品图像中自动提取属性（颜色、材质、类别等），即时生成目录元数据。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 电商网站运营者 / 目录管理者 / 商品企划负责人 |
| **日常业务** | 商品注册、图像管理、目录更新 |
| **课题** | 新商品的属性输入和标签需要大量时间 |
| **期待成果** | 商品注册自动化和搜索性提升 |

### Persona: 吉田（电商目录管理者）

- 每周注册 200+ 件新商品
- 每件商品手动输入 10+ 个属性标签
- "希望只需上传商品图像就能自动生成标签"

---

## Demo Scenario: 新商品批量注册

### 工作流程全貌

```
商品图像          图像分析        属性提取          目录更新
(JPEG/PNG)   →   AI 分析    →   标签生成    →    元数据
                  物体检测        类别分类          注册
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 每周 200 件以上的新商品。为每件商品手动输入颜色、材质、类别、风格等标签是巨大的工作量。还会发生输入错误和不统一。

**Key Visual**: 商品图像文件夹、手动标签输入界面

### Section 2: Image Upload（0:45–1:30）

**解说要点**:
> 只需将商品图像放置到文件夹中，自动标签流水线即可启动。

**Key Visual**: 图像上传 → 工作流程自动启动

### Section 3: AI Analysis（1:30–2:30）

**解说要点**:
> AI 分析每张图像，自动判定商品类别、颜色、材质、图案、风格。同时提取多个属性。

**Key Visual**: 图像分析处理中、属性提取结果

### Section 4: Tag Generation（2:30–3:45）

**解说要点**:
> 将提取的属性转换为标准化标签。确保与现有标签体系的一致性。

**Key Visual**: 生成标签列表、按类别分布

### Section 5: Catalog Update（3:45–5:00）

**解说要点**:
> 元数据自动注册到目录。有助于提升搜索性和商品推荐精度。生成处理摘要报告。

**Key Visual**: 目录更新结果、AI 摘要报告

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 商品图像文件夹 | Section 1 |
| 2 | 流水线启动界面 | Section 2 |
| 3 | AI 图像分析结果 | Section 3 |
| 4 | 标签生成结果列表 | Section 4 |
| 5 | 目录更新摘要 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "每周 200 件的手动标签是巨大的工作量" |
| Upload | 0:45–1:30 | "只需放置图像即可开始自动标签" |
| Analysis | 1:30–2:30 | "AI 自动判定颜色、材质、类别" |
| Tags | 2:30–3:45 | "自动生成标准化标签" |
| Catalog | 3:45–5:00 | "自动注册到目录，搜索性提升" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 服装商品图像（10 张） | 主要处理对象 |
| 2 | 家具商品图像（5 张） | 类别分类演示 |
| 3 | 配饰图像（5 张） | 多属性提取演示 |
| 4 | 现有标签体系主数据 | 标准化演示 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 准备样本商品图像 | 2 小时 |
| 确认流水线执行 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 创建解说稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 相似商品搜索
- 自动商品说明文生成
- 趋势分析联动

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流程编排 |
| Lambda (Image Analyzer) | 通过 Bedrock/Rekognition 进行图像分析 |
| Lambda (Tag Generator) | 属性标签生成・标准化 |
| Lambda (Catalog Updater) | 目录元数据注册 |
| Lambda (Report Generator) | 处理摘要报告生成 |

### 后备方案

| 场景 | 对应 |
|---------|------|
| 图像分析精度不足 | 使用预先分析的结果 |
| Bedrock 延迟 | 显示预先生成的标签 |

---

*本文档是技术演示视频的制作指南。*

---

## 已验证的 UI/UX 截图（2026-05-10 AWS 验证）

与 Phase 7 相同方针，拍摄 **电商负责人在日常业务中实际使用的 UI/UX 界面**。
排除面向技术人员的界面（Step Functions 图表等）。

### 输出目标选择：标准 S3 vs FSxN S3AP

UC11 在 2026-05-10 的更新中支持了 `OutputDestination` 参数。
通过 **将 AI 成果物写回同一 FSx 卷**，SMB/NFS 用户可以
在商品图像的目录结构内查看自动生成的标签 JSON
（"no data movement" 模式）。

```bash
# STANDARD_S3 模式（默认，与以往相同）
--parameter-overrides OutputDestination=STANDARD_S3 ...

# FSXN_S3AP 模式（将 AI 成果物写回 FSx ONTAP 卷）
--parameter-overrides \
  OutputDestination=FSXN_S3AP \
  OutputS3APPrefix=ai-outputs/ \
  ...
```

AWS 规格限制和解决方法请参考 [项目 README 的 "AWS 规格限制和解决方法"
部分](../../README.md#aws-仕规格限制和解决方法)。

### 1. 商品图像的自动标签结果

电商管理者在新商品注册时收到的 AI 分析结果。Rekognition 从实际图像中检测出 7 个标签
（`Oval` 99.93%、`Food`、`Furniture`、`Table`、`Sweets`、`Cocoa`、`Dessert`）。

<!-- SCREENSHOT: uc11-product-tags.png
     内容: 商品图像 + AI 检测标签列表（含置信度）
     掩码: 账户 ID、存储桶名称 -->
![UC11: 商品标签](../../docs/screenshots/masked/uc11-demo/uc11-product-tags.png)

### 2. S3 输出存储桶 — 标签・质量检查结果概览

电商运营负责人确认批处理结果的界面。
在 `tags/` 和 `quality/` 两个前缀下，为每件商品生成 JSON。

<!-- SCREENSHOT: uc11-s3-output-bucket.png
     内容: S3 控制台中的 tags/, quality/ 前缀
     掩码: 账户 ID -->
![UC11: S3 输出存储桶](../../docs/screenshots/masked/uc11-demo/uc11-s3-output-bucket.png)

### 实测值（2026-05-10 AWS 部署验证）

- **Step Functions 执行**: SUCCEEDED，并行处理 4 张商品图像
- **Rekognition**: 从实际图像检测出 7 个标签（最高置信度 99.93%）
- **生成 JSON**: tags/*.json (~750 bytes)、quality/*.json (~420 bytes)
- **实际堆栈**: `fsxn-retail-catalog-demo`（ap-northeast-1，2026-05-10 验证时）
