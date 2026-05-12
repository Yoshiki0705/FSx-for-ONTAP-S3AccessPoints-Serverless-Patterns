# EDA 设计文件验证 — 演示指南

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## 执行摘要

本指南定义了面向半导体设计工程师的技术演示。演示将展示设计文件（GDS/OASIS）的自动质量验证工作流，并展示在流片前提高设计审查效率的价值。

**演示的核心信息**：将设计工程师手动进行的跨 IP 块质量检查，通过自动化工作流在几分钟内完成，并通过 AI 生成的设计审查报告立即采取行动。

**预计时间**：3～5 分钟（带旁白的屏幕录制视频）

---

## 目标受众与角色

### 主要受众：EDA 最终用户（设计工程师）

| 项目 | 详细信息 |
|------|------|
| **职位** | Physical Design Engineer / DRC Engineer / Design Lead |
| **日常工作** | 布局设计、DRC 执行、IP 块集成、流片准备 |
| **挑战** | 跨多个 IP 块全面了解质量需要大量时间 |
| **工具环境** | Calibre、Virtuoso、IC Compiler、Innovus 等 EDA 工具 |
| **期望成果** | 早期发现设计质量问题，遵守流片时间表 |

### 角色：田中先生（Physical Design Lead）

- 管理大规模 SoC 项目中的 40+ IP 块
- 需要在流片前 2 周对所有块进行质量审查
- 逐个检查每个块的 GDS/OASIS 文件不切实际
- "希望一目了然地掌握所有块的质量摘要"

---

## 演示场景：流片前质量审查

### 场景概述

在流片前的质量审查阶段，设计负责人对多个 IP 块（40+ 文件）执行自动质量验证，并根据 AI 生成的审查报告决定行动方案。

### 整体工作流程

```
设计文件群        自动验证          分析结果           AI 审查
(GDS/OASIS)    →   工作流     →   统计汇总    →    报告生成
                    触发           (Athena SQL)     (自然语言)
```

### 演示展示的价值

1. **节省时间**：将手动需要数天的跨块审查在几分钟内完成
2. **全面性**：对所有 IP 块进行无遗漏验证
3. **定量判断**：通过统计异常值检测（IQR 方法）进行客观质量评估
4. **可操作性**：AI 提供具体的推荐对应措施

---

## 故事板（5 个部分 / 3～5 分钟）

### Section 1: 问题陈述（0:00–0:45）

**画面**：设计项目的文件列表（40+ GDS/OASIS 文件）

**旁白要点**：
> 流片前 2 周。需要确认 40 多个 IP 块的设计质量。
> 用 EDA 工具逐个打开每个文件进行检查不现实。
> 单元数异常、边界框异常值、命名规则违规——需要一种跨块检测这些问题的方法。

**关键视觉**：
- 设计文件的目录结构（.gds、.gds2、.oas、.oasis）
- "手动审查：预计 3～5 天"的文本叠加

---

### Section 2: 工作流触发（0:45–1:30）

**画面**：设计工程师触发质量验证工作流的操作

**旁白要点**：
> 达到设计里程碑后，启动质量验证工作流。
> 只需指定目标目录，即可开始对所有设计文件的自动验证。

**关键视觉**：
- 工作流执行画面（Step Functions 控制台）
- 输入参数：目标卷路径、文件过滤器（.gds/.oasis）
- 执行开始确认

**工程师的操作**：
```
目标：/vol/eda_designs/ 下的所有设计文件
过滤器：.gds、.gds2、.oas、.oasis
执行：质量验证工作流开始
```

---

### Section 3: 自动分析（1:30–2:30）

**画面**：工作流执行中的进度显示

**旁白要点**：
> 工作流自动执行以下操作：
> 1. 设计文件的检测和列表化
> 2. 从每个文件的头部提取元数据（library_name、cell_count、bounding_box、units）
> 3. 对提取的数据进行统计分析（SQL 查询）
> 4. AI 生成设计审查报告
>
> 即使是大容量的 GDS 文件（数 GB），也只读取头部（64KB），因此处理速度很快。

