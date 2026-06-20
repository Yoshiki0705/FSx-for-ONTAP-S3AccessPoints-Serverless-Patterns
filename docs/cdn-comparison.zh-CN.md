# CDN / 边缘分发集成对比 — 从 FSx for ONTAP S3 Access Points 分发

🌐 **Language / 言語**: [日本語](cdn-comparison.md) | [English](cdn-comparison.en.md) | [한국어](cdn-comparison.ko.md) | [简体中文](cdn-comparison.zh-CN.md) | [繁體中文](cdn-comparison.zh-TW.md) | [Français](cdn-comparison.fr.md) | [Deutsch](cdn-comparison.de.md) | [Español](cdn-comparison.es.md)

## 0. 范围

整理从 FSx for ONTAP S3 Access Points（S3 AP）上的数据通过 CDN/边缘网络分发时的**技术可行性**的参考资料。
本文档**不**进行厂商优劣对比、价格/性能对比或营销主张。仅讨论针对 FSx for ONTAP S3 AP 的约束，**哪些可实现、
哪些不可实现、哪些需验证**。分发厂商选型由客户结合本文档范围之外的因素（合同·SLA·运维体系·区域要求等）判断。

## 1. 决定分发设计的 S3 AP 约束

| 约束 | 内容 | 对分发的影响 |
|------|------|------------|
| 强制 Block Public Access（不可禁用） | 默认开启·不可变更 | 无认证的公开源不可用；需源认证 |
| 源认证为 SigV4（IAM） | 由 IAM / AP 策略评估 | CDN 回源请求须用 AWS SigV4 签名 |
| 双层授权（AWS + ONTAP） | 先 IAM 再 ONTAP 文件身份（UNIX UID / Windows AD） | 分发对象限于 ONTAP 身份可读范围 |
| 不支持 Presigned URL | 官方不支持 | 观众令牌认证不能用 S3 Presigned URL；用 CDN 原生令牌 |
| NetworkOrigin（Internet/VPC，不可变更） | CDN 从托管/外部网络访问 | CDN 集成需 **Internet origin** |
| PutObject 最大 5 GB | 单次 PUT 限制 | 大文件写回需分段上传 |

## 2. 集成机制（厂商中立）

- **M1 — 原生 SigV4 回源**：CDN 用 SigV4 签名直接回源 S3 AP。当 CDN 内置 SigV4 源签名时可实现。
  **需验证**：S3 AP 的 `accesspoint alias` 主机与标准桶不同，SigV4 行为须在实机验证。
- **M2 — 边缘计算 SigV4 签名**：在 CDN 边缘运行时（Workers/Compute/EdgeWorkers）自实现 SigV4。
  无原生源签名时可实现，签名·密钥管理需自持。
- **M3 — 推送到 CDN 原生 S3 兼容存储**：FSx 保留为主，仅将已批准成品复制到 CDN 侧对象存储。规避源认证问题，
  且厂商中立。验证风险最低的首选。
- **M4 — 自管 SigV4 签名代理**：将签名中间层（Lambda Function URL / ALB）作为源。几乎所有 CDN 都可用，
  但代理成为可用性·扩展的关注点。

> 通用绝对约束：观众令牌认证不能用 S3 Presigned URL — 用 CDN 原生令牌。
> 公开分发绕过 NFS/SMB ACL，故仅分发已批准成品（见第 4 节）。

## 3. 各分发网络的机制支持（基于事实）

○ = 有官方功能 / △ = 有条件·自实现 / − = 无该功能 / TBV = 需 S3 AP 专属验证。

