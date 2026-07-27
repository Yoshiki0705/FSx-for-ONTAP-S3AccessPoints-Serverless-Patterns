# 文件门户 — 安全与合规人员指南

> 🌐 Language: [English](../en/portal-compliance-guide.md) | [日本語](../ja/portal-compliance-guide.md) | [한국어](../ko/portal-compliance-guide.md) | **简体中文** | [繁體中文](../zh-TW/portal-compliance-guide.md) | [Français](../fr/portal-compliance-guide.md) | [Deutsch](../de/portal-compliance-guide.md) | [Español](../es/portal-compliance-guide.md)

本指南面向安全官员、合规分析师和数据保护人员，帮助您通过门户**验证**监管控制措施，无需执行存储管理操作。您不需要 `storage-admin` 权限 — 以下所有任务均使用只读访问完成。

---

## 您在门户中的角色

| 您可以执行的操作 | 门户位置 |
|----------------|----------|
| 验证勒索软件保护状态 | 侧边栏 → 🛡️ ARP/AI |
| 确认快照锁定和保留期限 | 侧边栏 → 🔒 Lock |
| 审查审计追踪（谁访问了什么） | 侧边栏 → 🔍 Audit Trail |
| 检查 PHI 防护栏的执行情况 | 侧边栏 → 📂 All Files（导航至 `/dicom/` 或 `/phi/`） |
| 验证输出存储桶的 S3 Object Lock | 侧边栏 → 🔒 Lock → S3 Object Lock 选项卡 |
| 查看 EMS 告警（ONTAP 系统事件） | Admin → Resources（非 `storage-admin` 为只读） |

> **注意**：您无法更改配置（锁定设置、ARP 状态、导出策略）。如需更改，请联系 `storage-admin` 用户。

---

## 任务 1：验证勒索软件保护 (ARP/AI)

**监管背景**：FISC、NIST CSF DE.CM-4、ISO 27001 A.12.2

1. 点击侧边栏中的 **🛡️ ARP/AI**
2. 确认每个受监控卷显示绿色状态（🟢 无威胁）
3. 如果出现威胁标记（🔴），记录卷名称和检测时间戳
4. 检查**事件生命周期标记**以了解当前响应阶段：
   - 🔴 已检测 — 威胁已识别，等待遏制
   - 🟠 已遏制 — 攻击者访问已阻止，快照已保留
   - 🟡 调查中 — 取证分析进行中
   - 🟢 已解决 — 事件关闭

**审计证据**：截图 ARP 面板，显示所有卷的保护状态 + 活动事件标记及时间戳。

---

## 任务 2：确认快照不可变性 (WORM)

**监管背景**：SEC 17a-4、FISC 7 年保留、HIPAA 6 年、SOX 5 年、NARA

1. 点击侧边栏中的 **🔒 Lock**
2. 检查三个选项卡：

### 选项卡 A：ONTAP SnapLock
- 验证卷类型：**Compliance**（包括 root 在内任何人都无法删除）或 **Enterprise**（管理员可释放）
- 检查保留期限是否符合您的策略：
  - 最短期限 ≥ 监管要求
  - Compliance Clock 已初始化并运行

### 选项卡 B：S3 Object Lock
- 验证输出存储桶已启用 Object Lock
- 确认模式：监管归档用 **Compliance**，AI 输出用 **Governance**
- 检查默认保留天数是否符合要求

### 选项卡 C：Tamperproof Snapshots
- 检查已锁定快照表格：名称、创建时间、过期时间
- 验证过期日期是否符合监管保留要求：

| 法规 | 必要保留期限 | 预期过期时间 |
|------|-------------|-------------|
| FISC | 7 年（2,557 天） | 创建 + 7 年 |
| HIPAA | 6 年（2,192 天） | 创建 + 6 年 |
| SOX/J-SOX | 5 年（1,825 天） | 创建 + 5 年 |
| NARA | 3-75 年（不等） | 按记录计划 |

**审计证据**：截图每个选项卡，显示锁定状态 + 保留期限。

---

## 任务 3：审查审计追踪

**监管背景**：FISC、SOX Section 302/404、HIPAA §164.312(b)、PCI DSS 10.x

1. 点击侧边栏中的 **🔍 Audit Trail**
2. 面板显示 S3 Access Point 的 CloudTrail S3 数据事件
3. 需要审查的关键字段：
   - **谁**：IAM 主体（Cognito 用户身份）
   - **何时**：事件时间戳 (UTC)
   - **做了什么**：API 操作（`GetObject`、`PutObject`、`ListObjectsV2`）
   - **哪个文件**：S3 键（文件路径）
