# UC13: 教育 / 研究 — 论文 PDF 自动分类·引用网络分析

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        PAPERS["论文 PDF / 研究数据<br/>.pdf, .csv, .json, .xml"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(6 hours)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内执行<br/>• S3 AP 文件检测<br/>• .pdf 过滤<br/>• Manifest 生成"]
        OCR["2️⃣ OCR Lambda<br/>• 通过 S3 AP 获取 PDF<br/>• Textract (跨区域)<br/>• 文本提取<br/>• 结构化文本输出"]
        META["3️⃣ Metadata Lambda<br/>• 标题提取<br/>• 作者名提取<br/>• DOI / ISSN 检测<br/>• 出版年份・期刊名称"]
        CL["4️⃣ Classification Lambda<br/>• Bedrock InvokeModel<br/>• 研究领域分类<br/>  (CS, Bio, Physics, etc.)<br/>• 关键词提取<br/>• 结构化摘要"]
        CA["5️⃣ Citation Analysis Lambda<br/>• 参考文献部分解析<br/>• 引用关系提取<br/>• 引用网络构建<br/>• 邻接表 JSON 输出"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        TEXT["ocr-text/*.txt<br/>OCR 提取文本"]
        METADATA["metadata/*.json<br/>结构化元数据"]
        CLASS["classification/*.json<br/>领域分类结果"]
        CITE["citations/*.json<br/>引用网络"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>处理完成通知"]
    end

    PAPERS --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    OCR --> META
    META --> CL
    CL --> CA
    OCR --> TEXT
    META --> METADATA
    CL --> CLASS
    CA --> CITE
    CA --> SNS
```

---

## Data Flow Detail

### Input
| Item | Description |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .pdf (论文 PDF)、.csv, .json, .xml (研究数据) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 获取完整 PDF（OCR・元数据提取所需） |

### Processing
| Step | Service | Function |
|------|---------|----------|
| Discovery | Lambda (VPC) | 通过 S3 AP 检测论文 PDF，生成 Manifest |
| OCR | Lambda + Textract | PDF 文本提取（支持跨区域） |
| Metadata | Lambda | 论文元数据提取（标题、作者、DOI、出版年份） |
| Classification | Lambda + Bedrock | 研究领域分类、关键词提取、结构化摘要生成 |
| Citation Analysis | Lambda | 参考文献解析、引用网络构建（邻接表） |

### Output
| Artifact | Format | Description |
|----------|--------|-------------|
| OCR Text | `ocr-text/YYYY/MM/DD/{stem}.txt` | Textract 提取文本 |
| Metadata | `metadata/YYYY/MM/DD/{stem}.json` | 结构化元数据（title, authors, DOI, year） |
| Classification | `classification/YYYY/MM/DD/{stem}_class.json` | 领域分类・关键词・摘要 |
| Citation Network | `citations/YYYY/MM/DD/citation_network.json` | 引用网络（邻接表格式） |
| SNS Notification | Email | 处理完成通知（处理数量・分类结果摘要） |

---

## Key Design Decisions

1. **S3 AP over NFS** — 无需从 Lambda 挂载 NFS，通过 S3 API 获取论文 PDF
2. **Textract 跨区域** — 即使在 Textract 不支持的区域也可通过跨区域调用实现
3. **5 阶段流水线** — 按 OCR → Metadata → Classification → Citation 的顺序逐步积累信息
4. **通过 Bedrock 进行领域分类** — 基于预定义分类体系（ACM CCS 等）的自动分类
5. **引用网络（邻接表）** — 以图结构表示引用关系，支持下游分析（PageRank、社区检测）
6. **基于轮询** — 由于 S3 AP 不支持事件通知，采用定期调度执行

---

## AWS Services Used

| Service | Role |
|---------|------|
| FSx for NetApp ONTAP | 论文・研究数据存储 |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 定期触发器 |
| Step Functions | 工作流编排 |
| Lambda | 计算（Discovery, OCR, Metadata, Classification, Citation Analysis） |
| Amazon Textract | PDF 文本提取（跨区域） |
| Amazon Bedrock | 领域分类・关键词提取 (Claude / Nova) |
| SNS | 处理完成通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性 |
