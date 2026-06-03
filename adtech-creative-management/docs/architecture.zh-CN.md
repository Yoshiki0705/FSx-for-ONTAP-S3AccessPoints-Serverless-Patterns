# UC19: 广告·营销 / 创意资产管理 — 资产编目与品牌合规检查

🌐 **Language / 语言**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | 简体中文 | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | [Deutsch](architecture.de.md) | [Español](architecture.es.md)

## 端到端架构（输入 → 输出）

---

## 架构图

```mermaid
flowchart TB
    subgraph INPUT["📥 输入 — FSx for ONTAP"]
        DATA["创意资产<br/>.jpeg/.png/.tiff（图像）<br/>.mp4/.mov（视频）<br/>.psd（设计文件）"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ 触发器"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — 每天 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions 工作流"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC 内执行<br/>• 媒体文件检测<br/>• 格式 + 大小过滤（5 GB 限制）<br/>• Manifest 生成"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• 通过 S3 AP 获取资产<br/>• Rekognition DetectLabels（80% 置信度阈值）<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• 每资产最多生成 50 个标签"]
        TC["3️⃣ Text Compliance Lambda<br/>• Textract 文本提取（us-east-1 跨区域）<br/>• 加载品牌术语指南 JSON<br/>• Bedrock InvokeModel — 品牌合规检查<br/>• 结果：compliant / non-compliant + 匹配术语列表"]
        RL["4️⃣ Report Lambda<br/>• 资产目录生成（JSON + CSV）<br/>• 审核违规标记（requires-review）<br/>• CloudWatch EMF Metrics 发送<br/>• SNS 通知"]
    end

    subgraph OUTPUT["📤 输出 — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json"]
        CSV["reports/{execution-id}/asset-catalog.csv"]
        FLAGGED["reports/{execution-id}/flagged-assets.json"]
        ERROUT["errors/{execution-id}/{filename}.json"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    RL --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
```

---

## 使用的 AWS 服务

| 服务 | 角色 |
|------|------|
| FSx for ONTAP | 创意资产存储 |
| S3 Access Points | ONTAP 卷的无服务器访问 |
| EventBridge Scheduler | 每日触发（00:00 UTC） |
| Step Functions | 工作流编排（并行 Map State） |
| Lambda | 计算（Discovery、Visual Analyzer、Text Compliance、Report） |
| Amazon Rekognition | 视觉分析（标签、审核、文本检测） |
| Amazon Textract | 文本叠加提取（us-east-1 跨区域） |
| Amazon Bedrock | 品牌指南合规检查推理（Claude / Nova） |
| SNS | 审核违规警报通知 |
| CloudWatch + X-Ray | 可观测性（EMF Metrics、追踪） |
