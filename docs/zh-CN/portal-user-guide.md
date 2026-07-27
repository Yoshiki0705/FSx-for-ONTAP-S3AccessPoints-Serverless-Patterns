# 文件门户 — 用户指南

> 🌐 Language: [English](../en/portal-user-guide.md) | [日本語](../ja/portal-user-guide.md) | [한국어](../ko/portal-user-guide.md) | **简体中文** | [繁體中文](../zh-TW/portal-user-guide.md) | [Français](../fr/portal-user-guide.md) | [Deutsch](../de/portal-user-guide.md) | [Español](../es/portal-user-guide.md)

本指南面向已被邀请使用已部署 File Portal 的最终用户。本文档假设门户管理员已完成部署并创建了您的账户 — 您无需具备 AWS CLI 访问权限或部署知识。

**此门户的功能**: 通过浏览器浏览 NAS 文件、触发 AI/ML 分析、查看结果并检查数据保护状态 — 无需 VPN 或 SMB/NFS 客户端设置。

---

## 入门

### 1. 登录

1. 打开管理员提供的门户 URL
2. 输入您的邮箱和密码（根据配置为管理员提供或自行注册）
3. 如果启用了 MFA，请输入验证器应用中的 TOTP 代码
4. 首次登录时，**Welcome Modal** 将引导您了解 3 项关键功能：
   - 📂 文件浏览 — 在浏览器中浏览 NAS 文件
   - ⚡ AI 处理 — 选择文件并触发工作流
   - 🔒 数据保护 — 快照、锁定和勒索软件状态

> **提示**: 勾选"不再显示"可在后续登录时跳过 Welcome Modal。

### 2. 门户布局

```
┌─────────────────────────────────────────────────────────┐
│ [☰] File Portal              🌐 ZH ▾   user@example.com │
├───────────────┬─────────────────────────────────────────┤
│ 侧边栏       │  主内容区                               │
│ (导航)        │                                         │
│               │                      AI 助手面板 →      │
└───────────────┴─────────────────────────────────────────┘
```

- **左侧边栏**: 按浏览、AI & 处理、数据保护、管理分组的导航
- **主内容区**: 活动区域（点击侧边栏项目时切换）
- **右侧面板**: AI 助手（在 All Files 中选择文件时显示）
- **顶部栏**: 语言切换器、用户邮箱、退出登录

### 3. 语言

点击顶部栏的 🌐 语言选择器可在 8 种语言间切换：日本語、English、한국어、简体中文、繁體中文、Français、Deutsch、Español。切换即时生效，无需重新加载页面。

---

## 浏览 — 文件操作

### All Files

您的主要文件浏览器。通过 S3 Access Point 显示 FSx for ONTAP 卷的内容。

| 操作 | 方法 |
|------|------|
| 浏览文件夹 | 点击文件夹名称 |
| 返回上一级 | 点击文件列表顶部的 `..` |
| 预览图片 | 点击图片文件旁的 🖼️ 图标 |
| 预览 PDF | 点击 📕 图标 — 在浏览器内置查看器中打开 |
| 预览 Word 文档 | 点击 📝 图标 — 在浏览器中渲染 |
| 下载文件 | 点击 📄 图标 |
| 创建分享链接 | 点击 🔗 → 选择 TTL（5 分钟 / 15 分钟 / 1 小时）→ 复制 URL |
| 向 AI 询问文件相关问题 | 选择文件 → 在右侧 AI 面板中输入问题 |
| 检测图像中的对象 | 选择图片 → 在 AI 面板中点击 "Detect Objects" |
| 处理此文件夹 | 点击文件列表上方的 ⚡ 按钮 |

**PHI 保护文件夹**: 如果您进入名为 `/dicom/`、`/phi/`、`/pii/` 等的文件夹，AI 处理按钮将显示 `🚫 PHI — AI Blocked`。这是安全护栏 — 无论您的权限如何，这些文件夹中的文件都不能发送到 AI 服务。

### Favorites

点击文件列表中的 ⭐ 图标固定常用文件。固定的文件显示在 Favorites 部分，便于快速访问。

### Recent

显示您最近查看、下载或 AI 查询的文件，带有相对时间戳（"3分钟前"、"2小时前"）。仅显示您自己的历史记录，其他用户的活动不可见。

### Upload

基于 Storage Browser for S3 的拖放文件上传。还支持：
- 创建文件夹
- 文件复制和删除
- 多文件上传（每个文件最大 5 GB）

---

## AI & 处理

### AI Processing

对文件夹或文件集触发 AI/ML 工作流。

1. 从下拉菜单选择处理模式（如 Legal Compliance、Financial IDP、Semiconductor EDA）
2. 设置输入前缀（如果从 All Files 点击 ⚡ 则已预填）
3. 点击 **Start Processing**
4. 页面将跳转到 Job History，状态每 5 秒更新一次

### Job History

查看所有过去的处理任务及其状态、时间戳和输出数据。

