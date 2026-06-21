# ORIGIN_PULL SigV4 × S3 AP alias — 实机验证清单

🌐 **Language / 言語**: [日本語](cdn-origin-verification-checklist.md) | [English](cdn-origin-verification-checklist.en.md) | [한국어](cdn-origin-verification-checklist.ko.md) | [简体中文](cdn-origin-verification-checklist.zh-CN.md) | [繁體中文](cdn-origin-verification-checklist.zh-TW.md) | [Français](cdn-origin-verification-checklist.fr.md) | [Deutsch](cdn-origin-verification-checklist.de.md) | [Español](cdn-origin-verification-checklist.es.md)

## 目的

为在实机上确定 [CDN 对比文档](cdn-comparison.zh-CN.md) 中标记为 **需验证（TBV）** 的项，即
**“各 CDN 的 SigV4 源签名对 FSx for ONTAP S3 Access Point 的 `accesspoint alias` 主机是否与标准 S3 桶一样工作”**
而提供的可复现步骤。

本清单用于 `solutions/edge/content-delivery` UC 的 `DeliveryMode=ORIGIN_PULL`（M1/M2）采用判断。
**M3（PUBLISH_PUSH）不依赖本验证**（因其规避源认证）。

> **区分说明**：本验证为“特定测试环境下的实测”。请勿将一般 S3 行为或各 CDN 在标准桶上的实绩作为对 S3 AP
> alias 的保证。

---

## 0. 前提条件

- FSx for ONTAP 文件系统与 **Internet-origin** S3 Access Point（VPC-origin 不可用于 CDN）
- S3 AP alias（如 `<alias>-ext-s3alias`）与目标区域
- **已批准前缀**下的测试对象（如 `delivery-approved/test-1mb.bin`）
  - 遵循 permission-aware 原则，不将受 ACL 控制的主数据用于验证
- 用于源签名的**最小权限 IAM 凭证**（仅对目标 AP 的 `s3:GetObject`）。尽量使用短期凭证
- 验证终端（curl 7.75 以上支持 `--aws-sigv4`）、AWS CLI v2

> **安全**：验证期间也不要将访问密钥留在日志·截图·提交中。以密钥名而非值引用（公开仓库策略）。

---

## 1. 基线验证（无 CDN / 最重要）

不经 CDN，直接确认 **S3 AP alias 主机是否接受 SigV4**。这是所有 CDN 共通的核心。

### 1.1 AWS CLI（SDK 签名）

```bash
aws s3api get-object \
  --bucket "<alias>-ext-s3alias" \
  --key "delivery-approved/test-1mb.bin" \
  /tmp/out.bin --region <region>
```

- 期望：HTTP 200 + 对象获取成功。
- 失败时：分离 IAM / AP 策略 / ONTAP 侧身份（UNIX UID / AD）的双层授权进行排查。

### 1.2 原始 SigV4（近似 CDN 的源签名行为）

CDN 通常以固定访问密钥进行 SigV4 签名回源。用 `curl --aws-sigv4` 近似等效行为：

```bash
curl -sS -o /tmp/out.bin -w "%{http_code}\n" \
  --aws-sigv4 "aws:amz:<region>:s3" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
  "https://<alias>-ext-s3alias.s3.<region>.amazonaws.com/delivery-approved/test-1mb.bin"
```

- **若返回 200**：alias 主机与标准桶一样接受 SigV4 → M1/M4 实现可能性高。
- **若失败**：可能是 alias 专属寻址差异所致 → 在各 CDN 的源配置中逐一验证主机格式·区域·服务名（`s3`）·
  路径风格/虚拟主机的处理。
- 使用临时凭证时追加 `-H "x-amz-security-token: $AWS_SESSION_TOKEN"`。

### 1.3 负向确认（重申规范）

- 无签名 GET 应为 **403/AccessDenied**（确认 Block Public Access 强制）。
- Presigned URL 不可用（无法生成/不支持）→ 观众令牌走 CDN 原生机制。

---

## 2. 各 CDN 验证步骤

在每个 CDN 设置“源=S3 AP alias 主机”，确认缓存未命中时的回源是否为 200。

### 2.1 Amazon CloudFront（M1 / OAC）— 参考
- 以 `EnableCloudFront=true` 部署 `solutions/edge/content-delivery` 模板（OAC + `SigningProtocol: sigv4`）。
- 验证：`curl -I https://<distribution-domain>/delivery-approved/test-1mb.bin` → 200。
- 期望：依 AWS 官方教程成立（**有实绩**）。

