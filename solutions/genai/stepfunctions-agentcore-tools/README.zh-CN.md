# Step Functions × AgentCore Gateway — 将工作流作为 AI 代理工具

🌐 **Language / 语言**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

本示例通过 Amazon Bedrock AgentCore Gateway 内置的 Step Functions 连接器，将处理
FSx for ONTAP S3 Access Points 上文件的 Standard Step Functions 工作流（发现 → 处理 →
报告）暴露为 AI 代理工具。

代理决定何时运行以及传入什么输入，步骤顺序由状态机保证。固定流程放在工作流，
运行判断交给代理。

## 使用场景

- 不修改状态机，从代理启动现有的 Step Functions 工作流
- 将流程和审批固定在工作流中，仅把运行判断委托给代理
- 让代理从执行历史中查看执行进行到哪一步

## 架构

```
AI 代理 ──MCP──▶ AgentCore Gateway (Step Functions 连接器)
                   │ GatewayServiceRole → states:StartExecution 等
                   ▼
          Standard StateMachine (Discover→Choice→Map→Report)
                   │
      Discovery / Processing / Report Lambda
                   │
             S3 Access Point (FSx for ONTAP / DemoMode 为普通 S3)
```

详情参见 [docs/architecture.md](docs/architecture.md)。

## 暴露的工具

| 工具 | 输入 | 用途 |
|---|---|---|
| `workflow___StartExecution` | `input`（JSON 字符串） | 启动工作流 |
| `workflow___ListExecutions` | `statusFilter`（可选） | 执行列表（仅 Standard） |
| `workflow___DescribeStateMachine` | `includedData`（可选） | 状态机元数据/定义 |
| `workflow___DescribeExecution` | `executionArn`、`includedData` | 查看状态与结果 |
| `workflow___GetExecutionHistory` | `executionArn` | 步骤历史 |

固定的状态机 ARN 不会出现在工具中，代理无法更改。

## 参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `S3AccessPointAlias` | FSx for ONTAP 卷的 S3 AP Alias（DemoMode 下为普通存储桶名称） | (必填) |
| `DemoMode` | `true` 时无需 FSx for ONTAP（普通 S3 存储桶） | `false` |
| `FilePrefix` | 扫描的前缀 | `input/` |
| `BedrockModelId` | 摘要模型 / 推理配置文件 ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 每次执行的最大文件数 | `100` |
| `NotificationEmail` | SNS 通知对象（留空则跳过） | `""` |
| `GatewayName` | Gateway 名称（部署脚本使用） | `sfn-agentcore-tools-gateway` |

## 部署

Gateway 本体和 Step Functions 连接器目标不受 CloudFormation 支持，因此模板创建
Lambda、状态机和 Gateway 服务角色，Gateway 与目标由部署脚本创建。

```bash
# DemoMode（无需 FSx for ONTAP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# 生产（S3 AP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# 清理
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

对话示例和验证步骤见 [docs/demo-guide.md](docs/demo-guide.md)。

## Human Review 阈值

Processing Lambda 使用 `shared/human_review.py` 评估摘要置信度。

| 置信度 | 判定 |
|---|---|
| `>= 0.85`（默认 `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`） | AUTO_APPROVE |
| `>= 0.30`（默认 `HUMAN_REVIEW_REJECT_THRESHOLD`）且 `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

阈值可通过环境变量覆盖。判定仅包含在结果中，本模式不会自动做出最终判断。

## 数据分类

Report Lambda 为输出添加来自 `shared/data_classification.py` 的 `data_classification`
标签（默认 `INTERNAL`，可用 `DATA_CLASSIFICATION` 更改）。

## Governance Note

- 代理只负责运行判断和状态确认。顺序、分支和审批由状态机保证，代理无法跳过或重排。
- 固定的状态机 ARN 不会暴露，代理无法启动其他状态机。
- AI 摘要/分类是**辅助信号**，不是最终判断。置信度低于阈值时转交人工审核。
- 任务令牌操作（`SendTaskSuccess` 等）在此不暴露，因为 IAM 无法将其限定到具体执行。
- 这是治理指南，不替代法律或合规判断。

## 测试

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## 已知注意事项

同区域约束、每个操作一个 pin、日语输入的 `?` 乱码及 `\uXXXX` 规避、Cedar 的 `input`
条件限制，均整理在 [docs/demo-guide.md](docs/demo-guide.md#既知の注意点)。

## 参考

- [AWS Step Functions as Connector Target（官方）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools（What's New）](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)
