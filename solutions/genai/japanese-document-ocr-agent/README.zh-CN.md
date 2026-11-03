# 日语文档 OCR × AI 代理 — 在 S3 Access Points 上运行 Textract（东京）

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

这是一个示例：用东京区域的 Amazon Textract 读取 FSx for ONTAP S3 Access Points 上的扫描文档（图像、PDF、TIFF），
并通过 Amazon Bedrock AgentCore Gateway 的 Step Functions 连接器，把这次运行作为 AI 代理工具公开。
Textract 对日语的支持及其在东京区域的上线已于 2026-11-02 发布。

代理只决定读取哪个集合、使用哪个配置、最多处理多少份文档。步骤顺序、重试和失败处理由状态机负责。
OCR 文本不会交给代理，而是写入结果存储桶。

## 使用场景

- 对发票、合同、备忘录等扫描文档，在文件服务器上原地进行日语 OCR
- 让代理列出需要人工确认的文档及各自的原因
- 对无法使用 Textract Forms 的日语发票，连同依据一起提取合计金额等字段（可选）

## 架构

```
AI 代理 ──MCP──▶ AgentCore Gateway（NONE | AWS_IAM）
                       │ GatewayServiceRole：states:StartExecution 等
                       ▼
           Standard StateMachine（Discover → Map → Report）
                       │
   图像：把 bytes 传给 Textract 同步 API    PDF / TIFF：临时副本 → Textract 异步 API
                       │
   S3 Access Points（DemoMode 为普通 S3）──▶ 结果存储桶（result.json / text.txt / manifest.json）
```

详情见 [docs/architecture.md](docs/architecture.md)（日语）。

## 暴露的工具

| 工具 | 输入 | 用途 |
|---|---|---|
| `ocr___StartExecution` | `input`（JSON 字符串） | 启动 OCR，返回 `executionArn` |
| `ocr___DescribeExecution` | `executionArn`、`includedData: "ALL_DATA"` | 确认状态和结果 |
| `ocr___ListExecutions` | `statusFilter`（可选） | 最近的执行列表 |
| `ocr___GetExecutionHistory` | `executionArn` | 查找停止位置（输出较大） |
| `ocr___DescribeStateMachine` | `includedData`（可选） | 查看定义 |

固定的状态机 ARN 不会出现在工具中，代理无法更改。不带 `includedData: "ALL_DATA"` 调用 `DescribeExecution`，
既不会返回 `output`，也不会返回 FAILED 执行的 `error` 和 `cause`。

## 代理传入的输入

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| 键 | 必需 | 规则 |
|---|---|---|
| `collection` | 是 | ASCII ID（`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`），必须在允许列表（`CollectionsJson`）中 |
| `profile` | 否 | `text`（仅文字）或 `structure`（文字、表格、版面）。省略时使用集合的设置 |
| `max_files` | 否 | 1 到 `MaxFilesPerExecution` 的整数。按键的顺序从前面开始选取 |
| `modified_after` | 否 | `YYYY-MM-DD`。仅处理该日期及之后修改的文档 |

不接受 S3 路径和键。未知的键或违反规则的输入会使执行以 FAILED 结束，`Cause` 中会写明修正方法。

## 处理路径与配置

| 文档 | 路径 | 备注 |
|---|---|---|
| PNG / JPEG，5 MiB 以下 | 同步，直接传 bytes | 不产生副本 |
| PNG / JPEG，超过 5 MiB 且不超过 10 MiB | 异步，临时副本 | |
| PDF / TIFF | 异步，临时副本 | 不推测页数 |

`text` 调用 `DetectDocumentText`，`structure` 调用 `AnalyzeDocument`（`TABLES` 和 `LAYOUT`）。不提供 Forms、
Queries、AnalyzeExpense 和 AnalyzeID（不支持日语，或在东京不被允许）。

## 代理收到的内容