| 状态 | 含义 |
|------|------|
| 🔵 RUNNING | 处理中 |
| 🟢 SUCCEEDED | 已完成 — 点击查看结果 |
| 🔴 FAILED | 发生错误 — 查看输出了解详情 |
| ⚪ TIMED_OUT | 超过最大执行时间 |

点击任何任务可展开其输出。如果结果已写回卷，导航链接可直接跳转到 All Files 中的输出文件夹。

### Analytics

使用 Amazon Athena 对数据运行 SQL 查询。此功能需要管理员预先配置的 Glue Data Catalog 表。

---

## 数据保护

### Snapshots

查看卷快照 — 数据的时间点副本。

- **列表**: 查看所有可用快照及其创建时间戳
- **恢复**: 点击 "Restore" 从任何快照创建 FlexClone（即时创建的空间高效副本）。克隆拥有自己的 S3 Access Point，数秒内即可使用。

### Lock (WORM)

查看三种机制下数据的不可变性状态：

| 选项卡 | 显示内容 |
|--------|----------|
| ONTAP SnapLock | 卷是否使用 Compliance 或 Enterprise 模式及保留期限 |
| S3 Object Lock | AI 输出存储桶是否启用了对象级 WORM |
| Tamperproof Snapshot | 哪些快照已锁定及到期时间 |

> **注意**: 配置锁定设置需要 `storage-admin` 角色。普通用户对此部分仅有只读访问权限。

### ARP/AI（勒索软件防护）

查看卷的自主勒索软件防护状态。

| 显示内容 | 含义 |
|----------|------|
| 🟢 No threats | 所有卷健康 |
| 🔴 Threat detected | ARP/AI 标记了可疑活动 |
| Incident badge | 显示当前响应阶段（Detected → Contained → Investigating → Resolved） |

如果检测到威胁且您属于 `storage-admin` 组，可以直接从此面板执行隔离操作。

---

## 管理（需要 `storage-admin` 组）

以下部分仅在您的账户属于 `storage-admin` Cognito 组时可见/可操作。

### Storage Dashboard

管理员着陆页。显示四张卡片：
- 💾 卷数量 + 平均容量利用率
- 🛡️ ARP 保护的卷 + 活跃威胁
- 🔐 已锁定（防篡改）快照
- 📊 存储效率比率

点击任何卡片可深入查看详情面板。

### Resources

卡片网格管理面板，10 个管理区域按类别组织：

| 类别 | 面板 |
|------|------|
| 存储 | Volumes、Qtrees、Quotas、Efficiency |
| 访问控制 | Export Policies、CIFS Shares、QoS |
| 保护 | ARP Admin、Snapshot Admin、SnapLock |

### Version Diff

并排比较两个快照之间的文件内容。

### Audit Trail

查询 CloudTrail S3 数据事件，回答"谁在什么时候访问了什么"。

---

## 提示与常见问题

**Q: 某些面板显示 "ONTAP Connection Required"。**
A: 门户处于 DemoMode 或管理员尚未配置 VPC 连接。文件浏览和 AI 功能仍可正常使用 — 只有 ONTAP 专属面板（Snapshots、ARP、Lock）需要该连接。

**Q: AI 处理按钮显示 "PHI — AI Blocked"。**
A: 您位于受保护文件夹（`/dicom/`、`/phi/`、`/pii/` 等）中。这是设计行为 — 这些路径中的文件不能发送到 AI 服务。请导航到非保护文件夹以使用 AI 功能。

**Q: 分享链接过期太快。**
A: 分享链接使用您选择的有效时间（5 分钟、15 分钟或 1 小时）的 Presigned URL。如需更长期的分享，请咨询管理员关于 Nextcloud 集成或调整 TTL 选项。

**Q: 通过 NFS/SMB 上传的文件未显示。**
A: 文件应立即显示（ONTAP 保证跨协议强一致性）。请尝试刷新文件列表。如果仍未显示，文件可能在子文件夹中 — 请检查路径。

**Q: 可以在移动设备上使用门户吗？**
A: 可以。在窄屏幕上侧边栏会折叠。所有功能在移动浏览器上均可使用，但体验针对桌面进行了优化。

**Q: 如何更改密码？**
A: 使用 Cognito Hosted UI 或请管理员重置。

---

## 相关文档

| 文档 | 受众 | 用途 |
|------|------|------|
| [Getting Started (Deploy)](../../solutions/amplify-portal/docs/GETTING-STARTED.md) | 管理员 | 从零开始部署门户 |
| [Admin Demo Guide](admin-resource-management-demo.md) | 存储管理员 | 管理操作 E2E 演示 |
| [AI Features Quick Start](ai-features-quick-start.md) | 所有用户 | 试用 Bedrock、Rekognition、Athena |
| [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) | 开发者 | 架构与自定义 |
| [Authorization Model](portal-authorization-model.md) | 安全团队 | Cognito 组、IAM、文件级访问 |
| [Compliance Guide](portal-compliance-guide.md) | 安全/合规 | 验证监管控制 |
| [Quick Reference](portal-quick-reference.md) | 所有角色 | 单页速查表 |