4. 如果调查特定事件，按日期范围或用户进行筛选

**审计证据**：导出或截图按审查期间筛选的审计追踪。

---

## 任务 4：验证 PHI 防护栏

**监管背景**：HIPAA §164.502（最小必要原则）、45 CFR 164.514

1. 点击侧边栏中的 **📂 All Files**
2. 导航到名为 `/dicom/`、`/phi/`、`/pii/` 或 `/hipaa/` 的文件夹
3. 观察 AI 处理按钮显示：**🚫 PHI — AI Blocked**
4. 验证按钮已禁用（无论用户角色如何都无法点击）

**含义**：这些受保护路径中的文件在结构上被阻止发送到外部 AI 服务（Bedrock、Rekognition、Textract、Comprehend）。这在 UI 层通过路径模式匹配实现，任何用户都无法覆盖。

**局限性**：此防护栏依赖于文件夹命名约定。放置在非受保护路径中的包含 PHI 内容的文件不会被阻止。请确保组织的文件夹结构策略在上游得到执行。

**审计证据**：截图显示 `/dicom/` 文件夹中已禁用的 AI 按钮。

---

## 任务 5：验证 AI 输出的 S3 Object Lock

**监管背景**：SEC 17a-4(f)、CFTC 1.31、FINRA 4511

1. 点击 **🔒 Lock** → **S3 Object Lock** 选项卡
2. 验证：
   - 输出存储桶已**启用** Object Lock
   - 模式适当：监管归档用 **Compliance**（不可变）或 AI 输出用 **Governance**（有权限可覆盖）
   - 默认保留期限与您的保留计划匹配
3. 如果未配置 Object Lock，请上报给 `storage-admin` 用户

**重要性**：存储在 S3 中的 AI 处理结果（分类标签、提取的文本、合规报告）本身可能是监管记录。Object Lock 确保这些输出在保留期间内不能被更改或删除。

---

## 任务 6：事件响应验证

当检测到勒索软件事件时：

1. 前往 **🛡️ ARP/AI** → 检查事件标记状态
2. 验证遏制已执行：
   - 快照已拍摄（保留证据）
   - 可疑用户/IP 已阻止
3. 前往 **🔍 Audit Trail** → 筛选检测时间戳前后的事件
4. 记录时间线：检测时间 → 遏制时间 → 调查开始
5. 解决后，验证事件标记显示 🟢 已解决

**事件时间线 SLA 参考**：

| 阶段 | 典型时长 | 您的 SLA |
|------|:---:|:---:|
| 检测 → 遏制 | < 5 分钟（自动） | _____ |
| 遏制 → 调查开始 | < 1 小时 | _____ |
| 调查 → 解决 | 视情况而定 | _____ |

---

## 监管映射

| 门户功能 | FISC | HIPAA | SOX | NIST CSF | ISO 27001 |
|---------|:---:|:---:|:---:|:---:|:---:|
| ARP/AI 勒索软件检测 | ✅ | ✅ | — | DE.CM-4 | A.12.2 |
| SnapLock (Compliance 模式) | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| S3 Object Lock | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| Tamperproof Snapshots | ✅ | ✅ | ✅ | PR.DS-1 | A.12.3 |
| PHI 防护栏 | — | ✅ | — | PR.AC-4 | A.9.4 |
| Audit Trail (CloudTrail) | ✅ | ✅ | ✅ | DE.AE-3 | A.12.4 |
| 事件生命周期追踪 | ✅ | ✅ | — | RS.RP-1 | A.16.1 |

---

## 您无法执行的操作（及负责人）

| 操作 | 所需组 | 联系人 |
|------|:---:|--------|
| 更改 ARP/AI 状态 | `storage-admin` | 存储管理员 |
| 锁定/解锁快照 | `storage-admin` | 存储管理员 |
| 配置 S3 Object Lock | `storage-admin` | 存储管理员 |
| 阻止/解除用户（遏制） | `storage-admin` | 安全运营 + 存储管理员 |
| 创建/删除卷 | `storage-admin` | 存储管理员 |
| 修改导出策略 | `storage-admin` | 存储管理员 |

---

## 相关文档

| 文档 | 用途 |
|------|------|
| [用户指南](portal-user-guide.md) | 最终用户日常操作 |
| [授权模型](portal-authorization-model.md) | 完整权限矩阵 |
| [管理员演示指南](admin-resource-management-demo.md) | 存储管理操作 |
| [事件响应手册](../../docs/incident-response-playbook.md) | 完整事件响应流程 |
| [快速参考卡](portal-quick-reference.md) | 1 页速查 |
