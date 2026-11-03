# Japanese Document OCR × AI Agents — Textract (Tokyo) over S3 Access Points

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

A sample that reads scanned documents (images, PDF, TIFF) on FSx for ONTAP S3 Access Points with Amazon Textract in
the Tokyo Region, and exposes the run as AI agent tools through the Amazon Bedrock AgentCore Gateway Step Functions
connector. Textract's Japanese support and its availability in Tokyo were announced on 2026-11-02.

The agent decides only which collection to read, with which profile, and how many documents. The state machine owns the
order of steps, retries, and failure handling. OCR text never goes to the agent; it is written to a results bucket.

## Use Cases

- OCR Japanese scans such as invoices, contracts, and memos while they stay on the file server
- Have an agent list the documents that need a person's review, with the reason for each
- Extract fields such as the invoice total, with their evidence, from Japanese invoices where Textract Forms is not
  available (optional)

## Architecture

```
AI agent ──MCP──▶ AgentCore Gateway (NONE | AWS_IAM)
                       │ GatewayServiceRole: states:StartExecution and others
                       ▼
           Standard StateMachine (Discover → Map → Report)
                       │
   Images: bytes to Textract (sync)    PDF / TIFF: short-lived copy → Textract (async)
                       │
   S3 Access Points (regular S3 in DemoMode) ──▶ results bucket (result.json / text.txt / manifest.json)
```

See [docs/architecture.md](docs/architecture.md) for details (Japanese).

## Tools exposed

| Tool | Input | Purpose |
|---|---|---|
| `ocr___StartExecution` | `input` (JSON string) | Start OCR. Returns `executionArn` |
| `ocr___DescribeExecution` | `executionArn`, `includedData: "ALL_DATA"` | Status and result |
| `ocr___ListExecutions` | `statusFilter` (optional) | Recent executions |
| `ocr___GetExecutionHistory` | `executionArn` | Find where a run stopped (large output) |
| `ocr___DescribeStateMachine` | `includedData` (optional) | Inspect the definition |

The pinned state machine ARN is not part of any tool, so the agent cannot change it. `DescribeExecution` without
`includedData: "ALL_DATA"` returns neither `output` nor, for a FAILED run, `error` and `cause`.

## Input the agent passes

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| Key | Required | Rule |
|---|---|---|
| `collection` | Yes | ASCII ID (`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`) present in the allow-list (`CollectionsJson`) |
| `profile` | No | `text` (characters only) or `structure` (characters, tables, layout). Defaults to the collection's setting |
| `max_files` | No | Integer from 1 to `MaxFilesPerExecution`. Documents are taken in key order |
| `modified_after` | No | `YYYY-MM-DD`. Only documents modified on or after that date |

S3 paths and keys are not accepted. An unknown key or a rule violation ends the run as FAILED, and `Cause` says how
to fix it.

## Routes and profiles

| Document | Route | Note |
|---|---|---|
| PNG / JPEG, up to 5 MiB | Sync, bytes passed inline | No copy is made |
| PNG / JPEG, over 5 MiB up to 10 MiB | Async, short-lived copy | |
| PDF / TIFF | Async, short-lived copy | The page count is not guessed |

`text` calls `DetectDocumentText`; `structure` calls `AnalyzeDocument` (`TABLES` and `LAYOUT`). Forms, Queries,
AnalyzeExpense, and AnalyzeID are not offered (not supported for Japanese, or not allowed in Tokyo).

## What the agent gets back

The `output` of `DescribeExecution` (`ALL_DATA`) holds the status, counts, mean confidence, the review list with the
reason for each, and the S3 URI of each document's result. It holds no OCR text. It does include the original key (file
name). With field extraction on, it also holds the field values (up to 60 characters). The complete list is
`manifest.json` in the results bucket.

## Parameters

| Parameter | Description | Default |
|---|---|---|
| `S3AccessPointAlias` | S3 Access Points alias (a regular bucket name in DemoMode) | (required) |
| `DemoMode` | `true` runs without FSx for ONTAP | `false` |
| `CollectionsJson` | Allow-list of collections (JSON). If empty, one is built from `FilePrefix` | `""` |
| `MaxFilesPerExecution` | Maximum documents per execution (1–100) | `50` |
| `MapConcurrency` | Documents processed in parallel. The Tokyo sync API is 1 TPS | `2` |
| `AsyncJobMaxSeconds` | How long to wait for an async job | `600` |
| `EnableFieldExtraction` | Field extraction with Bedrock. When off, no Bedrock permission is granted | `false` |
| `BedrockModelId` | Model or inference profile ID for field extraction ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | Default data classification label on outputs | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | Mean-confidence thresholds | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | What counts as a low-confidence line, and the share of characters that sends a document to review | `90` / `0.05` |
| `HandwritingWordRatioLimit` | Upper limit of words detected as handwriting | `0.05` |
| `GatewayAuthorizerType` | `NONE` (PoC only) or `AWS_IAM` | `NONE` |
| `GatewayName` | Gateway name | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS notification address (empty to skip) | `""` |

## Deploy

The deploy script runs `sam build`, `sam package`, and `aws cloudformation deploy`, then checks the stored
`CollectionsJson` and `tools/list`.

