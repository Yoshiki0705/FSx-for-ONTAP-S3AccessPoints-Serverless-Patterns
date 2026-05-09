# EDA 设计文件验证 — 演示指南

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

## Executive Summary

本指南定义了面向半导体设计工程师的技术演示。演示展示设计文件（GDS/OASIS）的自动质量验证工作流，体现简化流片前设计审查的价值。

**演示核心信息**：将设计工程师以往手动执行的跨 IP 模块质量检查，通过自动化工作流在数分钟内完成，并通过 AI 生成的设计审查报告实现即时行动。

**预计时长**：3～5 分钟（带旁白的屏幕录制视频）

---

## Target Audience & Persona

### Primary Audience：EDA 最终用户（设计工程师）

| 项目 | 详情 |
|------|------|
| **职位** | Physical Design Engineer / DRC Engineer / Design Lead |
| **日常工作** | 版图设计、DRC 执行、IP 模块集成、流片准备 |
| **挑战** | 跨多个 IP 模块全面了解质量状况耗时较长 |
| **工具环境** | Calibre、Virtuoso、IC Compiler、Innovus 等 EDA 工具 |
| **期望成果** | 尽早发现设计质量问题，确保流片进度 |

### Persona：田中先生（Physical Design Lead）

- 在大规模 SoC 项目中管理 40 个以上的 IP 模块
- 需要在流片前 2 周对所有模块进行质量审查
- 逐个检查各模块的 GDS/OASIS 文件不切实际
- "希望一目了然地掌握所有模块的质量概况"

---

## Demo Scenario: Pre-tapeout Quality Review

### 场景概述

在流片前质量审查阶段，设计负责人对多个 IP 模块（40 个以上文件）执行自动质量验证，并根据 AI 生成的审查报告决定后续行动。

### 整体工作流

```
设计文件群        自动验证          分析结果           AI 审查
(GDS/OASIS)    →   工作流    →   统计汇总    →    报告生成
                    触发           (Athena SQL)     (自然语言)
```

### 演示展示的价值

1. **时间缩短**：将手动需要数天的横向审查在数分钟内完成
2. **完整性**：无遗漏地验证所有 IP 模块
3. **定量判断**：通过统计异常值检测（IQR 方法）进行客观质量评估
4. **可操作性**：AI 提出具体的建议措施

---

## Storyboard（5 个部分 / 3～5 分钟）

### Section 1: Problem Statement（0:00–0:45）

**画面**：设计项目的文件列表（40 个以上 GDS/OASIS 文件）

**旁白要点**：
> 流片前 2 周。需要确认 40 个以上 IP 模块的设计质量。
> 用 EDA 工具逐个打开每个文件进行检查不现实。
> 单元数异常、边界框异常值、命名规则违规——需要一种横向检测这些问题的方法。

**Key Visual**：
- 设计文件目录结构（.gds、.gds2、.oas、.oasis）
- "手动审查：预计 3～5 天"文字叠加

---

### Section 2: Workflow Trigger（0:45–1:30）

**画面**：设计工程师触发质量验证工作流的操作

**旁白要点**：
> 达到设计里程碑后，启动质量验证工作流。
> 只需指定目标目录，所有设计文件的自动验证即开始。

**Key Visual**：
- 工作流执行画面（Step Functions 控制台）
- 输入参数：目标卷路径、文件过滤器（.gds/.oasis）
- 执行开始确认

**工程师操作**：
```
目标：/vol/eda_designs/ 下的所有设计文件
过滤器：.gds、.gds2、.oas、.oasis
执行：启动质量验证工作流
```

---

### Section 3: Automated Analysis（1:30–2:30）

**画面**：工作流执行中的进度显示

**旁白要点**：
> 工作流自动执行以下操作：
> 1. 设计文件的检测和列表化
> 2. 从各文件头部提取元数据（library_name、cell_count、bounding_box、units）
> 3. 对提取数据进行统计分析（SQL 查询）
> 4. AI 生成设计审查报告
>
> 即使是大容量 GDS 文件（数 GB），由于只读取头部（64KB），处理速度也很快。

**Key Visual**：
- 工作流各步骤依次完成的过程
- 并行处理（Map State）显示多个文件同时处理
- 处理时间：约 2～3 分钟（40 个文件的情况）

