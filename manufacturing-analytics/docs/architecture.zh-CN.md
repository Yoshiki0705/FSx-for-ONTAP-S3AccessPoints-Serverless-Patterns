# UC3: 制造业 — IoT 传感器日志·质量检查图像的分析

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## End-to-End Architecture (Input → Output)

---

## Architecture Diagram

```mermaid
flowchart TB
    subgraph INPUT["📥 Input — FSx for NetApp ONTAP"]
        DATA["工厂数据<br/>.csv (传感器日志)<br/>.jpeg/.png (检查图像)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Trigger"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC内执行<br/>• S3 AP 文件检测<br/>• .csv/.jpeg/.png 过滤<br/>• Manifest 生成 (类型分离)"]
        TR["2️⃣ Transform Lambda<br/>• 通过 S3 AP 获取 CSV<br/>• 数据标准化·类型转换<br/>• CSV → Parquet 转换<br/>• S3 输出 (日期分区)"]
        IMG["3️⃣ Image Analysis Lambda<br/>• 通过 S3 AP 获取图像<br/>• Rekognition DetectLabels<br/>• 缺陷标签检测<br/>• 置信度评分判定<br/>• 手动审核标志设置"]
        ATH["4️⃣ Athena Analysis Lambda<br/>• Glue Data Catalog 更新<br/>• Athena SQL 查询执行<br/>• 基于阈值的异常值检测<br/>• 质量统计汇总"]
    end

    subgraph OUTPUT["📤 Output — S3 Bucket"]
        PARQUET["parquet/*.parquet<br/>已转换传感器数据"]
        ATHENA["athena-results/*.csv<br/>异常值检测·统计结果"]
        IMGOUT["image-results/*.json<br/>缺陷检测结果"]
    end

    subgraph NOTIFY["📧 Notification"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(异常检测时)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> TR
    DISC --> IMG
    TR --> ATH
    TR --> PARQUET
    ATH --> ATHENA
    IMG --> IMGOUT
    IMG --> SNS
    ATH --> SNS
```

---

## Data Flow Detail

### Input
| 项目 | 说明 |
|------|-------------|
| **Source** | FSx for NetApp ONTAP volume |
| **File Types** | .csv (传感器日志), .jpeg/.jpg/.png (质量检查图像) |
| **Access Method** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Read Strategy** | 获取完整文件（转换·分析所需） |

### Processing
| 步骤 | 服务 | 功能 |
|------|---------|----------|
| Discovery | Lambda (VPC) | 通过 S3 AP 检测传感器日志·图像文件，按类型生成 Manifest |
| Transform | Lambda | CSV → Parquet 转换，数据标准化（时间戳统一、单位转换） |
| Image Analysis | Lambda + Rekognition | 使用 DetectLabels 进行缺陷检测，基于置信度评分的分级判定 |
| Athena Analysis | Lambda + Glue + Athena | 使用 SQL 进行基于阈值的异常值检测，质量统计汇总 |

### Output
| 产物 | 格式 | 说明 |
|----------|--------|-------------|
| Parquet Data | `parquet/YYYY/MM/DD/{stem}.parquet` | 已转换传感器数据 |
| Athena Results | `athena-results/{id}.csv` | 异常值检测结果·质量统计 |
| Image Results | `image-results/YYYY/MM/DD/{stem}_analysis.json` | Rekognition 缺陷检测结果 |
| SNS Notification | Email | 异常检测警报（阈值超标·缺陷检测时） |

---

## Key Design Decisions

1. **S3 AP over NFS** — Lambda 无需 NFS 挂载，在不改变现有 PLC → 文件服务器流程的情况下添加分析功能
2. **CSV → Parquet 转换** — 通过列式存储格式大幅提升 Athena 查询性能（压缩率·扫描量减少）
3. **Discovery 中的类型分离** — 传感器日志和检查图像通过不同路径并行处理，提升吞吐量
4. **Rekognition 的分级判定** — 基于置信度评分的 3 级判定（自动合格 ≥90% / 手动审核 50-90% / 自动不合格 <50%）
5. **基于阈值的异常检测** — 通过 Athena SQL 灵活设置阈值（温度 >80°C、振动 >5mm/s 等）
6. **基于轮询** — 由于 S3 AP 不支持事件通知，采用定期调度执行

---

## AWS Services Used

| 服务 | 角色 |
|---------|------|
| FSx for NetApp ONTAP | 工厂文件存储（传感器日志·检查图像保存） |
| S3 Access Points | 对 ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 定期触发器 |
| Step Functions | 工作流编排（支持并行路径） |
| Lambda | 计算（Discovery, Transform, Image Analysis, Athena Analysis） |
| Amazon Rekognition | 质量检查图像的缺陷检测 (DetectLabels) |
| Glue Data Catalog | Parquet 数据的架构管理 |
| Amazon Athena | 基于 SQL 的异常值检测·质量统计汇总 |
| SNS | 异常检测警报通知 |
| Secrets Manager | ONTAP REST API 凭证管理 |
| CloudWatch + X-Ray | 可观测性 |