`DescribeExecution`（`ALL_DATA`）的 `output` 包含状态、件数、平均置信度、需复核的列表及各自原因，以及每份文档结果的
S3 URI。不包含 OCR 文本，但包含原始键（文件名）。启用字段提取时，还包含字段值（最多 60 个字符）。完整的文档列表在
结果存储桶的 `manifest.json` 中。

## 参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `S3AccessPointAlias` | S3 Access Points alias（DemoMode 下为普通存储桶名称） | （必需） |
| `DemoMode` | `true` 时无需 FSx for ONTAP 即可运行 | `false` |
| `CollectionsJson` | 集合允许列表（JSON）。为空时根据 `FilePrefix` 生成一个 | `""` |
| `MaxFilesPerExecution` | 每次执行的最大文档数（1–100） | `50` |
| `MapConcurrency` | 并行处理的文档数。东京的同步 API 为 1 TPS | `2` |
| `AsyncJobMaxSeconds` | 等待异步作业的秒数 | `600` |
| `EnableFieldExtraction` | 使用 Bedrock 提取字段。关闭时不授予 Bedrock 权限 | `false` |
| `BedrockModelId` | 字段提取使用的模型或推理配置文件 ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | 输出所带数据分类的默认值 | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | 平均置信度阈值 | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | 低置信度行的标准，以及使文档进入复核的字符占比 | `90` / `0.05` |
| `HandwritingWordRatioLimit` | 被判定为手写的单词占比上限 | `0.05` |
| `GatewayAuthorizerType` | `NONE`（仅限 PoC）或 `AWS_IAM` | `NONE` |
| `GatewayName` | Gateway 名称 | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS 通知地址（留空则跳过） | `""` |

## 部署

部署脚本依次执行 `sam build`、`sam package` 和 `aws cloudformation deploy`，部署后确认已保存的 `CollectionsJson`
和 `tools/list`。

