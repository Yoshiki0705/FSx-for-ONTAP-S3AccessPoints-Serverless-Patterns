# 文件服务器权限审计 — Demo Guide

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## Executive Summary

本演示展示了自动检测文件服务器上过度访问权限的审计工作流。通过解析 NTFS ACL，识别违反最小权限原则的条目，并自动生成合规报告。

**演示核心信息**：将手动需要数周时间的文件服务器权限审计自动化，即时可视化过度权限的风险。

**预计时间**：3～5 分钟

---

## Target Audience & Persona

| 项目 | 详细 |
|------|------|
| **职位** | 信息安全负责人 / IT 合规管理员 |
| **日常业务** | 访问权限审查、审计响应、安全策略管理 |
| **课题** | 手动确认数千个文件夹的权限不切实际 |
| **期待成果** | 早期发现过度权限并自动化合规证据追踪 |

### Persona: 佐藤（信息安全管理员）

- 年度审计需要审查所有共享文件夹的权限
- 希望即时检测"Everyone 完全控制"等危险设置
- 希望高效创建提交给审计机构的报告

---

## Demo Scenario: 年度权限审计的自动化

### 工作流全貌

```
文件服务器     ACL 收集        权限分析          报告生成
(NTFS 共享)   →   元数据   →   违规检测    →    审计报告
                   提取            (规则匹配)      (AI 摘要)
```

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**旁白要点**:
> 年度审计时期。需要对数千个共享文件夹进行权限审查，但手动确认需要数周时间。如果放任过度权限，信息泄露风险将增加。

**Key Visual**: 大量文件夹结构和"手动审计：预计 3～4 周"的叠加显示

### Section 2: Workflow Trigger（0:45–1:30）

**旁白要点**:
> 指定审计目标卷，启动权限审计工作流。

**Key Visual**: Step Functions 执行画面，目标路径指定

### Section 3: ACL Analysis（1:30–2:30）

**旁白要点**:
> 自动收集各文件夹的 NTFS ACL，通过以下规则检测违规：
> - 对 Everyone / Authenticated Users 的过度权限
> - 不必要的继承累积
> - 离职员工账户的残留

**Key Visual**: 并行处理的 ACL 扫描进度

### Section 4: Results Review（2:30–3:45）

**旁白要点**:
> 通过 SQL 查询检测结果。确认违规数量、按风险级别的分布。

**Key Visual**: Athena 查询结果 — 违规列表表格

### Section 5: Compliance Report（3:45–5:00）

**旁白要点**:
> AI 自动生成审计报告。展示风险评估、推荐对应措施、优先级操作。

**Key Visual**: 生成的审计报告（风险摘要 + 对应建议）

---

## Screen Capture Plan

| # | 画面 | 部分 |
|---|------|-----------|
| 1 | 文件服务器的文件夹结构 | Section 1 |
| 2 | 工作流执行开始 | Section 2 |
| 3 | ACL 扫描并行处理中 | Section 3 |
| 4 | Athena 违规检测查询结果 | Section 4 |
| 5 | AI 生成审计报告 | Section 5 |

---

## Narration Outline

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "手动对数千个文件夹进行权限审计不切实际" |
| Trigger | 0:45–1:30 | "指定目标卷并开始审计" |
| Analysis | 1:30–2:30 | "自动收集 ACL 并检测策略违规" |
| Results | 2:30–3:45 | "即时掌握违规数量和风险级别" |
| Report | 3:45–5:00 | "自动生成审计报告，展示对应优先级" |

---

## Sample Data Requirements

| # | 数据 | 用途 |
|---|--------|------|
| 1 | 正常权限文件夹（50+） | 基线 |
| 2 | Everyone 完全控制设置（5 件） | 高风险违规 |
| 3 | 离职员工账户残留（3 件） | 中风险违规 |
| 4 | 过度继承文件夹（10 件） | 低风险违规 |

---

## Timeline

### 1 周内可达成

| 任务 | 所需时间 |
|--------|---------|
| 生成样本 ACL 数据 | 2 小时 |
| 工作流执行确认 | 2 小时 |
| 获取屏幕截图 | 2 小时 |
| 创建旁白稿 | 2 小时 |
| 视频编辑 | 4 小时 |

### Future Enhancements

- 通过 Active Directory 集成自动检测离职员工
- 实时权限变更监控
- 自动执行纠正操作

---

## Technical Notes

| 组件 | 角色 |
|--------------|------|
| Step Functions | 工作流编排 |
| Lambda (ACL Collector) | NTFS ACL 元数据收集 |
| Lambda (Policy Checker) | 策略违规规则匹配 |
| Lambda (Report Generator) | 通过 Bedrock 生成审计报告 |
| Amazon Athena | 违规数据的 SQL 分析 |

