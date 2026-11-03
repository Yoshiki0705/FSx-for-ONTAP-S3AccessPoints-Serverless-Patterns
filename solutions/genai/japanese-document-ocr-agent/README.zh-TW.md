# 日語文件 OCR × AI 代理 — 在 S3 Access Points 上執行 Textract（東京）

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

這是一個範例：以東京區域的 Amazon Textract 讀取 FSx for ONTAP S3 Access Points 上的掃描文件（影像、PDF、TIFF），
並透過 Amazon Bedrock AgentCore Gateway 的 Step Functions 連接器，將這次執行作為 AI 代理工具公開。
Textract 對日語的支援及其在東京區域的上線已於 2026-11-02 發布。

代理只決定讀取哪個集合、使用哪個設定檔、最多處理多少份文件。步驟順序、重試與失敗處理由狀態機負責。
OCR 文字不會交給代理，而是寫入結果儲存貯體。

## 使用案例

- 對發票、合約、備忘錄等掃描文件，在檔案伺服器上原地進行日語 OCR
- 讓代理列出需要人工確認的文件及各自的原因
- 對無法使用 Textract Forms 的日語發票，連同依據一起擷取合計金額等欄位（選用）

## 架構

```
AI 代理 ──MCP──▶ AgentCore Gateway（NONE | AWS_IAM）
                       │ GatewayServiceRole：states:StartExecution 等
                       ▼
           Standard StateMachine（Discover → Map → Report）
                       │
   影像：將 bytes 傳給 Textract 同步 API    PDF / TIFF：暫時副本 → Textract 非同步 API
                       │
   S3 Access Points（DemoMode 為一般 S3）──▶ 結果儲存貯體（result.json / text.txt / manifest.json）
```

詳情請見 [docs/architecture.md](docs/architecture.md)（日語）。

## 公開的工具

| 工具 | 輸入 | 用途 |
|---|---|---|
| `ocr___StartExecution` | `input`（JSON 字串） | 啟動 OCR，回傳 `executionArn` |
| `ocr___DescribeExecution` | `executionArn`、`includedData: "ALL_DATA"` | 確認狀態與結果 |
| `ocr___ListExecutions` | `statusFilter`（選用） | 最近的執行清單 |
| `ocr___GetExecutionHistory` | `executionArn` | 查找停止位置（輸出較大） |
| `ocr___DescribeStateMachine` | `includedData`（選用） | 檢視定義 |

固定的狀態機 ARN 不會出現在工具中，代理無法變更。未帶 `includedData: "ALL_DATA"` 呼叫 `DescribeExecution`，
既不會回傳 `output`，也不會回傳 FAILED 執行的 `error` 與 `cause`。

## 代理傳入的輸入

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| 鍵 | 必填 | 規則 |
|---|---|---|
| `collection` | 是 | ASCII ID（`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`），必須在允許清單（`CollectionsJson`）中 |
| `profile` | 否 | `text`（僅文字）或 `structure`（文字、表格、版面）。省略時採用集合的設定 |
| `max_files` | 否 | 1 到 `MaxFilesPerExecution` 的整數。依鍵的順序從前面開始選取 |
| `modified_after` | 否 | `YYYY-MM-DD`。僅處理該日期之後修改的文件 |

不接受 S3 路徑與鍵。未知的鍵或違反規則的輸入會使執行以 FAILED 結束，`Cause` 會寫明修正方式。

## 處理路徑與設定檔

| 文件 | 路徑 | 備註 |
|---|---|---|
| PNG / JPEG，5 MiB 以下 | 同步，直接傳 bytes | 不產生副本 |
| PNG / JPEG，超過 5 MiB 且不超過 10 MiB | 非同步，暫時副本 | |
| PDF / TIFF | 非同步，暫時副本 | 不推測頁數 |

`text` 呼叫 `DetectDocumentText`，`structure` 呼叫 `AnalyzeDocument`（`TABLES` 與 `LAYOUT`）。不提供 Forms、
Queries、AnalyzeExpense 與 AnalyzeID（不支援日語，或在東京不被允許）。

## 代理收到的內容