```bash
# DemoMode (no FSx for ONTAP)
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points. Require signed calls and turn on field extraction
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# Cleanup (--delete-results also deletes the results bucket, which holds OCR text)
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

How to write collections, the agent system prompt, and example conversations are in
[docs/demo-guide.md](docs/demo-guide.md) (Japanese).

## Human Review thresholds

The mean OCR confidence (weighted by character count) is evaluated with `shared/human_review.py`, then raised by these
conditions.

| Condition | Decision |
|---|---|
| Mean confidence at or above `ReviewAutoApproveThreshold` (0.95) and none of the conditions below | AUTO_APPROVE |
| Mean confidence below 0.95 | HUMAN_REVIEW |
| Mean confidence below `ReviewRejectThreshold` (0.30) | REJECT |
| More than 5% of characters are in lines below confidence 90 | Raised to HUMAN_REVIEW |
| More than 5% of words are detected as handwriting | Raised to HUMAN_REVIEW |
| A table with a doubtful structure, such as a merged cell | Raised to HUMAN_REVIEW |
| No line detected | HUMAN_REVIEW |
| Field extraction has a field without evidence, or failed | Raised to HUMAN_REVIEW (REJECT is not changed) |

The defaults are a starting point, not measured optima. In a run of four synthetic documents, all four went to
HUMAN_REVIEW under the defaults, including a contract with zero character errors
([docs/success-metrics.md](docs/success-metrics.md)). Measure the distribution on your own documents before choosing.
The decision is only included in the result; the pattern does not make the final call. `result.json` holds the
OCR-only decision. The final decision, including field extraction, is in `manifest.json` and the execution result.

## Data classification

Outputs carry a `data_classification` from `shared/data_classification.py`. The default is `INTERNAL`; change it with
`DataClassification`, or override it per collection with `classification`. The results bucket uses SSE-KMS, blocks
public access, denies non-TLS requests, and is kept when the stack is deleted.

## Field extraction (optional)

With `EnableFieldExtraction=true`, the fields listed in a collection's `fields` (up to 20, each up to 40 characters)
are extracted with the Bedrock Converse API. The model returns each value with a quote from the source text, and the
code checks mechanically that the quote exists in the OCR text (substring match after NFKC normalization and whitespace
removal). A field whose quote is not found is `grounded: false`, and one such field sends the document to
HUMAN_REVIEW. A field the document does not contain also counts as ungrounded, so list in `fields` only items that
every document in the collection carries.

## Governance Note

- OCR confidence is an assistive signal, not a final decision. In the measured run, a document with zero errors had
  22.6% of its characters in lines below confidence 90, and a line in which a common word was misread by one character had confidence 98.2. Do not make
  confidence the only condition for automatic approval.
- Extracted field values are LLM output. The quote check reduces fabrication but does not guarantee correctness.
- Values taken from document content are untrusted input for an agent. Tell the agent in its system prompt not to
  follow instructions that appear in a value. The behavior with a document that contains instructions was not measured.
- PDF and TIFF files are copied to a short-lived bucket in the same account and Region while they are processed
  (SSE-KMS, public access blocked, deleted when the job ends, a 1-day lifecycle rule as a backstop). If your policy
  does not allow copies, limit the collection's `suffixes` to images.
- `GatewayAuthorizerType=NONE` lets anyone who knows the URL start OCR runs (no text is returned). Use it for a PoC
  only; use `AWS_IAM` in shared environments. The authorizer type cannot be changed after creation. <!-- [E-017] -->
- Textract cannot cancel a started job. Giving up at `AsyncJobMaxSeconds` does not stop the charge. <!-- [E-018] -->
- This is governance guidance, not a substitute for legal or compliance judgment.

## Performance Considerations

- The Tokyo sync API is 1 TPS. In 20 consecutive calls, a client without retries was throttled 4 times at 2 workers and
  7 times at 5; an adaptive client (up to 5 attempts) was throttled 0 times at 1, 2, and 5. `MapConcurrency` defaults to 2.
- A 3-page PDF (async) finished in about 12 seconds through the pattern.
- Execution history events: 13 per sync document, and 20 + 9 × polls per async document. The worst case for 100
  documents is estimated at about 23,200, inside the Standard limit of 25,000.
- To keep the Map state under 256 KiB, very long keys make discovery select fewer documents than `max_files` and
  return `truncated`.
- The Textract cost is per page. The Tokyo Price List gives 0.0015 USD per page for `text` and 0.019 USD per page for
  `structure` (Tables plus Layout), effective 2026-10-01; not checked against a bill.

## Tests

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## Known gotchas

- Forms does not support Japanese. The request is accepted, but on the memo it returned pairs split mid-sentence.
- `DescribeExecution` needs `includedData: "ALL_DATA"`. `GetExecutionHistory` cannot be paged.
- Japanese in a Gateway input becomes `??`. This pattern passes only ASCII IDs.
- `max_files` takes documents in key order, so a corrupt first document is selected every time.
- The S3 Access Points in the verification environment held no images or PDFs, so an OCR success on a real Access
  Point was not confirmed (listing, reading, and deleting the staged copy were). See "Known gotchas" in
  [docs/demo-guide.md](docs/demo-guide.md).

## References

- [Amazon Textract adds Japanese and other languages and launches in Tokyo (What's New)](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target (official)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- Related pattern: [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## Read before going to production

How the constraints that surface after deploying translate into design decisions is covered in the [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook). The same content in two places means the copy that stops being updated outlives the one that was corrected.

- [Data Utilization](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — constraints of reaching data through an access point (every pattern)
- [Security & Governance](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — where the decisions concentrate for this pattern
- [Build](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — run through before production (every pattern)
<!-- playbook-reading:end -->
