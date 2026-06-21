# Content Edge Delivery — FSx for ONTAP S3 AP × CDN/边缘（厂商中立）

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## 概述

将 FSx for NetApp ONTAP 作为**单一可信源（主数据）**保留，同时让 S3 Access Points（S3 AP）上的
**已批准分发的成品（rendition）**可通过 CDN/边缘网络分发的**厂商中立**无服务器模式。

各分发网络的技术可行性对比（CloudFront / Akamai / Fastly / Cloudflare / Bunny.net /
Google Media CDN 等）请参阅 **[CDN 对比](../docs/cdn-comparison.zh-CN.md)**。

> 本模式为参考实现。分发厂商选型、版权处理、地域限制与合规由客户负责。

> **TL;DR（30秒）**：不移动 ONTAP/NAS 主数据，**仅分发已批准成品**，经 CloudFront 或第三方 CDN。
> 从验证风险最低的 `PUBLISH_PUSH`（M3）开始。SigV4 直接回源（ORIGIN_PULL）需先用
> [验证清单](../docs/cdn-origin-verification-checklist.zh-CN.md)实测再采用。

## 业务成果与采用（Outcome / Adoption）

以**业务成果**评估，而非“部署成功”。

| 区分 | Outcome / Metric / 测量方法 |
|---|---|
| Business Outcome | 不双份保存主数据即实现边缘分发（分发用复制仅限已批准成品） |
| Metric | 流入分发层的主数据条数 = 0 / 批准证迹 `unrecorded` 条数 |
| 测量方法 | 汇总 publish 清单的 `provenance` 与 `skipped`/`published` |

- **安全实验边界**：`DemoMode=true` 可在无 FSx/外部 CDN 时验证逻辑。
- **Business Sponsor**：任命分发负责人（媒体/分发平台团队）并批准 Go/No-Go。
- **Go/No-Go 清单**：`ApprovedPrefix` 外不被纳入对象 / 记录批准证迹 / 观众令牌以 CDN 原生机制工作 /
  采用 ORIGIN_PULL 时 SigV4×alias 实测为 PASS。
- 将未来工作定位为**证据扩展**（TBV → 实测），而非未完成。

## Partner/SI 使用指南

- **首个客户问题**：“是否希望将既有 NAS/ONTAP 资产在不复制的情况下接入边缘分发？分发走 CloudFront，
  还是既有合约 CDN（如 Akamai）？”
- **PoC 产出**：DemoMode 演示 → 已批准成品的分发清单 →（可选）实机 SigV4 验证结果。可将
  [CDN 对比](../docs/cdn-comparison.zh-CN.md)直接用于客户对话。

## 两种集成机制

- **ORIGIN_PULL**：不复制对象，生成供 CDN 通过 SigV4 直接回源 S3 AP 的源引用清单。CloudFront 通过 OAC
  原生支持（参考实现）。第三方 CDN 的 SigV4 回源签名**需验证**。
- **PUBLISH_PUSH**：将已批准成品复制到 CDN 侧 S3 兼容对象存储。规避回源认证问题，且厂商中立——验证风险最低的首选。

## 主要组件

| 组件 | 职责 |
|---|---|
| `functions/publish/handler.py` | 将已批准成品反映到分发层，并将分发清单写回 S3 AP |
| `functions/delivery_log_sync/handler.py` | 将 CDN 分发日志规范化（IP 脱敏）并写回 S3 AP，以便与制作数据关联 |
| Step Functions | Publish → SNS 通知 |
| CloudFront（可选） | ORIGIN_PULL 的参考分发（OAC + SigV4） |

## 部署

```bash
sam build --template content-edge-delivery/template.yaml
sam deploy --guided \
  --template content-edge-delivery/template.yaml \
  --stack-name fsxn-content-edge-delivery
```

## 安全 / 治理

- **permission-aware**：分发对象仅限 `ApprovedPrefix` 下。不直接分发受 ACL 控制的主数据。
- **观众认证**：不支持 S3 Presigned URL → 使用 CDN 原生令牌机制。
- **PII**：写回分发日志时对客户端 IP 脱敏（`RedactClientIp=true`）。
- **最小权限**：分发 Lambda 因访问 Internet-origin S3 AP 而在 **VPC 外**运行。

> **Governance Note**：分发不强制执行 ONTAP 文件权限。分发边界由“仅分发已批准成品”的运维规则、批准证迹记录
> 以及分发目标的访问控制来保障。

### 责任分担（RACI / 公共部门视角）

| 角色 | 职责 |
|---|---|
| Data Owner | 分发对象数据的分类·驻留地·可否公开的最终责任 |
| Approver | 批准置于 `ApprovedPrefix`；赋予批准证迹（approved-by / approval-id） |
| Audit Reviewer | 定期审查 publish 清单的 `provenance` 与分发日志 |
| Ops Owner | 接收告警·处理事件·执行回滚 |

- AI/自动判定为**辅助信号**；可否公开由人（Data Owner / Approver）决定。
- 验证用数据使用**非机密合成/样本**（不将生产个人数据用于验证）。
- 技术验证**不替代**法务·合规·隐私评估。

## 运维 / Runbook

- **告警**：`EnableCloudWatchAlarms=true` 时，Lambda 错误（publish/log-sync）与 Step Functions 失败经 SNS 通知
  （`NotificationEmail`）。
- **排查**：publish 错误 → 查看 `/aws/lambda/<stack>-publish`；分离 S3 AP 授权（IAM + AP policy + ONTAP 身份）
  与外部存储认证（Secrets Manager）。外部 push 失败 → 检查 `ExternalStoreSecretName`·端点·桶。疑似边界破坏 →
  [事件响应 Playbook](../docs/incident-response-playbook.md)。
- **回滚**：分发仅 publish 已批准成品；误公开时从分发目标（CDN 存储/Distribution）移除该对象，从 `ApprovedPrefix`
  撤回后重新 publish。
- **外部存储认证**：PUBLISH_PUSH 推送到 Akamai/R2/Fastly 等时，AWS 默认凭证不通用，需设置
  `ExternalStoreSecretName`（Secrets Manager，`{"access_key_id","secret_access_key"}`）。

## 相关文档

- [CDN/边缘分发集成对比](../docs/cdn-comparison.zh-CN.md)
- [ORIGIN_PULL SigV4 验证清单](../docs/cdn-origin-verification-checklist.zh-CN.md)（实机验证步骤）
- [替代架构对比](../docs/comparison-alternatives.md)
- [事件响应 Playbook](../docs/incident-response-playbook.md)