`DescribeExecution`（`ALL_DATA`）的 `output` 包含狀態、件數、平均信賴度、需覆核的清單及各自原因，以及每份文件結果的
S3 URI。不包含 OCR 文字，但包含原始鍵（檔名）。啟用欄位擷取時，還包含欄位值（最多 60 個字元）。完整的文件清單在
結果儲存貯體的 `manifest.json` 中。

## 參數

| 參數 | 說明 | 預設值 |
|---|---|---|
| `S3AccessPointAlias` | S3 Access Points alias（DemoMode 下為一般儲存貯體名稱） | （必填） |
| `DemoMode` | `true` 時無需 FSx for ONTAP 即可執行 | `false` |
| `CollectionsJson` | 集合允許清單（JSON）。為空時依 `FilePrefix` 產生一個 | `""` |
| `MaxFilesPerExecution` | 每次執行的最大文件數（1–100） | `50` |
| `MapConcurrency` | 並行處理的文件數。東京的同步 API 為 1 TPS | `2` |
| `AsyncJobMaxSeconds` | 等待非同步作業的秒數 | `600` |
| `EnableFieldExtraction` | 以 Bedrock 擷取欄位。關閉時不授予 Bedrock 權限 | `false` |
| `BedrockModelId` | 欄位擷取使用的模型或推論設定檔 ID（[docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)） | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | 輸出所帶資料分類的預設值 | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | 平均信賴度門檻 | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | 低信賴度行的標準，以及使文件進入覆核的字元占比 | `90` / `0.05` |
| `HandwritingWordRatioLimit` | 被判定為手寫的單字占比上限 | `0.05` |
| `GatewayAuthorizerType` | `NONE`（僅限 PoC）或 `AWS_IAM` | `NONE` |
| `GatewayName` | Gateway 名稱 | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS 通知地址（留空則略過） | `""` |

## 部署

部署指令碼依序執行 `sam build`、`sam package` 與 `aws cloudformation deploy`，部署後確認已儲存的 `CollectionsJson`
與 `tools/list`。

