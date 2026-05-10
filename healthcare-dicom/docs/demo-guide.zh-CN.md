# DICOM 匿名化工作流程 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了医疗影像（DICOM）的匿名化工作流程。演示了为研究数据共享自动删除患者个人信息并验证匿名化质量的过程。

**演示核心信息**：从 DICOM 文件中自动删除患者识别信息，安全生成可用于研究的匿名化数据集。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细信息 |
|------|------|
| **职位** | 医疗信息管理员 / 临床研究数据管理员 |
| **日常工作** | 医疗影像管理、研究数据提供、隐私保护 |
| **挑战** | 大量 DICOM 文件的手动匿名化耗时且存在错误风险 |
| **期望成果** | 安全可靠的匿名化和审计追踪自动化 |

### Persona: 高橋先生（临床研究数据管理员）

- 多中心合作研究需要匿名化 10,000+ DICOM 文件
- 要求确实删除患者姓名、ID、出生日期等信息
- "希望在保证零匿名化遗漏的同时，维持影像质量"

---

## Demo Scenario: 研究数据共享的 DICOM 匿名化

### 工作流程全貌

```
DICOM 文件     标签解析        匿名化处理        质量验证
(含患者信息) →  元数据提取  →   个人信息删除  →   匿名化确认
                            哈希化          报告生成
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 需要为多中心合作研究匿名化 10,000 个 DICOM 文件。手动处理存在错误风险，不允许个人信息泄露。

**Key Visual**: DICOM 文件列表、患者信息标签高亮显示

### Section 2: Workflow Trigger（0:45–1:30）

**解说要点**:
> 指定匿名化目标数据集，启动匿名化工作流程。设置匿名化规则（删除、哈希化、泛化）。

**Key Visual**: 工作流程启动、匿名化规则设置界面

### Section 3: De-identification（1:30–2:30）

**解说要点**:
> 自动处理每个 DICOM 文件的个人信息标签。患者姓名→哈希、出生日期→年龄范围、机构名称→匿名代码。保留影像像素数据。

**Key Visual**: 匿名化处理进度、标签转换的 before/after

### Section 4: Quality Verification（2:30–3:45）

**解说要点**:
> 自动验证匿名化后的文件。扫描所有标签检查是否存在残留的个人信息。同时确认影像的完整性。

**Key Visual**: 验证结果 — 匿名化成功率、残留风险标签列表

### Section 5: Audit Report（3:45–5:00）

**解说要点**:
> 自动生成匿名化处理的审计报告。记录处理数量、删除标签数、验证结果。可作为研究伦理委员会的提交资料使用。

**Key Visual**: 审计报告（处理摘要 + 合规追踪）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | DICOM 文件列表（匿名化前） | Section 1 |
| 2 | 工作流程启动・规则设置 | Section 2 |
| 3 | 匿名化处理进度 | Section 3 |
| 4 | 质量验证结果 | Section 4 |
| 5 | 审计报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "不允许大量 DICOM 的匿名化遗漏" |
| Trigger | 0:45–1:30 | "设置匿名化规则并启动工作流程" |
| Processing | 1:30–2:30 | "自动删除个人信息标签，维持影像质量" |
| Verification | 2:30–3:45 | "通过全标签扫描确认零匿名化遗漏" |
| Report | 3:45–5:00 | "自动生成审计追踪，可提交给伦理委员会" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 测试 DICOM 文件（20 个） | 主要处理对象 |
| 2 | 复杂标签结构的 DICOM（5 个） | 边缘案例 |
| 3 | 包含私有标签的 DICOM（3 个） | 高风险验证 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 测试 DICOM 数据准备 | 3 小时 |
| 管道执行确认 | 2 小时 |
| 屏幕截图获取 | 2 小时 |
| 解说稿创作 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 影像内文本（烧入）的自动检测・删除
- 通过 FHIR 联动进行匿名化映射管理
- 差分匿名化（追加数据的增量处理）

---

## Technical Notes

| 组件 | 角色 |
|--------------|------|
| Step Functions | 工作流程编排 |
| Lambda (Tag Parser) | DICOM 标签解析・个人信息检测 |
| Lambda (De-identifier) | 标签匿名化处理 |
| Lambda (Verifier) | 匿名化质量验证 |
| Lambda (Report Generator) | 审计报告生成 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| DICOM 解析失败 | 使用预处理数据 |
| 验证错误 | 切换到手动确认流程 |

---

*本文档是技术演示视频的制作指南。*

---

## 关于输出目标：FSxN S3 Access Point (Pattern A)

UC5 healthcare-dicom 归类为 **Pattern A: Native S3AP Output**
（参见 `docs/output-destination-patterns.md`）。

**设计**：DICOM 元数据、匿名化结果、PII 检测日志全部通过 FSxN S3 Access Point
写回到与原始 DICOM 医疗影像**相同的 FSx ONTAP 卷**。不创建标准 S3 存储桶
（"no data movement" 模式）。

**CloudFormation 参数**:
- `S3AccessPointAlias`: 用于读取输入数据的 S3 AP Alias
- `S3AccessPointOutputAlias`: 用于写入输出的 S3 AP Alias（可与输入相同）

**部署示例**:
```bash
aws cloudformation deploy \
  --template-file healthcare-dicom/template-deploy.yaml \
  --stack-name fsxn-healthcare-dicom-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必需参数)
