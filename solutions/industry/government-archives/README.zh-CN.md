# UC16：政府机构 — 公文数字档案·FOIA 应对

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文档**: [架构](docs/architecture.md) | [演示脚本](docs/demo-guide.md) | [故障排查](../docs/phase7-troubleshooting.md)

## 概述

基于 FSx for ONTAP S3 Access Points 的政府机构公文
数字档案以及信息公开请求（FOIA：Freedom of Information Act）
应对自动化流水线。

## 使用场景

将政府机构持有的大量公文（PDF、扫描图像、电子邮件）
自动数字化、分类、涂黑（编修），从而快速应对信息公开请求。

### 处理流程

```
FSx for ONTAP (公文存储 — 按部门 NTFS ACL)
  → S3 Access Point
    → Step Functions 工作流
      → Discovery：检测新文档（PDF, TIFF, EML, MSG）
      → OCR：使用 Textract 进行文档数字化（ap-northeast-1 不支持，故跨区域）
      → Classification：使用 Comprehend 进行文档分类（机密级别判定）
      → EntityExtraction：PII 检测（姓名、地址、SSN、电话号码）
      → Redaction：机密信息自动涂黑（编修）
      → IndexGeneration：全文检索索引生成（OpenSearch，可禁用）
      → ComplianceCheck：保存期限·销毁计划确认（NARA GRS）
```

### 目标数据

| 数据格式 | 说明 | 典型大小 |
|-----------|------|-----------|
| PDF | 公文、报告书、合同 | 100 KB – 50 MB |
| TIFF | 扫描文档 | 1 – 100 MB |
| EML / MSG | 电子邮件档案 | 10 KB – 10 MB |
| DOCX / XLSX | Office 文档 | 50 KB – 20 MB |

### AWS 服务

| 服务 | 用途 |
|---------|------|
| FSx for ONTAP | 公文持久化存储（按部门 NTFS ACL） |
| S3 Access Points | 从无服务器访问文档 |
| Step Functions | 工作流编排 |
| Lambda | 文档分类、PII 检测、涂黑处理 |
| Amazon Textract ⚠️ | 文档 OCR（经由 us-east-1 跨区域） |
| Amazon Comprehend | 实体提取、文档分类、PII 检测 |
| Amazon Bedrock | 文档摘要、FOIA 答复草稿生成 |
| Amazon Macie | 机密数据自动检测 |
| DynamoDB | 文档元数据、处理状态管理 |
| OpenSearch Serverless | 全文检索索引（可选，默认禁用） |
| SNS | FOIA 期限告警 |

### Public Sector 适配性

- **NARA（国家档案与记录管理局）合规**：满足电子记录管理要求
- **FOIA 应对**：自动追踪 20 个工作日内的答复期限
- **FedRAMP High**：在 AWS GovCloud 上合规
- **Section 508**：无障碍支持（OCR + 替代文本生成）
- **Records Management**：保存期限·销毁计划的自动管理

### FOIA 应对流程

```
FOIA 请求受理
  → 目标文档检索（OpenSearch）
  → 相关文档的机密级别判定
  → 自动涂黑（PII、国家安全信息）
  → 通知审阅负责人
  → 答复期限追踪（20 个工作日）
  → 公开文档包生成
```

## 已验证的画面（截图）

### 1. 公文存储（经由 S3 Access Point）

信息公开请求受理后，目标文档会存储在 `archives/YYYY/MM/` 前缀下。

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     内容：S3 AP 的 archives/ 前缀下的 PDF 文档列表
     掩码：账户 ID、S3 AP ARN、文档名 -->