### 2.2 Fastly（M1 / SigV4 原生）
- 将 alias 主机配置为 S3 兼容私有源并启用 SigV4 签名（区域·服务 `s3`）。
- 验证：经 Fastly 服务 GET → 200。确认 alias 虚拟主机格式在 Fastly SigV4 实现中被正确签名。

### 2.3 Cloudflare（M2 / Workers 签名）
- 在 Worker 中实现 SigV4 并对 alias 主机做签名回源（直接以 S3 AP 为源而非 R2 时）。
- 验证：经 Worker GET → 200。确认签名头·载荷哈希的处理。

### 2.4 Akamai（M1 / Cloud Access Manager）
- 在 Cloud Access Manager 配置 AWS 签名方式，并用 Origin Characteristics 指定 alias 主机。
- 验证：经 Akamai 属性 GET → 200。确认在 AP alias 主机上是否可应用签名。

### 2.5 Bunny.net（M1 / S3 源回源）
- 将 Pull Zone 源以 AWS S3 源类型设置为 alias 主机。验证：经 Pull Zone GET → 200。

### 2.6 Google Cloud CDN / Media CDN（M1 / private S3 origin）
- 以 private S3 兼容源 SigV4 认证配置 alias 主机。验证：经 Media CDN GET → 200。并确认跨云 egress 路径。

---

## 3. 合格/不合格标准

| 判定 | 条件 |
|------|------|
| **PASS** | 基线 1.2 为 200 且该 CDN 经由的缓存未命中 GET 为 200；观众令牌以 CDN 原生机制工作 |
| **CONDITIONAL** | CDN 经由为 200，但需额外配置（路径风格等）或约束（特定头） |
| **FAIL** | 对 alias 主机的 SigV4 在该 CDN 不成立，需回避方案（M2 签名实现/M4 签名代理/转 M3） |
| **BLOCKED** | 前提（Internet-origin、IAM、测试对象）未就绪，无法验证 |

---

## 4. 验证时的安全/治理确认

- [ ] 测试对象仅限 `delivery-approved/` 下（不使用受 ACL 控制的主数据）
- [ ] 源签名 IAM 仅对目标 AP 的 `s3:GetObject` 最小权限
- [ ] 不在边缘/配置留存长期密钥（优先短期凭证，验证后失效）
- [ ] 不将访问密钥·alias 实值·账户 ID 留在日志/截图/提交
- [ ] 观众令牌使用 CDN 原生机制（不用 S3 Presigned URL）
- [ ] 清理验证中创建的临时资源（Distribution、Pull Zone 等）

---

## 5. 结果记录表（证据）

| CDN | 机制 | 配置完成 | 1.2 基线 | 经 CDN GET | 观众令牌 | 判定 | 证据（HTTP 状态/头/时间） | 验证日 | 负责角色 |
|-----|------|:---:|:---:|:---:|:---:|:---:|---|---|---|
| CloudFront | M1/OAC |  |  |  |  |  |  |  | Storage |
| Fastly | M1 |  |  |  |  |  |  |  | Storage |
| Cloudflare | M2 |  |  |  |  |  |  |  | Storage |
| Akamai | M1 |  |  |  |  |  |  |  | Storage/Partner |
| Bunny.net | M1 |  |  |  |  |  |  |  | Storage |
| Google Media CDN | M1 |  |  |  |  |  |  |  | Storage |

> 记录注意：alias 实值·账户 ID·IP 用占位符（`<alias>-ext-s3alias`、`123456789012`）。
> 验证结果作为“特定测试环境下的实测”，不作为一般保证记载。

---

## 6. 验证结果反馈

- 已确定的结果反映到 [CDN 对比文档](cdn-comparison.zh-CN.md) 第 3 节“S3 AP 专属 TBV”列 / 4.1“需验证”的更新（TBV → 实测结果）。
- FAIL 的 CDN 在 `solutions/edge/content-delivery` 中以 `DeliveryMode=PUBLISH_PUSH`（M3）为推荐路径。

## 相关文档

- [CDN/边缘分发集成对比](cdn-comparison.zh-CN.md)
- [content-edge-delivery UC](../solutions/edge/content-delivery/README.zh-CN.md)
- [S3AP 兼容性说明](s3ap-compatibility-notes.md)
