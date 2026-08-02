# 文件门户 — 快速参考卡

> 🌐 Language: [English](../en/portal-quick-reference.md) | [日本語](../ja/portal-quick-reference.md) | [한국어](../ko/portal-quick-reference.md) | **简体中文** | [繁體中文](../zh-TW/portal-quick-reference.md) | [Français](../fr/portal-quick-reference.md) | [Deutsch](../de/portal-quick-reference.md) | [Español](../es/portal-quick-reference.md)

门户日常操作的单页速查手册。可打印或添加书签。

---

## 导航

| 侧边栏区域 | 功能 |
|:---:|------|
| 📂 All Files | 浏览、预览、下载、共享、AI 问答 |
| ⭐ Favorites | 已固定的文件 |
| 🕐 Recent | 您的访问历史 |
| 📤 Upload | 拖放上传（最大 50 GB/文件） |
| ⚡ AI Processing | 对文件夹触发 AI/ML 工作流 |
| 📋 Job History | 历史作业结果 + 状态 |
| 📊 Analytics | Athena SQL 查询 |
| 📸 Snapshots | 时间点副本 + FlexClone 恢复 |
| 🔒 Lock | SnapLock / S3 Object Lock / Tamperproof |
| 🛡️ ARP/AI | 勒索软件保护状态 |
| 🔧 Resources | 存储管理面板（仅管理员） |
| 🔄 Version Diff | 跨快照比较文件 |
| 🔍 Audit Trail | 谁在何时访问了什么 |

---

## 常见任务（所有用户）

| 我想... | 操作方法 |
|---------|----------|
| 浏览文件 | 侧边栏 → 📂 All Files → 点击文件夹 |
| 预览 PDF | 点击文件旁的 📕 |
| 预览 Word 文档 | 点击文件旁的 📝 |
| 下载文件 | 点击文件旁的 📄 |
| 共享文件链接 | 点击 🔗 → 选择 TTL → 复制 URL |
| 向 AI 询问文件内容 | 选择文件 → 在右侧面板输入问题 |
| 检测图像中的对象 | 选择图像 → 右侧面板中的 "Detect Objects" |
| 上传文件 | 侧边栏 → 📤 Upload → 拖放 |
| 对文件夹运行 AI | 在 All Files 中，点击文件列表上方的 ⚡ |
| 查看作业结果 | 侧边栏 → 📋 Job History → 点击作业 |
| 从快照恢复 | 侧边栏 → 📸 Snapshots → "Restore" 按钮 |
| 切换语言 | 点击顶部栏的 🌐 |

---

## 常见任务（合规 / 安全）

| 我想... | 操作方法 |
|---------|----------|
| 检查勒索软件状态 | 侧边栏 → 🛡️ ARP/AI |
| 验证 WORM 锁定 | 侧边栏 → 🔒 Lock → SnapLock 选项卡 |
| 检查输出存储桶锁定 | 侧边栏 → 🔒 Lock → S3 Object Lock 选项卡 |
| 查看已锁定快照 | 侧边栏 → 🔒 Lock → Tamperproof 选项卡 |
| 审查访问审计 | 侧边栏 → 🔍 Audit Trail |
| 验证 PHI 防护栏 | All Files → 导航至 `/dicom/` → 按钮显示 🚫 |

---

## 常见任务（存储管理员）

| 我想... | 操作方法 |
|---------|----------|
| 查看健康仪表板 | 侧边栏 → 🔧 Resources（仪表板首先显示） |
| 管理卷 | Resources → Storage → Volumes |
| 配置导出策略 | Resources → Access Control → Export Policies |
| 在卷上启用 ARP | Resources → Protection → ARP Admin |
| 锁定快照 | Resources → Protection → Snapshot Admin → Lock 表单 |
| 阻止受感染用户 | 侧边栏 → 🛡️ ARP/AI → Contain 选项卡 → Block SMB User |
| 解决后解除阻止 | 侧边栏 → 🛡️ ARP/AI → Unblock 选项卡 |
| 查看 EMS 告警 | Resources →（监控中显示 EMS 事件） |

---

## 键盘快捷键

| 按键 | 操作 |
|------|------|
| `Tab` | 在交互元素间移动 |
| `Enter` | 激活按钮 / 打开文件夹 |
| `Escape` | 关闭模态框 / 关闭面板 |

---

## 状态指示器

| 图标 | 含义 |
|:---:|------|
| 🟢 | 健康 / 无威胁 / 已解决 |
| 🔴 | 检测到威胁 / 错误 |
| 🟠 | 已遏制（事件进行中） |
| 🟡 | 调查中 |
| 🚫 | PHI — AI 已阻止（防护栏激活） |
| ⚠️ | 警告（容量 > 85% 等） |

---

## 访问级别

| 组 | 可执行操作 | 不可执行操作 |
|----|-----------|-------------|
| `authenticated` | 浏览、下载、上传、AI、查看保护状态 | 修改存储配置 |
| `storage-admin` | 以上所有 + 创建/删除卷、锁定快照、阻止用户、管理策略 | — |

---

## 快速故障排除

| 症状 | 解决方法 |
|------|----------|
| "ONTAP Connection Required" | DemoMode 下正常。请联系管理员配置 VPC。 |
| AI 按钮显示 🚫 | 您在 PHI 保护文件夹中。请导航到其他位置。 |
| 共享链接已过期 | 生成新链接（🔗）。最大 TTL = 1 小时。 |
| NFS 写入后文件未显示 | 刷新文件列表。应立即显示。 |
| 一直加载 | 检查网络。尝试退出登录 → 重新登录。 |

---

## 文档导航

| 您的角色 | 从这里开始 |
|---------|-----------|
| 最终用户（日常任务） | [用户指南](portal-user-guide.md) |
| 安全 / 合规人员 | [合规指南](portal-compliance-guide.md) |
| 存储管理员 | [管理员演示指南](admin-resource-management-demo.md) |
| IT 管理员（部署） | [入门指南](../../solutions/amplify-portal/docs/GETTING-STARTED.md) |
| 开发者（定制） | [实施指南](../../solutions/amplify-portal/docs/IMPLEMENTATION.md) |
