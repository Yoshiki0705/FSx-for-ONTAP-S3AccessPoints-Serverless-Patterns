# UC2: 金融 / 保险 — 合同与发票自动处理 (IDP)

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端到端架构 (输入 → 输出)

---

## 高层级流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/documents/                                                             │
│  ├── 契約書/保険契約_2024-001.pdf    (スキャン PDF)                          │
│  ├── 請求書/invoice_20240315.tiff    (複合機スキャン)                        │
│  ├── 申込書/application_form.jpeg    (手書き申込書)                          │
│  └── 見積書/quotation_v2.pdf         (電子 PDF)                             │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-idp-vol-ext-s3alias                                             │
│  • ListObjectsV2 (document discovery)                                        │
│  • GetObject (PDF/TIFF/JPEG retrieval)                                       │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌─────────────┐    ┌──────────────────────┐    ┌────────────────┐          │
│  │  Discovery   │───▶│  OCR                 │───▶│Entity Extraction│         │
│  │  Lambda      │    │  Lambda              │    │ Lambda         │          │
│  │             │    │                      │    │               │          │
│  │  • VPC内     │    │  • Textract sync/    │    │  • Comprehend  │          │
│  │  • S3 AP List│    │    async API auto-   │    │  • Named Entity│          │
│  │  • PDF/TIFF  │    │    selection         │    │  • Date/Amount │          │
│  └─────────────┘    └──────────────────────┘    └───────┬────────┘          │
│                                                          │                   │
│                                                          ▼                   │
│                                                 ┌────────────────┐          │
│                                                 │    Summary      │          │
│                                                 │    Lambda       │          │
│                                                 │               │          │
│                                                 │ • Bedrock      │          │
│                                                 │ • JSON output  │          │
│                                                 └────────────────┘          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── ocr-text/YYYY/MM/DD/                                                    │
│  │   ├── 保険契約_2024-001.txt       ← OCR extracted text                   │
│  │   └── invoice_20240315.txt                                                │
│  ├── entities/YYYY/MM/DD/                                                    │
│  │   ├── 保険契約_2024-001.json      ← Extracted entities                   │
│  │   └── invoice_20240315.json                                               │
│  └── summaries/YYYY/MM/DD/                                                   │
│      ├── 保険契約_2024-001_summary.json  ← Structured summary               │
│      └── invoice_20240315_summary.json                                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid 图表

```mermaid
flowchart TB
    subgraph INPUT["📥 输入 — FSx for NetApp ONTAP"]
        DOCS["文档文件<br/>.pdf, .tiff, .jpeg"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 触发器"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions 工作流"]
        DISC["1️⃣ Discovery Lambda<br/>• 在 VPC 内运行<br/>• S3 AP 文件发现<br/>• .pdf/.tiff/.jpeg 过滤<br/>• 清单生成"]
        OCR["2️⃣ OCR Lambda<br/>• 通过 S3 AP 获取文档<br/>• 页数判定<br/>• Textract sync API (≤1 页)<br/>• Textract async API (>1 页)<br/>• 文本提取并输出到 S3"]
        ENT["3️⃣ Entity Extraction Lambda<br/>• Amazon Comprehend 调用<br/>• 命名实体识别<br/>• 日期、金额、组织、人物提取<br/>• JSON 输出到 S3"]
        SUM["4️⃣ Summary Lambda<br/>• Amazon Bedrock (Nova/Claude)<br/>• 结构化摘要生成<br/>• 合同条款、金额、当事方整理<br/>• JSON 输出到 S3"]
    end

    subgraph OUTPUT["📤 输出 — S3 Bucket"]
        TEXT["ocr-text/*.txt<br/>OCR 提取文本"]
        ENTITIES["entities/*.json<br/>提取的实体"]
        SUMMARY["summaries/*.json<br/>结构化摘要"]
    end

    subgraph NOTIFY["📧 通知"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    DOCS --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    OCR --> ENT
    ENT --> SUM
    OCR --> TEXT
    ENT --> ENTITIES
    SUM --> SUMMARY
    SUM --> SNS
```

---

## 数据流详情

### 输入
| 项目 | 说明 |
|------|------|
| **来源** | FSx for NetApp ONTAP 卷 |
| **文件类型** | .pdf, .tiff, .tif, .jpeg, .jpg (扫描及电子文档) |
| **访问方式** | S3 Access Point (ListObjectsV2 + GetObject) |
| **读取策略** | 全文件获取 (OCR 处理所需) |

### 处理
| 步骤 | 服务 | 功能 |
|------|------|------|
| Discovery | Lambda (VPC) | 通过 S3 AP 发现文档文件，生成清单 |
| OCR | Lambda + Textract | 根据页数自动选择 sync/async API 进行文本提取 |
| Entity Extraction | Lambda + Comprehend | 命名实体识别 (日期、金额、组织、人物) |
| Summary | Lambda + Bedrock | 结构化摘要生成 (合同条款、金额、当事方) |

### 输出
| 产出物 | 格式 | 说明 |
|--------|------|------|
| OCR 文本 | `ocr-text/YYYY/MM/DD/{stem}.txt` | Textract 提取文本 |
| 实体 | `entities/YYYY/MM/DD/{stem}.json` | Comprehend 提取实体 |
| 摘要 | `summaries/YYYY/MM/DD/{stem}_summary.json` | Bedrock 结构化摘要 |
| SNS 通知 | Email | 处理完成通知 (处理数量及错误数量) |

---

## 关键设计决策

1. **S3 AP 替代 NFS** — Lambda 无需 NFS 挂载；通过 S3 API 获取文档
2. **Textract sync/async 自动选择** — 单页使用 sync API (低延迟)，多页文档使用 async API (高容量)
3. **Comprehend + Bedrock 两阶段方法** — Comprehend 用于结构化实体提取，Bedrock 用于自然语言摘要生成
4. **JSON 结构化输出** — 便于与下游系统 (RPA、核心业务系统) 集成
5. **日期分区** — 按处理日期分割目录，便于重新处理和历史管理
6. **轮询 (非事件驱动)** — S3 AP 不支持事件通知，因此使用定期调度执行

---

## 使用的 AWS 服务

| 服务 | 角色 |
|------|------|
| FSx for NetApp ONTAP | 企业文件存储 (合同及发票) |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 定期触发 |
| Step Functions | 工作流编排 |
| Lambda | 计算 (Discovery, OCR, Entity Extraction, Summary) |
| Amazon Textract | OCR 文本提取 (sync/async API) |
| Amazon Comprehend | 命名实体识别 (NER) |
| Amazon Bedrock | AI 摘要生成 (Nova / Claude) |
| SNS | 处理完成通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性 |