**关键视觉**：
- 工作流的各个步骤依次完成的情况
- 并行处理（Map State）同时处理多个文件的显示
- 处理时间：约 2～3 分钟（40 个文件的情况）

---

### Section 4: 结果审查（2:30–3:45）

**画面**：Athena SQL 查询结果和统计摘要

**旁白要点**：
> 可以使用 SQL 自由查询分析结果。
> 例如，可以进行"显示边界框异常大的单元"等临时分析。

**关键视觉 — Athena 查询示例**：
```sql
-- 边界框异常值检测
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**关键视觉 — 查询结果**：

| file_key | library_name | width | height | 判定 |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | 异常值 |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | 异常值 |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | 异常值 |

---

### Section 5: 可操作的洞察（3:45–5:00）

**画面**：AI 生成的设计审查报告

**旁白要点**：
> AI 解释统计分析结果，自动生成面向设计工程师的审查报告。
> 包含风险评估、具体的推荐对应措施、按优先级排列的行动项。
> 基于此报告，可以在流片前的审查会议上立即开始讨论。

**关键视觉 — AI 审查报告（摘录）**：

```markdown
# 设计审查报告

## 风险评估：Medium

## 检测事项摘要
- 边界框异常值：3 件
- 命名规则违规：2 件
- 无效文件：2 件