```

**从 SMB/NFS 用户的视角**:
```
/vol/dicom/
  ├── patient_001/study_A/image.dcm    # 原始 DICOM
  └── metadata/patient_001/             # AI 匿名化结果（同一卷内）
      └── study_A_anonymized.json
```

关于 AWS 规范限制，请参见
[项目 README 的 "AWS 规范限制与解决方案" 部分](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已验证的 UI/UX 屏幕截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示采用相同方针，以**最终用户在日常工作中实际
看到的 UI/UX 界面**为对象。技术人员视图（Step Functions 图表、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ⚠️ **E2E 验证**：仅部分功能（生产环境建议追加验证）
- 📸 **UI/UX 重新截图**：未实施

### 2026-05-10 重新部署验证时拍摄（以 UI/UX 为中心）

#### UC5 Step Functions Graph view（SUCCEEDED）

![UC5 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc5-demo/uc5-stepfunctions-graph.png)

Step Functions Graph view 是用颜色可视化各 Lambda / Parallel / Map 状态执行情况的
最终用户最重要界面。

### 现有屏幕截图（来自 Phase 1-6 的相关部分）

*(无相关内容。重新验证时请新拍摄)*

### 重新验证时的 UI/UX 目标界面（推荐拍摄列表）

- S3 输出存储桶（dicom-metadata/、deid-reports/、diagnoses/）
- Comprehend Medical 实体检测结果（跨区域）
- DICOM 匿名化后的元数据 JSON

### 拍摄指南

1. **事前准备**:
   - 使用 `bash scripts/verify_phase7_prerequisites.sh` 确认前提条件（共享 VPC/S3 AP 是否存在）
   - 使用 `UC=healthcare-dicom bash scripts/package_generic_uc.sh` 打包 Lambda
   - 使用 `bash scripts/deploy_generic_ucs.sh UC5` 部署

2. **样本数据配置**:
   - 通过 S3 AP Alias 将样本文件上传到 `dicom/` 前缀
   - 启动 Step Functions `fsxn-healthcare-dicom-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell・终端，浏览器右上角的用户名涂黑）:
   - S3 输出存储桶 `fsxn-healthcare-dicom-demo-output-<account>` 的概览
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **遮罩处理**:
   - 使用 `python3 scripts/mask_uc_demos.py healthcare-dicom-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行追加遮罩（如需要）

5. **清理**:
   - 使用 `bash scripts/cleanup_generic_ucs.sh UC5` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
