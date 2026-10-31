# Step Functions × AgentCore Gateway — 將工作流程作為 AI 代理工具

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

本範例透過 Amazon Bedrock AgentCore Gateway 內建的 Step Functions 連接器，將處理
FSx for ONTAP S3 Access Points 上檔案的 Standard Step Functions 工作流程（探索 → 處理 →
報告）公開為 AI 代理工具。

代理決定何時執行以及傳入什麼輸入，步驟順序由狀態機保證。固定流程放在工作流程，
執行判斷交給代理。

## 使用案例

- 不修改狀態機，從代理啟動既有的 Step Functions 工作流程
- 將流程與核准固定在工作流程中，僅將執行判斷委派給代理
- 讓代理從執行歷史中查看執行進行到哪一步

## 架構

```
AI 代理 ──MCP──▶ AgentCore Gateway (Step Functions 連接器)
                   │ GatewayServiceRole → states:StartExecution 等
                   ▼
          Standard StateMachine (Discover→Choice→Map→Report)
                   │
      Discovery / Processing / Report Lambda
                   │
             S3 Access Point (FSx for ONTAP / DemoMode 為一般 S3)
```

詳情參見 [docs/architecture.md](docs/architecture.md)。

## 公開的工具

| 工具 | 輸入 | 用途 |
|---|---|---|
| `workflow___StartExecution` | `input`（JSON 字串） | 啟動工作流程 |
| `workflow___ListExecutions` | `statusFilter`（選用） | 執行清單（僅 Standard） |
| `workflow___DescribeStateMachine` | `includedData`（選用） | 狀態機中繼資料/定義 |
| `workflow___DescribeExecution` | `executionArn`、`includedData` | 查看狀態與結果 |
| `workflow___GetExecutionHistory` | `executionArn` | 步驟歷史 |

固定的狀態機 ARN 不會出現在工具中，代理無法變更。

## 參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `S3AccessPointAlias` | FSx for ONTAP 磁碟區的 S3 AP Alias（DemoMode 下為一般儲存貯體名稱） | (必填) |
| `DemoMode` | `true` 時不需要 FSx for ONTAP（一般 S3 儲存貯體） | `false` |
| `FilePrefix` | 掃描的前綴 | `input/` |
| `BedrockModelId` | 摘要模型 / 推論設定檔 ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | 每次執行的最大檔案數 | `100` |
| `NotificationEmail` | SNS 通知對象（留空則略過） | `""` |
| `GatewayName` | Gateway 名稱（部署指令碼使用） | `sfn-agentcore-tools-gateway` |

## 部署

Gateway 與連接器目標都是 CloudFormation 一等資源
（`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`），因此整個模式用一個範本宣告式完成。
部署指令碼是 `sam build` + `sam deploy` 的包裝，部署後驗證 `tools/list`。

```bash
# DemoMode（不需要 FSx for ONTAP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# 生產（S3 AP）
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# 清理
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

對話範例與驗證步驟見 [docs/demo-guide.md](docs/demo-guide.md)。

## Human Review 門檻

Processing Lambda 使用 `shared/human_review.py` 評估摘要信賴度。

| 信賴度 | 判定 |
|---|---|
| `>= 0.85`（預設 `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`） | AUTO_APPROVE |
| `>= 0.30`（預設 `HUMAN_REVIEW_REJECT_THRESHOLD`）且 `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

門檻可透過環境變數覆寫。判定僅包含在結果中，本模式不會自動做出最終判斷。

## 資料分類

Report Lambda 為輸出加上來自 `shared/data_classification.py` 的 `data_classification`
標籤（預設 `INTERNAL`，可用 `DATA_CLASSIFICATION` 變更）。

## Governance Note

- 代理只負責執行判斷與狀態確認。順序、分支與核准由狀態機保證，代理無法略過或重排。
- 固定的狀態機 ARN 不會公開，代理無法啟動其他狀態機。
- AI 摘要/分類是**輔助訊號**，不是最終判斷。信賴度低於門檻時轉交人工審查。
- 工作權杖操作（`SendTaskSuccess` 等）在此不公開，因為 IAM 無法將其限定到特定執行。
- 這是治理指南，不取代法律或合規判斷。

## 測試

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## 已知注意事項

同區域限制、每個操作一個 pin、日語輸入的 `?` 亂碼及 `\uXXXX` 規避、Cedar 的 `input`
條件限制，均整理在 [docs/demo-guide.md](docs/demo-guide.md)。

## 參考

- [AWS Step Functions as Connector Target（官方）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools（What's New）](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)

---

<!-- playbook-reading:start -->
## 上線前需要閱讀的內容

部署後才會遇到的限制如何轉化為設計決策，記錄在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一內容放在兩處時，停止更新的那份會比已修正的那份留存更久。

- [資料活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 透過存取點存取資料的限制（所有模式通用）
- [安全與治理](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — 該模式的決策集中之處
- [建置](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上線前通讀（所有模式通用）
<!-- playbook-reading:end -->