## 推荐对应措施（按优先级）
1. [High] 调查 2 个无效文件的原因
2. [Medium] 考虑优化 analog_frontend.oas 的布局
3. [Low] 统一命名规则（block-a-io → block_a_io）
```

**结束语**：
> 手动需要数天的跨块审查，在几分钟内完成。
> 设计工程师可以专注于确认分析结果和决定行动方案。

---

## 屏幕录制计划

### 所需屏幕录制列表

| # | 画面 | 部分 | 备注 |
|---|------|-----------|------|
| 1 | 设计文件目录列表 | Section 1 | FSx ONTAP 上的文件结构 |
| 2 | 工作流执行开始画面 | Section 2 | Step Functions 控制台 |
| 3 | 工作流执行中（Map State 并行处理） | Section 3 | 可见进度状态 |
| 4 | 工作流完成画面 | Section 3 | 所有步骤成功 |
| 5 | Athena 查询编辑器 + 结果 | Section 4 | 异常值检测查询 |
| 6 | 元数据 JSON 输出示例 | Section 4 | 1 个文件的提取结果 |
| 7 | AI 设计审查报告全文 | Section 5 | Markdown 渲染显示 |
| 8 | SNS 通知邮件 | Section 5 | 报告完成通知 |

### 录制步骤

1. 在演示环境中放置样本数据
2. 手动执行工作流，在每个步骤进行屏幕录制
3. 在 Athena 控制台执行查询并录制结果
4. 从 S3 下载生成的报告并显示

---

## 已验证的 UI/UX 截图（2026-05-10 重新验证）

与 Phase 7 UC15/16/17 相同的方针，拍摄**设计工程师在日常工作中实际看到的 UI/UX 画面**。
排除 Step Functions 图表等面向技术人员的视图（详情参见
[`docs/verification-results-phase7.md`](../../docs/verification-results-phase7.md)）。

### 1. FSx for NetApp ONTAP Volumes — 设计文件用卷

从设计工程师角度看到的 ONTAP 卷列表。在 `eda_demo_vol` 中以 NTFS ACL 管理的状态放置 GDS/OASIS 文件。

<!-- SCREENSHOT: uc6-fsx-volumes-list.png
     内容：FSx 控制台中的 ONTAP Volumes 列表（eda_demo_vol 等），Status=Created，Type=ONTAP
     掩码：账户 ID、SVM ID 的实际值、文件系统 ID -->
![UC6: FSx Volumes 列表](../../docs/screenshots/masked/uc6-demo/uc6-fsx-volumes-list.png)

### 2. S3 输出存储桶 — 设计文档·分析结果列表

设计审查负责人在工作流完成后确认结果的画面。
整理为 `metadata/` / `athena-results/` / `reports/` 三个前缀。

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容：S3 控制台中确认 bucket 的 top-level prefix
     掩码：账户 ID、存储桶名称前缀 -->
![UC6: S3 输出存储桶](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 2. S3 输出存储桶 — 设计文档·分析结果列表

设计审查负责人在工作流完成后确认结果的画面。
整理为 `metadata/` / `athena-results/` / `reports/` 三个前缀。

<!-- SCREENSHOT: uc6-s3-output-bucket.png
     内容：S3 控制台中确认 bucket 的 top-level prefix
     掩码：账户 ID、存储桶名称前缀 -->
![UC6: S3 输出存储桶](../../docs/screenshots/masked/uc6-demo/uc6-s3-output-bucket.png)

### 3. Athena 查询结果 — EDA 元数据的 SQL 分析

设计负责人临时探索 DRC 信息的画面。
Workgroup 为 `fsxn-eda-uc6-workgroup`，数据库为 `fsxn-eda-uc6-db`。

<!-- SCREENSHOT: uc6-athena-query-result.png
     内容：EDA 元数据表的 SELECT 结果（file_key、library_name、cell_count、bounding_box）
     掩码：账户 ID -->
![UC6: Athena 查询结果](../../docs/screenshots/masked/uc6-demo/uc6-athena-query-result.png)

### 4. Bedrock 生成的设计审查报告

**UC6 的亮点功能**：基于 Athena 的 DRC 汇总结果，Bedrock Nova Lite 生成
面向 Physical Design Lead 的日语审查报告。

<!-- SCREENSHOT: uc6-bedrock-design-review.png
     内容：执行摘要 + 单元数分析 + 命名规则违规列表 + 风险评估 (High/Medium/Low)
     实际样本内容：
       ## 设计审查摘要
       ### 执行摘要
       基于本次 DRC 汇总结果，设计质量的整体评估如下。
       设计文件共 2 个，单元数分布稳定，未确认边界框异常值。
       但是，发现了 6 个命名规则违规。
       ...
       ### 风险评估
       - **High**：无
       - **Medium**：确认了 6 个命名规则违规。
       - **Low**：单元数分布和边界框异常值没有问题。
     掩码：账户 ID -->
![UC6: Bedrock 设计审查报告](../../docs/screenshots/masked/uc6-demo/uc6-bedrock-design-review.png)

### 实测值（2026-05-10 AWS 部署验证）

- **Step Functions 执行时间**：~30 秒（Discovery + Map(2 files) + DRC + Report）
- **Bedrock 生成报告**：2,093 bytes（Markdown 格式的日语）
- **Athena 查询**：0.02 KB 扫描，运行时间 812 ms
- **实际堆栈**：`fsxn-eda-uc6`（ap-northeast-1，2026-05-10 时点运行中）

---

## 旁白大纲

### 语气与风格

- **视角**：设计工程师（田中先生）的第一人称视角
- **语气**：实务型、问题解决型
- **语言**：日语（英语字幕选项）
- **速度**：缓慢清晰（因为是技术演示）

### 旁白构成

| 部分 | 时间 | 关键信息 |
|-----------|------|--------------|
| Problem | 0:00–0:45 | "流片前需要确认 40+ 块的质量。手动无法按时完成" |
| Trigger | 0:45–1:30 | "设计里程碑后只需启动工作流" |
| Analysis | 1:30–2:30 | "头部解析 → 元数据提取 → 统计分析自动进行" |
| Results | 2:30–3:45 | "使用 SQL 自由查询。立即识别异常值" |
| Insights | 3:45–5:00 | "AI 报告提供按优先级排列的行动方案。直接用于审查会议" |

---

## 样本数据要求

### 所需样本数据

| # | 文件 | 格式 | 用途 |
|---|---------|------------|------|
| 1 | `top_chip_v3.gds` | GDSII | 主芯片（大规模，1000+ 单元） |
| 2 | `block_a_io.gds2` | GDSII | I/O 块（正常数据） |
| 3 | `memory_ctrl.oasis` | OASIS | 内存控制器（正常数据） |
| 4 | `analog_frontend.oas` | OASIS | 模拟块（异常值：BB 大） |
| 5 | `test_block_debug.gds` | GDSII | 调试用（异常值：高度异常） |
| 6 | `legacy_io_v1.gds2` | GDSII | 遗留块（异常值：宽度·高度） |
| 7 | `block-a-io.gds2` | GDSII | 命名规则违规样本 |
| 8 | `TOP CHIP (copy).gds` | GDSII | 命名规则违规样本 |

### 样本数据生成方针

- **最小配置**：8 个文件（上述列表）覆盖演示的所有场景
- **推荐配置**：40+ 文件（提高统计分析的说服力）
- **生成方法**：使用 Python 脚本生成具有有效 GDSII/OASIS 头部的测试文件
- **大小**：仅进行头部解析，每个文件约 100KB 即可

### 现有演示环境的确认事项

- [ ] FSx ONTAP 卷中是否已放置样本数据
- [ ] S3 Access Point 是否已配置
- [ ] Glue Data Catalog 的表定义是否存在
- [ ] Athena 工作组是否可用

---

## 时间表

### 1 周内可实现

| # | 任务 | 所需时间 | 前提条件 |
|---|--------|---------|---------|
| 1 | 样本数据生成（8 个文件） | 2 小时 | Python 环境 |
| 2 | 演示环境中的工作流执行确认 | 2 小时 | 已部署环境 |
| 3 | 屏幕录制获取（8 个画面） | 3 小时 | 任务 2 完成后 |
| 4 | 旁白脚本最终化 | 2 小时 | 任务 3 完成后 |
| 5 | 视频编辑（录制 + 旁白） | 4 小时 | 任务 3、4 完成后 |
| 6 | 审查与修改 | 2 小时 | 任务 5 完成后 |
| **合计** | | **15 小时** | |

### 前提条件（1 周内实现所需）

- Step Functions 工作流已部署且正常运行
- Lambda 函数（Discovery、MetadataExtraction、DrcAggregation、ReportGeneration）已确认运行
- Athena 表和查询可执行
- Bedrock 模型访问已启用

### 未来增强（将来的扩展）

| # | 扩展项目 | 概要 | 优先级 |
|---|---------|------|--------|
| 1 | DRC 工具集成 | 直接导入 Calibre/Pegasus 的 DRC 结果文件 | High |
| 2 | 交互式仪表板 | 使用 QuickSight 的设计质量仪表板 | Medium |
| 3 | Slack/Teams 通知 | 审查报告完成时的聊天通知 | Medium |
| 4 | 差异审查 | 自动检测并报告与上次执行的差异 | High |
| 5 | 自定义规则定义 | 可设置项目特定的质量规则 | Medium |
| 6 | 多语言报告 | 生成英语/日语/中文报告 | Low |
| 7 | CI/CD 集成 | 作为设计流程中的自动质量门集成 | High |
| 8 | 大规模数据支持 | 优化 1000+ 文件的并行处理 | Medium |

---

## 技术说明（演示制作者用）

### 使用组件（仅现有实现）

| 组件 | 作用 |
|--------------|------|
| Step Functions | 整体工作流的编排 |
| Lambda (Discovery) | 设计文件的检测·列表化 |
| Lambda (MetadataExtraction) | GDSII/OASIS 头部解析和元数据提取 |
| Lambda (DrcAggregation) | 通过 Athena SQL 执行统计分析 |
| Lambda (ReportGeneration) | 通过 Bedrock 生成 AI 审查报告 |
| Amazon Athena | 对元数据的 SQL 查询 |
| Amazon Bedrock | 自然语言报告生成（Nova Lite / Claude） |

### 演示执行时的备用方案

| 场景 | 对应 |
|---------|------|
| 工作流执行失败 | 使用预先录制的执行画面 |
| Bedrock 响应延迟 | 显示预先生成的报告 |
| Athena 查询超时 | 显示预先获取的结果 CSV |
| 网络故障 | 将所有画面预先录制为视频 |

---

*本文档作为技术演示视频的制作指南而创建。*