---

### Section 4: Results Review（2:30–3:45）

**画面**：Athena SQL 查询结果和统计摘要

**旁白要点**：
> 分析结果可以用 SQL 自由查询。
> 例如，可以进行"显示边界框异常大的单元"等即席分析。

**Key Visual — Athena 查询示例**：
```sql
-- 边界框异常值检测
SELECT file_key, library_name, 
       bounding_box_width, bounding_box_height
FROM eda_metadata
WHERE bounding_box_width > (SELECT Q3 + 1.5 * IQR FROM stats)
ORDER BY bounding_box_width DESC;
```

**Key Visual — 查询结果**：

| file_key | library_name | width | height | 判定 |
|----------|-------------|-------|--------|------|
| analog_frontend.oas | ANALOG_FE | 15200.3 | 12100.8 | 异常值 |
| test_block_debug.gds | TEST_DBG | 8900.1 | 14500.2 | 异常值 |
| legacy_io_v1.gds2 | LEGACY_IO | 11200.5 | 13800.7 | 异常值 |

---

### Section 5: Actionable Insights（3:45–5:00）

**画面**：AI 生成的设计审查报告

**旁白要点**：
> AI 解读统计分析结果，自动生成面向设计工程师的审查报告。
> 包含风险评估、具体建议措施和按优先级排列的行动项。
> 基于此报告，可以在流片前审查会议上立即开始讨论。

**Key Visual — AI 审查报告（摘录）**：

```markdown
# 设计审查报告

## 风险评估：Medium

## 检测事项摘要
- 边界框异常值：3 项
- 命名规则违规：2 项
- 无效文件：2 项

## 建议措施（按优先级）
1. [High] 调查 2 个无效文件的原因
2. [Medium] 考虑 analog_frontend.oas 的版图优化
3. [Low] 统一命名规则（block-a-io → block_a_io）
```

**结尾**：
> 以往手动需要数天的横向审查，现在数分钟即可完成。
> 设计工程师可以专注于确认分析结果和决定行动方案。

---

## Screen Capture Plan

### 所需屏幕截图列表

| # | 画面 | 部分 | 备注 |
|---|------|------|------|
| 1 | 设计文件目录列表 | Section 1 | FSx ONTAP 上的文件结构 |
| 2 | 工作流执行开始画面 | Section 2 | Step Functions 控制台 |
| 3 | 工作流执行中（Map State 并行处理） | Section 3 | 可见进度状态 |
| 4 | 工作流完成画面 | Section 3 | 所有步骤成功 |
| 5 | Athena 查询编辑器 + 结果 | Section 4 | 异常值检测查询 |
| 6 | 元数据 JSON 输出示例 | Section 4 | 1 个文件的提取结果 |
| 7 | AI 设计审查报告全文 | Section 5 | Markdown 渲染显示 |
| 8 | SNS 通知邮件 | Section 5 | 报告完成通知 |

### 截图步骤

1. 在演示环境中放置示例数据
2. 手动执行工作流，在每个步骤进行屏幕截图
3. 在 Athena 控制台执行查询并截取结果
4. 从 S3 下载生成的报告并显示

---

## Narration Outline

### 语调与风格

- **视角**：设计工程师（田中先生）的第一人称视角
- **语调**：务实、问题解决型
- **语言**：日语（可选英文字幕）
- **语速**：缓慢清晰（技术演示）

### 旁白结构

| 部分 | 时间 | 关键信息 |
|------|------|---------|
| Problem | 0:00–0:45 | "流片前需要确认 40 个以上模块的质量。手动来不及" |
| Trigger | 0:45–1:30 | "设计里程碑后只需启动工作流" |
| Analysis | 1:30–2:30 | "头部解析 → 元数据提取 → 统计分析自动进行" |
| Results | 2:30–3:45 | "用 SQL 自由查询。立即定位异常值" |
| Insights | 3:45–5:00 | "AI 报告提出优先级行动。直接对接审查会议" |

---

## Sample Data Requirements

### 所需示例数据

