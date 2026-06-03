# Partner/SI 一页摘要: FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 语言**: [日本語](partner-si-one-pager.md) | [English](partner-si-one-pager.en.md) | [한국어](partner-si-one-pager.ko.md) | [简体中文](partner-si-one-pager.zh-CN.md)

---

## What — 本仓库提供什么

| 项目 | 内容 |
|------|------|
| 行业用例 | 28 UC（法务、医疗、制造、公共部门等） |
| FlexCache/FlexClone 模式 | 6 FC（DR、渲染、RAG、CAE、生命科学、游戏） |
| 模板格式 | CloudFormation (SAM Transform) — 独立部署 |
| 触发模式 | POLLING（默认）/ EVENT_DRIVEN (FPolicy) / HYBRID |
| 成熟度模型 | 4 阶段（Sandbox → Scheduled → Monitored → Production） |
| 测试 | 1,499+ unit/property tests, cfn-lint, ruff validation |

## When — 何时使用

以下条件适用的客户可以提案：

- ✅ 在 FSx for ONTAP 上拥有文件数据
- ✅ 需要对文件数据进行无服务器自动处理
- ✅ 需要通过 S3 API 读写（GetObject, PutObject, ListObjectsV2 等）
- ✅ 需要 NTFS ACL / AD SID 访问控制（权限感知处理）
- ✅ 希望利用 AI/ML（Bedrock, Textract, Comprehend, Rekognition）
- ✅ 希望通过事件驱动或定时执行自动化文件处理

## How — PoC 推进方法

```
Step 1: 确定最接近的 UC → 确认 Success Metrics
Step 2: 部署模板 → 验证 S3AP 访问
Step 3: 测量客户特定 Baseline
Step 4: 按 Go/No-Go 标准评估
```

**预计时间**：
- Level 1 (Sandbox): 1-2 小时
- Level 2 (Scheduled): 1-2 天
- Level 3 (Monitored): 1-2 周

## Where — 主要资源位置

| 资源 | 路径 |
|------|------|
| Success Metrics | 各 UC 的 README.md |
| 治理 | [docs/governance-checklist.md](governance-checklist.md) |
| 生产就绪 | [docs/production-readiness.md](production-readiness.md) |
| 基准测试 | [docs/s3ap-benchmark-results.md](s3ap-benchmark-results.md) |
| 客户访谈 | [docs/customer-discovery-template.md](customer-discovery-template.md) |
| 成本估算 | [docs/cost-calculator.md](cost-calculator.md) |
| PoC 判定 | [docs/poc-go-nogo-template.md](poc-go-nogo-template.md) |

---

> **注意**: 本仓库是"学习设计决策的参考实现"。生产环境应用需要客户特定的安全审查、合规评估和性能验证。