```bash
# DemoMode（無需 FSx for ONTAP）
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points。要求簽署呼叫並啟用欄位擷取
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# 清理（加上 --delete-results 會一併刪除存放 OCR 文字的結果儲存貯體）
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

集合的寫法、代理的系統提示詞與對話範例請見 [docs/demo-guide.md](docs/demo-guide.md)（日語）。

## Human Review 門檻

以 `shared/human_review.py` 評估 OCR 的平均信賴度（依字元數加權），再依下列條件上調。

| 條件 | 判定 |
|---|---|
| 平均信賴度不低於 `ReviewAutoApproveThreshold`（0.95），且沒有下列條件 | AUTO_APPROVE |
| 平均信賴度低於 0.95 | HUMAN_REVIEW |
| 平均信賴度低於 `ReviewRejectThreshold`（0.30） | REJECT |
| 信賴度低於 90 的行中的字元超過總數的 5% | 上調為 HUMAN_REVIEW |
| 被判定為手寫的單字超過 5% | 上調為 HUMAN_REVIEW |
| 存在合併儲存格等結構可疑的表格 | 上調為 HUMAN_REVIEW |
| 未偵測到任何行 | HUMAN_REVIEW |
| 欄位擷取中有無依據的欄位，或擷取失敗 | 上調為 HUMAN_REVIEW（不改變 REJECT） |

預設門檻只是起點，並非實測得出的最佳值。在 4 份虛構文件的執行中，包括字元錯誤為 0 的合約在內，4 份在預設門檻下都變成了
HUMAN_REVIEW（[docs/success-metrics.md](docs/success-metrics.md)）。請在自己的文件上量測分布後再決定。判定只包含在結果中，
本模式不做最終判斷。`result.json` 保存僅基於 OCR 的判定，包含欄位擷取的最終判定在 `manifest.json` 與執行結果中。

## 資料分類

輸出帶有來自 `shared/data_classification.py` 的 `data_classification`。預設值為 `INTERNAL`，可用 `DataClassification`
變更，也可用集合的 `classification` 覆寫。結果儲存貯體使用 SSE-KMS、封鎖公開存取、拒絕非 TLS 請求，刪除堆疊後仍會保留。

## 欄位擷取（選用）

設定 `EnableFieldExtraction=true` 後，集合的 `fields` 中列出的欄位（最多 20 個，每個不超過 40 個字元）會透過 Bedrock
Converse API 擷取。模型隨值回傳來自原文的引文，程式碼會機械式地確認該引文是否真的存在於 OCR 文字中（經 NFKC 正規化並移除
空白後做子字串比對）。找不到引文的欄位為 `grounded: false`，只要有一個，文件就會變為 HUMAN_REVIEW。文件中沒有寫的欄位也
算作無依據，因此 `fields` 中只應列出集合內所有文件都有的欄位。

## Governance Note

- OCR 信賴度是輔助訊號，不是最終判斷。實測中，一份錯誤為 0 的文件有 22.6% 的字元位於信賴度低於 90 的行，而被誤讀的
  一行（「括孤」）信賴度為 98.2。不要把信賴度作為自動核准的唯一條件。
- 擷取出的欄位值是 LLM 的輸出。引文檢查可以減少捏造，但不能保證正確。
- 從文件內容中取出的值，對代理而言是不可信的輸入。請在系統提示詞中說明，即使值裡出現類似指令的語句也不要照做。
  對包含指令的文件的行為未做量測。
- PDF 與 TIFF 在處理期間會被複製到同一帳戶、同一區域的暫時儲存貯體（SSE-KMS、封鎖公開存取、作業結束時刪除、以 1 天的
  生命週期規則作為後盾）。若營運上不允許複製，請將集合的 `suffixes` 限制為影像。
- `GatewayAuthorizerType=NONE` 時，任何知道 URL 的人都能啟動 OCR（不會回傳文字）。僅用於 PoC，共用環境請使用
  `AWS_IAM`。authorizer 類型在建立後無法變更。
- Textract 無法取消已啟動的作業。在 `AsyncJobMaxSeconds` 處停止等待，計費仍可能持續。
- 這是治理方面的指引，不能取代法律或合規判斷。

## Performance Considerations

- 東京的同步 API 為 1 TPS。連續呼叫 20 次時，沒有重試的用戶端在並行 2 時被限流 4 次，並行 5 時 7 次；adaptive（最多 5 次）
  用戶端在並行 1、2、5 時均為 0 次。`MapConcurrency` 的預設值為 2。
- 3 頁 PDF（非同步）透過本模式約 12 秒完成。
- 執行歷程事件：同步文件每份 13 個，非同步文件為 20 + 9 × 輪詢次數。最壞情況下 100 份文件估計約 23,200 個，在 Standard 的
  上限 25,000 之內。
- 為使 Map 狀態不超過 256 KiB，鍵非常長時 discovery 會選取少於 `max_files` 的文件並回傳 `truncated`。
- Textract 的費用按頁計算。東京 Price List 中 `text` 為 0.0015 USD/頁，`structure`（Tables 與 Layout 之和）為
  0.019 USD/頁（2026-10-01 起適用，未與帳單核對）。

## 測試

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## 已知注意事項

- Forms 不支援日語。請求會被接受，但在備忘錄上回傳了在句子中間被拆開的鍵值對。
- `DescribeExecution` 需要 `includedData: "ALL_DATA"`。`GetExecutionHistory` 無法分頁。
- 向 Gateway 傳入日語會變成 `??`。本模式只傳遞 ASCII ID。
- `max_files` 依鍵的順序從前面選取，因此第一份文件損毀時，每次都會選中它。
- 驗證環境的 S3 Access Points 中沒有影像與 PDF，因此未能在真實的 Access Point 上確認 OCR 成功
  （確認了清單、讀取與暫時副本的刪除）。請參閱 [docs/demo-guide.md](docs/demo-guide.md) 的「既知の注意点」。

## 參考

- [Amazon Textract 新增包括日語在內的支援語言，並在東京區域上線（What's New）](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target（官方）](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- 相關模式：[stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## 上線前需要閱讀的內容

部署後才會遇到的限制如何轉化為設計決策，記錄在 [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook)。同一內容放在兩處時，停止更新的那份會比已修正的那份留存更久。

- [資料活用](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — 透過存取點存取資料的限制（所有模式通用）
- [安全與治理](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — 該模式的決策集中之處
- [建置](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — 上線前通讀（所有模式通用）
<!-- playbook-reading:end -->