```bash
# DemoMode（无需 FSx for ONTAP）
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points。要求签名调用并启用字段提取
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# 清理（加上 --delete-results 会同时删除保存 OCR 文本的结果存储桶）
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

集合的写法、代理的系统提示词和对话示例见 [docs/demo-guide.md](docs/demo-guide.md)（日语）。

## Human Review 阈值

用 `shared/human_review.py` 评估 OCR 的平均置信度（按字符数加权），再按下列条件上调。

| 条件 | 判定 |
|---|---|
| 平均置信度不低于 `ReviewAutoApproveThreshold`（0.95），且没有下列条件 | AUTO_APPROVE |
| 平均置信度低于 0.95 | HUMAN_REVIEW |
| 平均置信度低于 `ReviewRejectThreshold`（0.30） | REJECT |
| 置信度低于 90 的行中的字符超过总数的 5% | 上调为 HUMAN_REVIEW |
| 被判定为手写的单词超过 5% | 上调为 HUMAN_REVIEW |
| 存在合并单元格等结构可疑的表格 | 上调为 HUMAN_REVIEW |
| 未检测到任何行 | HUMAN_REVIEW |
| 字段提取中有无依据的字段，或提取失败 | 上调为 HUMAN_REVIEW（不改变 REJECT） |

默认阈值只是起点，并非实测得出的最优值。在 4 份虚构文档的运行中，包括字符错误为 0 的合同在内，4 份在默认阈值下都变成了
HUMAN_REVIEW（[docs/success-metrics.md](docs/success-metrics.md)）。请在自己的文档上测量分布后再决定。判定只包含在结果中，
本模式不做最终判断。`result.json` 保存仅基于 OCR 的判定，包含字段提取的最终判定在 `manifest.json` 和执行结果中。

## 数据分类

输出带有来自 `shared/data_classification.py` 的 `data_classification`。默认值为 `INTERNAL`，可用 `DataClassification`
更改，也可用集合的 `classification` 覆盖。结果存储桶使用 SSE-KMS、阻止公开访问、拒绝非 TLS 请求，删除堆栈后仍会保留。

## 字段提取（可选）

设置 `EnableFieldExtraction=true` 后，集合的 `fields` 中列出的字段（最多 20 个，每个不超过 40 个字符）会通过 Bedrock
Converse API 提取。模型随值返回来自原文的引用，代码会机械地确认该引用是否真的存在于 OCR 文本中（经 NFKC 规范化并去除
空白后做子串匹配）。找不到引用的字段为 `grounded: false`，只要有一个，文档就会变为 HUMAN_REVIEW。文档中没有写的字段也
算作无依据，因此 `fields` 中只应列出集合内所有文档都有的字段。

## Governance Note

- OCR 置信度是辅助信号，不是最终判断。实测中，一份错误为 0 的文档有 22.6% 的字符位于置信度低于 90 的行，而被误读的
  一行（“括孤”）置信度为 98.2。不要把置信度作为自动批准的唯一条件。
- 提取出的字段值是 LLM 的输出。引用校验可以减少编造，但不能保证正确。
- 从文档内容中取出的值，对代理而言是不可信的输入。请在系统提示词中说明，即使值里出现类似指令的语句也不要执行。
  对包含指令的文档的行为未做测量。
- PDF 和 TIFF 在处理期间会被复制到同一账户、同一区域的临时存储桶（SSE-KMS、阻止公开访问、作业结束时删除、以 1 天的
  生命周期规则兜底）。如果运维上不允许复制，请把集合的 `suffixes` 限制为图像。
- `GatewayAuthorizerType=NONE` 时，任何知道 URL 的人都能启动 OCR（不会返回文本）。仅用于 PoC，共享环境请使用
  `AWS_IAM`。authorizer 类型在创建后无法更改。
- Textract 无法取消已启动的作业。在 `AsyncJobMaxSeconds` 处停止等待，计费仍可能继续。
- 这是治理方面的指引，不能替代法律或合规判断。

## Performance Considerations

- 东京的同步 API 为 1 TPS。连续调用 20 次时，没有重试的客户端在并行 2 时被限流 4 次，并行 5 时 7 次；adaptive（最多 5 次）
  客户端在并行 1、2、5 时均为 0 次。`MapConcurrency` 的默认值为 2。
- 3 页 PDF（异步）通过本模式约 12 秒完成。
- 执行历史事件：同步文档每份 13 个，异步文档为 20 + 9 × 轮询次数。最坏情况下 100 份文档估计约 23,200 个，在 Standard 的
  上限 25,000 之内。
- 为使 Map 状态不超过 256 KiB，键非常长时 discovery 会选取少于 `max_files` 的文档并返回 `truncated`。
- Textract 的费用按页计算。东京 Price List 中 `text` 为 0.0015 USD/页，`structure`（Tables 与 Layout 之和）为
  0.019 USD/页（2026-10-01 起适用，未与账单核对）。

## 测试

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## 已知注意事项

- Forms 不支持日语。请求会被接受，但在备忘录上返回了在句子中间被拆开的键值对。
- `DescribeExecution` 需要 `includedData: "ALL_DATA"`。`GetExecutionHistory` 无法分页。
- 向 Gateway 传入日语会变成 `??`。本模式只传递 ASCII ID。
- `max_files` 按键的顺序从前面选取，因此第一份文档损坏时，每次都会选中它。
- 验证环境的 S3 Access Points 中没有图像和 PDF，因此未能在真实的 Access Point 上确认 OCR 成功
  （确认了列表、读取和临时副本的删除）。参见 [docs/demo-guide.md](docs/demo-guide.md) 的“既知の注意点”。

## 参考

- [Amazon Textract 新增包括日语在内的支持语言，并在东京区域上线（What's New）](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target（官方）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- 相关模式：[stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## 上生产前需要阅读的内容

部署后才会遇到的约束如何转化为设计决策，记录在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一内容放在两处时，停止更新的那份会比已修正的那份存留更久。

- [数据利用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 通过访问点访问数据的约束（所有模式通用）
- [安全与治理](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — 该模式的决策集中之处
- [构建](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上生产前通读（所有模式通用）
<!-- playbook-reading:end -->