| 分发网 | M1 原生 SigV4 回源 | M2 边缘签名 | M3 自有 S3 兼容存储 | 观众令牌 | S3 AP 专属 TBV |
|--------|:---:|:---:|:---:|---|---|
| Amazon CloudFront | ○ OAC (SigV4) | △ Lambda@Edge / Functions | （到标准 S3） | CloudFront 签名 URL/Cookie | **有实绩**（AWS 官方教程展示 S3 AP + OAC） |
| Akamai | ○ Cloud Access Manager（AWS 签名） | △ EdgeWorkers | ○ NetStorage / Object Storage | Akamai Token Auth | AP alias 主机上的签名 TBV |
| Fastly | ○ 对 S3 兼容私有源用 SigV4 | △ Compute | ○ Fastly Object Storage | Fastly 签名 URL | AP alias 上的 SigV4 TBV |
| Cloudflare | −（代理本身不内置 SigV4） | ○ 用 Workers 做 SigV4 签名 | ○ R2（S3 兼容） | Cloudflare 签名 URL | Workers 签名 + AP alias TBV |
| Bunny.net | △ S3 回源（AWS S3 源类型） | − | ○ Bunny Storage（S3 兼容 API，beta） | Pull Zone 令牌认证 | AP alias 上的签名 TBV |
| Google Cloud CDN / Media CDN | ○ private S3 兼容源 SigV4 认证 | △ Media CDN 路由 | （GCS / 任意 S3 兼容） | Media CDN 签名 URL/Cookie | 跨云 egress + AP alias TBV |

### 不列入表格/作注释
- **Azure Front Door / Azure CDN**：同一机制（M1/M4）可能适用·TBV。非主要范围。
- **Gcore**：S3 兼容对象存储 + 存储作源（M3）。非主要范围。
- **Edgio（原 Limelight / Edgecast）**：**2025-01-15 停止 CDN 业务**，资产大部分由 Akamai 取得。
  **非在运选项** — 排除。

> 出处为各家公开文档（CloudFront OAC、Akamai Cloud Access Manager、Fastly S3 兼容私有源、Cloudflare
> Workers/R2、Bunny Storage、Google Media CDN）。均为针对**标准 S3 兼容桶**的描述；在 FSx for ONTAP S3 AP
> accesspoint alias 上的行为为 TBV。

## 4. 安全固定要求（机制通用）

1. 公开分发绕过 NFS/SMB ACL — **仅分发已批准成品**。不将受 ACL 控制的主数据直接送入分发层。
2. 分离主数据（受 ACL 控制·机密）与分发成品（公开/准公开）。M3 使该分离结构上自然。
3. 观众认证用 CDN 原生令牌机制（不用 S3 Presigned URL）。
4. 最小权限源凭证；不在边缘放置长期密钥，优先短期凭证。
5. 分发日志：将日志写回 FSx 时，将观众 PII 处理纳入设计。
6. **分发批准追踪**：记录哪个对象由谁在何时批准为公开分发。批准人未记录的对象不阻断，而以 `unrecorded` **可视化**。
7. **数据驻留 / 地域限制**：CDN 全球分发。不可出区的数据应从批准对象排除，或用 geo-blocking 控制；
   批准流程纳入驻留判定。

### 4.1 证据分类
- **公开证据**：第 3 节各分发网功能 — 基于公开文档、**时点相关**，采用前以最新信息再确认。
- **需验证（本项目）**：针对 FSx for ONTAP S3 AP accesspoint alias 的各 CDN SigV4 源签名实际行为。

## 5. 可行性小结

| 问题 | 回答 |
|------|------|
| 能否将 S3 AP 作为无认证的 CDN 源公开 | **否**（强制 BPA） |
| 能否从 S3 AP 经 CDN 直接分发 | **有条件可以** — 支持/实现 SigV4 时 M1/M2。AP alias 签名为 TBV |
| 没有 SigV4 的 CDN 能否分发 | **可以** — M3（推送）或 M4（签名代理） |
| 观众能否用 S3 Presigned URL | **否** — 用 CDN 原生令牌 |
| 分发时能否强制 ONTAP ACL | **否** — 以"仅分发已批准成品" + 追踪保障 |
| 验证风险最低的首选 | **M3（推送）** — 规避源认证，厂商中立，便于 DemoMode |

> **Governance Caveat**：本资料为技术参考信息。各家功能会更新，采用前请以最新官方文档再确认。针对 S3 AP
> accesspoint alias 的 SigV4 源签名是本项目的验证项（TBV）。分发厂商选型由客户判断。