| # | 文件 | 格式 | 用途 |
|---|------|------|------|
| 1 | `top_chip_v3.gds` | GDSII | 主芯片（大规模，1000+ 单元） |
| 2 | `block_a_io.gds2` | GDSII | I/O 模块（正常数据） |
| 3 | `memory_ctrl.oasis` | OASIS | 内存控制器（正常数据） |
| 4 | `analog_frontend.oas` | OASIS | 模拟模块（异常值：大 BB） |
| 5 | `test_block_debug.gds` | GDSII | 调试用（异常值：高度异常） |
| 6 | `legacy_io_v1.gds2` | GDSII | 旧版模块（异常值：宽度·高度） |
| 7 | `block-a-io.gds2` | GDSII | 命名规则违规示例 |
| 8 | `TOP CHIP (copy).gds` | GDSII | 命名规则违规示例 |

### 示例数据生成方针

- **最小配置**：8 个文件（上述列表）覆盖演示的所有场景
- **推荐配置**：40 个以上文件（提高统计分析的说服力）
- **生成方法**：用 Python 脚本生成具有有效 GDSII/OASIS 头部的测试文件
- **大小**：由于只进行头部解析，每个文件约 100KB 即可

### 现有演示环境确认事项

- [ ] 示例数据是否已放置在 FSx ONTAP 卷上
- [ ] S3 Access Point 是否已配置
- [ ] Glue Data Catalog 表定义是否存在
- [ ] Athena 工作组是否可用

---

## Timeline

### 1 周内可达成

| # | 任务 | 所需时间 | 前提条件 |
|---|------|---------|---------|
| 1 | 示例数据生成（8 个文件） | 2 小时 | Python 环境 |
| 2 | 演示环境中工作流执行确认 | 2 小时 | 已部署环境 |
| 3 | 屏幕截图获取（8 个画面） | 3 小时 | 任务 2 完成后 |
| 4 | 旁白脚本定稿 | 2 小时 | 任务 3 完成后 |
| 5 | 视频编辑（截图 + 旁白） | 4 小时 | 任务 3、4 完成后 |
| 6 | 审查与修改 | 2 小时 | 任务 5 完成后 |
| **合计** | | **15 小时** | |

### 前提条件（1 周达成所需）

- Step Functions 工作流已部署且正常运行
- Lambda 函数（Discovery、MetadataExtraction、DrcAggregation、ReportGeneration）已验证
- Athena 表和查询可执行
- Bedrock 模型访问已启用

### Future Enhancements（未来扩展）

| # | 扩展项目 | 概述 | 优先级 |
|---|---------|------|--------|
| 1 | DRC 工具集成 | 直接导入 Calibre/Pegasus 的 DRC 结果文件 | High |
| 2 | 交互式仪表板 | 通过 QuickSight 实现设计质量仪表板 | Medium |
| 3 | Slack/Teams 通知 | 审查报告完成时发送聊天通知 | Medium |
| 4 | 差异审查 | 自动检测并报告与上次执行的差异 | High |
| 5 | 自定义规则定义 | 可设置项目特定的质量规则 | Medium |
| 6 | 多语言报告 | 支持英语/日语/中文的报告生成 | Low |
| 7 | CI/CD 集成 | 作为设计流程中的自动质量门嵌入 | High |
| 8 | 大规模数据支持 | 1000 个以上文件的并行处理优化 | Medium |

---

## Technical Notes（演示制作者用）

### 使用组件（仅现有实现）

| 组件 | 角色 |
|------|------|
| Step Functions | 整体工作流编排 |
| Lambda (Discovery) | 设计文件检测和列表化 |
| Lambda (MetadataExtraction) | GDSII/OASIS 头部解析和元数据提取 |
| Lambda (DrcAggregation) | 通过 Athena SQL 执行统计分析 |
| Lambda (ReportGeneration) | 通过 Bedrock 生成 AI 审查报告 |
| Amazon Athena | 对元数据的 SQL 查询 |
| Amazon Bedrock | 自然语言报告生成（Nova Lite / Claude） |

### 演示执行时的回退方案

| 场景 | 应对 |
|------|------|
| 工作流执行失败 | 使用预先录制的执行画面 |
| Bedrock 响应延迟 | 显示预先生成的报告 |
| Athena 查询超时 | 显示预先获取的结果 CSV |
| 网络故障 | 所有画面预先截取并制作为视频 |

---

*本文档作为技术演示视频的制作指南而创建。*