![UC16：公文存储确认](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. 涂黑文档的浏览

处理完成后存储于 `redacted/` 前缀的文本中，PII 已被替换为
`[REDACTED]` 标记。**一般职员在公开前进行审阅的画面。**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     内容：S3 控制台中的 redacted 文本预览，[REDACTED] 标记可见
     掩码：账户 ID、涂黑目标文档名（仅显示示例名） -->
![UC16：涂黑文档预览](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. 涂黑元数据（sidecar JSON）

用于审计的 sidecar 数据。不保存原文 PII，仅保存 SHA-256 哈希。
记录偏移量、实体类型（NAME / EMAIL / SSN 等）与置信度。

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     内容：redaction-metadata/*.json 的格式化视图
     掩码：账户 ID、原文档名 -->
![UC16：涂黑元数据 JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA 期限提醒（SNS 邮件通知）

FOIA 负责人在期限前 3 个工作日收到的提醒邮件。
超过期限时会发送 severity=HIGH 的 OVERDUE 通知。

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     内容：在邮件客户端中显示 FOIA_DEADLINE_APPROACHING 邮件
     掩码：收件人·发件人邮箱、request_id（仅显示示例 ID） -->
![UC16：FOIA 期限提醒邮件](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA GRS 保存计划（DynamoDB Explorer）

`fsxn-uc16-demo-retention` 表。每个文档都记录 NARA GRS 代码
（GRS 2.1 / 2.2 / 1.1）与保存年数（3 / 7 / 30 年）、预定销毁日期。

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     内容：在 DynamoDB Explorer 中的 retention 表项目列表
     掩码：账户 ID、document_key（仅示例名） -->
![UC16：保存计划表](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
通过公文档案·FOIA 应对（OCR·分类·涂黑·保存期限管理）的自动化，加快信息公开请求的应对。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| 已处理文档数 / 执行 | > 500 documents |
| OCR 文本提取成功率 | > 95% |
| PII 检测精度 | > 95% |
| 涂黑处理时间 / 文档 | < 30 秒 |
| FOIA 应对时间缩短 | > 50% |
| Human Review 必需率 | 100%（涂黑结果需全件人工确认） |

> **100% Human Review 的理由**：由于涂黑遗漏会直接影响信息公开与个人信息保护，因此必须对全件进行人工确认。

### Measurement Method
Step Functions 执行历史、Comprehend PII 检测结果、涂黑前后 diff、DynamoDB 保存期限历史、CloudWatch Metrics。审阅结果记录到 DynamoDB，以便在审计时可追踪"谁·何时·确认·批准了什么"。

### Sample Run Results (实测示例)

**环境**：FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| 指标 | Before (手动) | After (S3AP 自动化) |
|------|-------------|-------------------|
| FOIA 应对时间 | 数天~数周 | 389 ms (10 docs, sequential) |
| 文档检出 | 手动检索 | 32 ms (10 documents) |
| 文件读取 | 单独访问 | avg 36 ms / document |
| 涂黑质量 | 依赖负责人，存在不一致 | Comprehend PII 检测 + 自动涂黑 |
| Human Review | 无 or 不定期 | 100%（全件需人工确认） |
| 审计证迹 | 个人记录 | DynamoDB (who/when/what) + S3 Object Lock |
| 保存期限管理 | 手动 | 自动追踪 + 告警 |

> **备注**：UC16 的 sample run 是使用合成或非敏感样本文档进行的验证，不代表实际的行政文档或生产数据。本 sample run 仅验证处理路径。涂黑质量、Human Review 的完整性、审计证迹评估请在客户特定的 PoC 中另行实施。

## 部署

### 事前验证

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一键部署

```bash
bash scripts/deploy_phase7.sh government-archives
```

### 手动部署

```bash
# 前提：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### OpenSearch 模式

| 模式 | 用途 | 每月成本（估算） |
|--------|------|-------------------|
| `none` | 验证·低成本运行（默认） | $0 |
| `serverless` | 可变工作负载，按量计费 | $350 – $700 |
| `managed` | 固定工作负载，价格低 | $35 – $100 |

## 目录结构

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # 跨区域 Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA GRS 保存期限
│   └── foia_deadline_reminder/handler.py  # 20 个工作日追踪
├── tests/                            # 52 pytest (含 Hypothesis)
└── README.md
```


---

## AWS 文档链接

| 服务 | 文档 |
|---------|------------|
| FSx for ONTAP | [用户指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [开发者指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [开发者指南](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [开发者指南](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [用户指南](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [开发者指南](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Well-Architected Framework 对应

| 支柱 | 对应 |
|----|------|
| 卓越运营 | X-Ray、EMF、FOIA 截止期限追踪、52+ 测试 |
| 安全性 | PII 编修、SHA-256 审计 sidecar、Macie、100% Human Review |
| 可靠性 | Step Functions Retry/Catch、跨区域 OCR、resilience 测试 |
| 性能效率 | 并行 PII 检测、OpenSearch 索引、批处理 |
| 成本优化 | 无服务器、OpenSearch Serverless、条件性索引 |
| 可持续性 | NARA GRS 合规、保存期限管理、自动销毁计划 |





---

## 成本估算（每月概算）

> **备注**：以下为 ap-northeast-1 区域的概算，实际成本因使用量而异。最新价格请在 [AWS Pricing Calculator](https://calculator.aws/) 确认。

### 无服务器组件（按量计费）

| 服务 | 单价 | 预估使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 函数 × 100 docs/天 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/天 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/天 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/执行 | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/查询 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/天 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### 固定成本（FSx for ONTAP — 以现有环境为前提）

| 组件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共享现有环境) |
| S3 Access Point | 无额外费用（仅 S3 API 费用） |

### 合计概算

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每天执行 1 次） | ~$5-15 |
| 标准配置（每小时执行） | ~$15-50 |
| 大规模配置（高频 + 告警） | ~$50-150 |

> **Governance Caveat**：成本估算为概算，非保证值。实际账单因使用模式、数据量、区域而异。

---

## 本地测试

### Prerequisites 检查

```bash
# 确认前提条件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 凭证
```

### sam local invoke

```bash
# 构建
# 前提：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

# Discovery Lambda 的本地执行
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 带环境变量覆盖
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 单元测试

```bash
python3 -m pytest tests/ -v
```

详情请参阅 [本地测试快速入门](../docs/local-testing-quick-start.md)。

---

## 输出示例 (Output Sample)

公文档案·FOIA 处理的输出示例：

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **备注**：以上为示例输出，实际值因环境·输入数据而异。基准数值为 sizing reference，而非 service limit。

---

## Governance Note

> 本模式提供技术架构指导。并非法律·合规·监管方面的建议。组织应咨询具备资质的专业人士。

---

## S3AP Compatibility

关于 S3 Access Points for FSx for ONTAP 的兼容性约束、故障排查、触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
