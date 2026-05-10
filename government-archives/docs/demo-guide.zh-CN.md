# UC16 演示脚本（30分钟版）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## 前提

- AWS 账户，ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- 部署 `government-archives/template-deploy.yaml`（使用 `OpenSearchMode=none` 降低成本）

## 时间线

### 0:00 - 0:05 简介（5 分钟）

- 用例：地方政府和行政机构的公共文档管理数字化
- FOIA / 信息公开请求的法定期限（20 个工作日）的负担
- 挑战：PII 检测和编辑需要手动操作数小时

### 0:05 - 0:10 架构（5 分钟）

- Textract + Comprehend + Bedrock 的组合
- OpenSearch 的 3 种模式（none / serverless / managed）
- NARA GRS 保留期限的自动管理

### 0:10 - 0:15 部署（5 分钟）

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 执行处理（7 分钟）

```bash
# 上传示例 PDF（包含机密信息）
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# 执行 Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

确认结果：
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt`（原始文本）
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json`（分类结果）
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json`（PII 检测）
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt`（编辑版本）
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json`（sidecar）

### 0:22 - 0:27 FOIA 期限跟踪（5 分钟）

```bash
# 注册 FOIA 请求
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# 手动执行 FOIA Deadline Lambda
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

确认 SNS 通知邮件。

### 0:27 - 0:30 总结（3 分钟）

- 启用 OpenSearch（使用 `serverless` 进行全面搜索）的路径
- 迁移到 GovCloud（FedRAMP High 要求）
- 下一步：使用 Bedrock 代理生成交互式 FOIA 响应

## 常见问题与解答

**Q. 能否支持日本的信息公开法（30 天）？**  
A. 修改 `REMINDER_DAYS_BEFORE` 和 20 个工作日的硬编码即可支持（将美国联邦假日改为日本假日）。

**Q. 原始 PII 存储在哪里？**  
A. 不存储在任何地方。`pii-entities/*.json` 仅包含 SHA-256 哈希，`redaction-metadata/*.json` 也仅包含哈希 + 偏移量。恢复需要从原始文档重新执行。

**Q. 如何降低 OpenSearch Serverless 的成本？**  
A. 最低 2 OCU = 每月约 $350。建议在非生产环境中停止。
A. 使用 `OpenSearchMode=none` 跳过，或使用 `OpenSearchMode=managed` + `t3.small.search × 1` 将成本控制在约 $25/月。

---

## 关于输出目标：可通过 OutputDestination 选择（模式 B）

UC16 government-archives 在 2026-05-11 的更新中支持了 `OutputDestination` 参数
（参见 `docs/output-destination-patterns.md`）。

**目标工作负载**：OCR 文本 / 文档分类 / PII 检测 / 编辑 / OpenSearch 前置文档

**2 种模式**：

### STANDARD_S3（默认，与以前相同）
创建新的 S3 存储桶（`${AWS::StackName}-output-${AWS::AccountId}`），
并将 AI 成果物写入其中。Discovery Lambda 的清单仅写入 S3 Access Point
（与以前相同）。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必需参数)
```

### FSXN_S3AP（"无数据移动"模式）
通过 FSxN S3 Access Point 将 OCR 文本、分类结果、PII 检测结果、编辑后的文档、编辑元数据
写回到与原始文档**相同的 FSx ONTAP 卷**。
公共文档管理人员可以在 SMB/NFS 的现有目录结构中直接引用 AI 成果物。
不会创建标准 S3 存储桶。

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必需参数)
```

**链式结构的读回**：

UC16 采用链式结构，后续 Lambda 读回前一阶段的成果物（OCR → Classification →
EntityExtraction → Redaction → IndexGeneration），因此 `shared/output_writer.py` 的
`get_bytes/get_text/get_json` 从与写入目标相同的 destination 读回。
这样，即使在 `OutputDestination=FSXN_S3AP` 时，也能从 FSxN S3 Access Point
读回，整个链条在一致的 destination 下运行。

**注意事项**：

- 强烈建议指定 `S3AccessPointName`（同时授予 Alias 格式和 ARN 格式的 IAM 权限）
- 超过 5GB 的对象在 FSxN S3AP 中不可用（AWS 规范），必须使用分段上传
- ComplianceCheck Lambda 仅使用 DynamoDB，因此不受 `OutputDestination` 影响
- FoiaDeadlineReminder Lambda 仅使用 DynamoDB + SNS，因此不受影响
- OpenSearch 索引由 `OpenSearchMode` 参数单独管理（与 `OutputDestination` 独立）
- AWS 规范上的限制请参见
  [项目 README 的"AWS 规范上的限制与解决方法"部分](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)