### 回退方案

| 场景 | 对应 |
|---------|------|
| ACL 收集失败 | 使用预先获取的数据 |
| Bedrock 延迟 | 显示预先生成的报告 |

---

*本文档是技术演示视频的制作指南。*

---

## 关于输出目标：FSxN S3 Access Point (Pattern A)

UC1 legal-compliance 归类为 **Pattern A: Native S3AP Output**
（参考 `docs/output-destination-patterns.md`）。

**设计**：合同元数据、审计日志、摘要报告全部通过 FSxN S3 Access Point
写回到与原始合同数据**相同的 FSx ONTAP 卷**。不创建标准 S3 存储桶
（"no data movement" 模式）。

**CloudFormation 参数**：
- `S3AccessPointAlias`：用于读取输入合同数据的 S3 AP Alias
- `S3AccessPointOutputAlias`：用于输出写入的 S3 AP Alias（可与输入相同）

**部署示例**：
```bash
aws cloudformation deploy \
  --template-file legal-compliance/template-deploy.yaml \
  --stack-name fsxn-legal-compliance-demo \
  --parameter-overrides \
    S3AccessPointAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    S3AccessPointOutputAlias=eda-demo-s3ap-XYZ-ext-s3alias \
    ... (其他必需参数)
```

**从 SMB/NFS 用户的视角**：
```
/vol/contracts/
  ├── 2026/Q2/contract_ABC.pdf         # 原始合同
  └── summaries/2026/05/                # AI 生成摘要（同一卷内）
      └── contract_ABC.json
```

关于 AWS 规范上的限制，请参考
[项目 README 的"AWS 规范上的限制与规避策略"部分](../../README.md#aws-仕様上の制約と回避策)
以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)。

---

## 已验证的 UI/UX 截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 画面**为对象。面向技术人员的视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ✅ **E2E 执行**：Phase 1-6 已确认（参考根 README）
- 📸 **UI/UX 重新拍摄**：✅ 2026-05-10 重新部署验证时已拍摄（确认 UC1 Step Functions 图、Lambda 执行成功）
- 🔄 **重现方法**：参考本文档末尾的"拍摄指南"

### 2026-05-10 重新部署验证时拍摄（以 UI/UX 为中心）

#### UC1 Step Functions Graph view（SUCCEEDED）

![UC1 Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc1-demo/uc1-stepfunctions-graph.png)

Step Functions Graph view 通过颜色可视化各 Lambda / Parallel / Map 状态的执行状况，
是最终用户最重要的画面。

### 现有截图（来自 Phase 1-6 的相关部分）

#### UC1 CloudFormation 堆栈部署完成（2026-05-02 验证时）

![UC1 CloudFormation 堆栈部署完成（2026-05-02 验证时）](../../docs/screenshots/masked/phase1/phase1-cloudformation-uc1-deployed.png)

#### UC1 Step Functions SUCCEEDED（E2E 执行成功）

![UC1 Step Functions SUCCEEDED（E2E 执行成功）](../../docs/screenshots/masked/phase1/phase1-step-functions-uc1-succeeded.png)


### 重新验证时的 UI/UX 目标画面（推荐拍摄列表）

- S3 输出存储桶（audit-reports/、acl-audits/、athena-results/ 前缀）
- Athena 查询结果（ACL 违规检测 SQL）
- Bedrock 生成的审计报告（合规违规摘要）
- SNS 通知邮件（审计警报）

### 拍摄指南

1. **事前准备**：
   - 通过 `bash scripts/verify_phase7_prerequisites.sh` 确认前提（共享 VPC/S3 AP 是否存在）
   - 通过 `UC=legal-compliance bash scripts/package_generic_uc.sh` 打包 Lambda
   - 通过 `bash scripts/deploy_generic_ucs.sh UC1` 部署

2. **放置样本数据**：
   - 通过 S3 AP Alias 将样本文件上传到 `contracts/` 前缀
   - 启动 Step Functions `fsxn-legal-compliance-demo-workflow`（输入 `{}`）

3. **拍摄**（关闭 CloudShell・终端，浏览器右上角的用户名涂黑）：
   - S3 输出存储桶 `fsxn-legal-compliance-demo-output-<account>` 的俯瞰图
   - AI/ML 输出 JSON 的预览（参考 `build/preview_*.html` 格式）
   - SNS 邮件通知（如适用）

4. **遮罩处理**：
   - 通过 `python3 scripts/mask_uc_demos.py legal-compliance-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外遮罩（如需要）

5. **清理**：
   - 通过 `bash scripts/cleanup_generic_ucs.sh UC1` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
