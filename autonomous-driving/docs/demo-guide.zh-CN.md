# 行驶数据预处理·标注 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了自动驾驶开发中行驶数据的预处理和标注流水线。自动分类和质量检查大量传感器数据，高效构建训练数据集。

**演示核心信息**：自动化行驶数据的质量验证和元数据添加，加速 AI 训练用数据集构建。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 数据工程师 / ML 工程师 |
| **日常业务** | 行驶数据管理、标注、训练数据集构建 |
| **课题** | 无法从大量行驶数据中高效提取有用场景 |
| **期待成果** | 数据质量自动验证和场景分类的效率化 |

### Persona: 伊藤先生（数据工程师）

- 每天积累 TB 级别的行驶数据
- 相机・LiDAR・雷达的同步确认需要手动操作
- "希望只将高质量数据自动发送到训练流水线"

---

## Demo Scenario: 行驶数据批量预处理

### 工作流程全貌

```
行驶数据        数据验证       场景分类        数据集
(ROS bag等)  →   质量检查  →  元数据   →   目录生成
                  同步确认        添加 (AI)
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**解说要点**:
> 每天积累 TB 级别的行驶数据。混杂着质量差的数据（传感器缺失、同步偏差），手动筛选不现实。

**Key Visual**: 行驶数据文件夹结构、数据量可视化

### Section 2: Pipeline Trigger（0:45–1:30）

**解说要点**:
> 上传新的行驶数据后，预处理流水线自动启动。

**Key Visual**: 数据上传 → 工作流自动启动

### Section 3: Quality Validation（1:30–2:30）

**解说要点**:
> 传感器数据完整性检查：自动检测帧缺失、时间戳同步、数据损坏。

**Key Visual**: 质量检查结果 — 按传感器分类的健康度评分

### Section 4: Scene Classification（2:30–3:45）

**解说要点**:
> AI 自动分类场景：交叉路口、高速公路、恶劣天气、夜间等。作为元数据添加。

**Key Visual**: 场景分类结果表、按类别分布

### Section 5: Dataset Catalog（3:45–5:00）

**解说要点**:
> 自动生成质量验证完成数据的目录。可作为按场景条件检索的数据集使用。

**Key Visual**: 数据集目录、检索界面

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 行驶数据文件夹结构 | Section 1 |
| 2 | 流水线启动画面 | Section 2 |
| 3 | 质量检查结果 | Section 3 |
| 4 | 场景分类结果 | Section 4 |
| 5 | 数据集目录 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "从 TB 级别数据中手动筛选有用场景是不可能的" |
| Trigger | 0:45–1:30 | "上传后自动开始预处理" |
| Validation | 1:30–2:30 | "自动检测传感器缺失・同步偏差" |
| Classification | 2:30–3:45 | "AI 自动分类场景并添加元数据" |
| Catalog | 3:45–5:00 | "自动生成可检索的数据集目录" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 正常行驶数据（5 个会话） | 基准线 |
| 2 | 帧缺失数据（2 件） | 质量检查演示 |
| 3 | 多样场景数据（交叉路口、高速、夜间） | 分类演示 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 准备样本行驶数据 | 3 小时 |
| 确认流水线执行 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 制作解说稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 3D 标注自动生成
- 通过主动学习进行数据选择
- 数据版本管理集成

---

## Technical Notes

| 组件 | 作用 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (Python 3.13) | 传感器数据质量验证、场景分类、目录生成 |
| Lambda SnapStart | 减少冷启动（通过 `EnableSnapStart=true` 选择加入） |
| SageMaker (4-way routing) | 推理（Batch / Serverless / Provisioned / Inference Components） |
| SageMaker Inference Components | 真正的 scale-to-zero（`EnableInferenceComponents=true`） |
| Amazon Bedrock | 场景分类・标注建议 |
| Amazon Athena | 元数据检索・汇总 |
| CloudFormation Guard Hooks | 部署时强制执行安全策略 |

### 本地测试 (Phase 6A)

```bash
# SAM CLI でローカルテスト
sam local invoke \
  --template autonomous-driving/template-deploy.yaml \
  --event events/uc09-autonomous-driving/discovery-event.json \
  --env-vars events/env.json \
  DiscoveryFunction
```

### 回退方案

| 场景 | 对应 |
|---------|------|
| 大容量数据处理延迟 | 使用子集执行 |
| 分类精度不足 | 显示预分类结果 |

---

*本文档是技术演示用演示视频的制作指南。*

---

## 关于输出目标：可通过 OutputDestination 选择 (Pattern B)

UC9 autonomous-driving 在 2026-05-10 的更新中支持了 `OutputDestination` 参数
（参考 `docs/output-destination-patterns.md`）。

**目标工作负载**：ADAS / 自动驾驶数据（帧提取、点云QC、标注、推理）

**2 种模式**：

### STANDARD_S3（默认，与以往相同）
创建新的 S3 存储桶（`${AWS::StackName}-output-${AWS::AccountId}`），
将 AI 成果物写入其中。

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (他の必須パラメータ)
```

### FSXN_S3AP（"no data movement" 模式）
通过 FSxN S3 Access Point 将 AI 成果物写回到与原始数据**相同的 FSx ONTAP 卷**。
SMB/NFS 用户可以在业务使用的目录结构内直接查看 AI 成果物。不创建标准 S3 存储桶。

```bash
aws cloudformation deploy \
  --template-file autonomous-driving/template-deploy.yaml \
  --stack-name fsxn-autonomous-driving-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (他の必須パラメータ)
```

**注意事项**：

- 强烈建议指定 `S3AccessPointName`（同时使用 Alias 格式和 ARN 格式进行 IAM 授权）
- 超过 5GB 的对象在 FSxN S3AP 中不可用（AWS 规范），必须使用分段上传
- AWS 规范上的限制请参考
  [项目 README 的 "AWS 规范上的限制与规避方法" 部分](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已验证的 UI/UX 截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 画面**为对象。技术人员视图（Step Functions 图表、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ⚠️ **E2E 验证**：仅部分功能（生产环境建议追加验证）
- 📸 **UI/UX 重新拍摄**：未实施

### 现有截图（来自 Phase 1-6 的相关部分）

![UC9 Step Functions 图表视图 (SUCCEEDED)](../../docs/screenshots/masked/uc9-demo/step-functions-graph-succeeded.png)

### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- S3 输出存储桶（keyframes/、annotations/、qc/）
- Rekognition 关键帧物体检测结果
- LiDAR 点云质量检查摘要
- COCO 兼容标注 JSON

### 拍摄指南

1. **事前准备**：
   - 使用 `bash scripts/verify_phase7_prerequisites.sh` 确认前提条件（共用 VPC/S3 AP 是否存在）
   - 使用 `UC=autonomous-driving bash scripts/package_generic_uc.sh` 打包 Lambda
   - 使用 `bash scripts/deploy_generic_ucs.sh UC9` 部署

2. **样本数据配置**：
   - 通过 S3 AP Alias 将样本文件上传到 `footage/` 前缀
   - 启动 Step Functions `fsxn-autonomous-driving-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell・终端，浏览器右上角的用户名涂黑）：
   - S3 输出存储桶 `fsxn-autonomous-driving-demo-output-<account>` 的概览
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **遮罩处理**：
   - 使用 `python3 scripts/mask_uc_demos.py autonomous-driving-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行追加遮罩（如需要）

5. **清理**：
   - 使用 `bash scripts/cleanup_generic_ucs.sh UC9` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
