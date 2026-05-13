# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

基于 Amazon FSx for NetApp ONTAP S3 Access Points 的行业专属无服务器自动化模式集合。

> **本仓库的定位**: 这是一个「用于学习设计决策的参考实现」。部分用例已在 AWS 环境中完成 E2E 验证，其他用例也已完成 CloudFormation 部署、共享 Discovery Lambda 及关键组件的功能验证。本仓库以从 PoC 到生产环境的渐进式应用为目标，通过具体代码展示成本优化、安全性和错误处理的设计决策。

## 相关文章

本仓库是以下文章中所述架构的实现示例：

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

文章解释架构设计思想和权衡取舍，本仓库提供具体的、可复用的实现模式。

## 概述

本仓库提供 **5 种行业专属模式**，通过 **S3 Access Points** 对存储在 FSx for NetApp ONTAP 上的企业数据进行无服务器处理。

> 以下将 FSx for ONTAP S3 Access Points 简称为 **S3 AP**。

每个用例都是独立的 CloudFormation 模板，共享模块（ONTAP REST API 客户端、FSx 辅助工具、S3 AP 辅助工具）位于 `shared/` 目录中供复用。

### 主要特性

- **轮询架构**: 由于 S3 AP 不支持 `GetBucketNotificationConfiguration`，采用 EventBridge Scheduler + Step Functions 定期执行
- **事件驱动路径（Phase 10）**: 通过 ONTAP FPolicy → ECS Fargate → SQS → EventBridge 实现 NFSv3 文件事件检测（[快速入门](docs/event-driven/README.md)）
- **SMB (CIFS) 支持已验证**: FPolicy E2E 已通过 NFSv3 和 SMB 协议测试 — SMB 需要加入 AD 的 SVM（[SMB 设置](docs/event-driven/README.md#smb-cifs-テスト手順)）
- **共享模块分离**: OntapClient / FsxHelper / S3ApHelper 在所有用例中复用
- **CloudFormation / SAM Transform 架构**: 每个用例都是独立的 CloudFormation 模板（使用 SAM Transform）
- **安全优先**: 默认启用 TLS 验证、最小权限 IAM、KMS 加密
- **成本优化**: 高成本常驻资源（Interface VPC Endpoints 等）为可选项

## 架构

```mermaid
graph TB
    subgraph "Scheduling Layer"
        EBS[EventBridge Scheduler<br/>cron/rate expressions]
        KDS[Kinesis Data Streams<br/>Near-real-time detection<br/>UC11 opt-in]
    end

    subgraph "Orchestration Layer"
        SFN[Step Functions<br/>State Machine]
    end

    subgraph "Compute Layer"
        DL[Discovery Lambda<br/>Object Detection<br/>Within VPC]
        PL[Processing Lambda<br/>AI/ML Processing<br/>Map State parallel]
        RL[Report Lambda<br/>Report Generation & Notification]
    end

    subgraph "Data Sources"
        FSXN[FSx for NetApp ONTAP<br/>Volume]
        S3AP[S3 Access Point<br/>ListObjectsV2 / GetObject /<br/>Range / PutObject]
        ONTAP_API[ONTAP REST API<br/>ACL / Volume Metadata]
    end

    subgraph "AI/ML Services"
        BEDROCK[Amazon Bedrock<br/>Nova / Claude]
        TEXTRACT[Amazon Textract<br/>OCR ⚠️ Cross-Region]
        COMPREHEND[Amazon Comprehend /<br/>Comprehend Medical ⚠️]
        REKOGNITION[Amazon Rekognition<br/>Image Analysis]
        SAGEMAKER[Amazon SageMaker<br/>Batch / Real-time /<br/>Serverless Inference<br/>UC9 opt-in]
    end

    subgraph "Data Analytics"
        GLUE[AWS Glue<br/>Data Catalog]
        ATHENA[Amazon Athena<br/>SQL Analytics]
    end

    subgraph "Storage & State Management"
        S3OUT[S3 Output Bucket<br/>SSE-KMS Encryption]
        DDB[DynamoDB<br/>Task Token Store<br/>UC9 opt-in]
        SM[Secrets Manager]
    end

    subgraph "Notifications"
        SNS[SNS Topic<br/>Email / Slack]
    end

    subgraph "Observability (Phase 3+)"
        XRAY[AWS X-Ray<br/>Distributed Tracing]
        CW[CloudWatch<br/>EMF Metrics /<br/>Dashboards]
    end

    subgraph "VPC Endpoints (Optional)"
        VPCE_S3[S3 Gateway EP<br/>Free]
        VPCE_IF[Interface EPs<br/>Secrets Manager / FSx /<br/>CloudWatch / SNS]
    end

    EBS -->|Periodic trigger| SFN
    KDS -->|Real-time| SFN
    SFN -->|Step 1| DL
    SFN -->|Step 2 Map| PL
    SFN -->|Step 3| RL

    DL -->|ListObjectsV2| S3AP
    DL -->|REST API| ONTAP_API
    PL -->|GetObject / Range| S3AP
    PL -->|PutObject| S3OUT
    PL --> BEDROCK
    PL --> TEXTRACT
    PL --> COMPREHEND
    PL --> REKOGNITION
    PL --> SAGEMAKER
    PL --> GLUE
    PL --> ATHENA

    S3AP -.->|Exposes| FSXN
    GLUE -.-> ATHENA

    DL --> VPCE_S3
    DL --> VPCE_IF --> SM
    RL --> SNS

    SFN --> XRAY
    DL --> CW
    PL --> CW
    RL --> CW

    SAGEMAKER -.-> DDB
```

> 该图展示了涵盖所有阶段（Phase 1-5）服务的完整架构。SageMaker、Kinesis 和 DynamoDB 通过 CloudFormation Conditions 进行选择性控制，未启用时不会产生额外费用。对于 PoC/演示用途，也可以选择 VPC 外部的 Lambda 配置。

### 工作流概述

```
EventBridge Scheduler (定期执行)
  └─→ Step Functions State Machine
       ├─→ Discovery Lambda: 从 S3 AP 获取对象列表 → 生成 Manifest
       ├─→ Map State (并行处理): 使用 AI/ML 服务处理各对象
       └─→ Report/Notification: 生成结果报告 → SNS 通知
```

## 用例列表

### Phase 1 (UC1–UC5)

| # | 目录 | 行业 | 模式 | 使用的 AI/ML 服务 | ap-northeast-1 验证状态 |
|---|------|------|------|-----------------|----------------------|
| UC1 | `legal-compliance/` | 法务合规 | 文件服务器审计与数据治理 | Athena, Bedrock | ✅ E2E 成功 |
| UC2 | `financial-idp/` | 金融保险 | 合同/发票自动处理 (IDP) | Textract ⚠️, Comprehend, Bedrock | ⚠️ 东京不支持（使用对应区域） |
| UC3 | `manufacturing-analytics/` | 制造业 | IoT 传感器日志与质量检测图像分析 | Athena, Rekognition | ✅ E2E 成功 |
| UC4 | `media-vfx/` | 媒体 | VFX 渲染管线 | Rekognition, Deadline Cloud | ⚠️ Deadline Cloud 需配置 |
| UC5 | `healthcare-dicom/` | 医疗 | DICOM 图像自动分类与脱敏 | Rekognition, Comprehend Medical ⚠️ | ⚠️ 东京不支持（使用对应区域） |

### Phase 2 (UC6–UC14)

| # | 目录 | 行业 | 模式 | 使用的 AI/ML 服务 | ap-northeast-1 验证状态 |
|---|------|------|------|-----------------|----------------------|
| UC6 | `semiconductor-eda/` | 半导体 / EDA | GDS/OASIS 验证・元数据提取・DRC 汇总 | Athena, Bedrock | ✅ 测试通过 |
| UC7 | `genomics-pipeline/` | 基因组学 | FASTQ/VCF 质量检查・变异调用汇总 | Athena, Bedrock, Comprehend Medical ⚠️ | ⚠️ Cross-Region (us-east-1) |
| UC8 | `energy-seismic/` | 能源 | SEG-Y 元数据提取・井日志异常检测 | Athena, Bedrock, Rekognition | ✅ 测试通过 |
| UC9 | `autonomous-driving/` | 自动驾驶 / ADAS | 视频/LiDAR 预处理・质量检查・标注 | Rekognition, Bedrock, SageMaker | ✅ 测试通过 |
| UC10 | `construction-bim/` | 建筑 / AEC | BIM 版本管理・图纸 OCR・安全合规 | Textract ⚠️, Bedrock, Rekognition | ⚠️ Cross-Region (us-east-1) |
| UC11 | `retail-catalog/` | 零售 / 电商 | 商品图像标签・目录元数据生成 | Rekognition, Bedrock | ✅ 测试通过 |
| UC12 | `logistics-ocr/` | 物流 | 运单 OCR・仓库库存图像分析 | Textract ⚠️, Rekognition, Bedrock | ⚠️ Cross-Region (us-east-1) |
| UC13 | `education-research/` | 教育 / 研究 | 论文 PDF 分类・引用网络分析 | Textract ⚠️, Comprehend, Bedrock | ⚠️ Cross-Region (us-east-1) |
| UC14 | `insurance-claims/` | 保险 | 事故照片损害评估・估价单 OCR・理赔报告 | Rekognition, Textract ⚠️, Bedrock | ⚠️ Cross-Region (us-east-1) |

> **区域限制**: Amazon Textract 和 Amazon Comprehend Medical 在 ap-northeast-1（东京）不可用。Phase 2 UC（UC7、UC10、UC12、UC13、UC14）通过 Cross_Region_Client 将 API 调用路由到 us-east-1。Rekognition、Comprehend、Bedrock、Athena 在 ap-northeast-1 可用。
> 
> 参考: [Textract 支持区域](https://docs.aws.amazon.com/general/latest/gr/textract.html) | [Comprehend Medical 支持区域](https://docs.aws.amazon.com/general/latest/gr/comprehend-med.html)

### Phase 7 (UC15–UC17) 公共部门扩展

| # | 目录 | 行业 | 模式 | AI/ML 服务 | ap-northeast-1 验证状态 |
|---|------|------|------|-----------|-----------------------|
| UC15 | `defense-satellite/` | 国防/太空 | 卫星图像分析（对象检测、变化检测、警报）| Rekognition, SageMaker（可选）, Bedrock | ✅ 代码+测试完成，AWS 已验证 |
| UC16 | `government-archives/` | 政府 | 公文档案·FOIA（OCR、分类、编辑、20 天期限跟踪）| Textract ⚠️, Comprehend, Bedrock, OpenSearch（可选）| ✅ 代码+测试完成，AWS 已验证 |
| UC17 | `smart-city-geospatial/` | 智慧城市 | 地理空间分析（CRS 归一化、土地利用、风险映射、规划报告）| Rekognition, SageMaker（可选）, Bedrock (Nova Lite) | ✅ 代码+测试完成，AWS 已验证 |

> **公共部门合规性**: UC15 针对 DoD CC SRG / CSfC / FedRAMP High（GovCloud 迁移），UC16 针对 NARA / FOIA Section 552 / Section 508，UC17 针对 INSPIRE 指令 / OGC 标准。

## UI/UX 截图 (最终用户 / 员工 / 负责人视图)

每个 UC 的 **最终用户、员工、负责人在日常工作中实际看到的 UI/UX 界面**
在各 UC 的 README 和 demo-guide 中刊载。Step Functions 工作流图等技术人员视图
集中在各 phase 的验证结果文档 (`docs/verification-results-phase*.md`) 中。

不仅限于 Public Sector (UC15/16/17)，所有行业的 UC 采用相同方针:

- **担当人视角**: 在 S3 控制台确认输出物、阅读 Bedrock 报告、接收 SNS 邮件、
  在 DynamoDB 检索历史等日常业务界面
- **技术人员视角除外**: CloudFormation 堆栈事件、Lambda 日志、Step Functions 图
  (工作流可视化目的除外) 保留在 `verification-results-*.md` 中

| UC | 行业 | 截图数 | 主要内容 | 位置 |
|----|------|--------|---------|------|
| UC1 | 法务·合规 | 1 | Step Functions 图 (审计负责人工作流可视化) | [`legal-compliance/docs/demo-guide.zh-CN.md`](legal-compliance/docs/demo-guide.zh-CN.md) |
| UC2 | 金融·IDP | 1 | Step Functions 图 (发票处理负责人工作流可视化) | [`financial-idp/docs/demo-guide.zh-CN.md`](financial-idp/docs/demo-guide.zh-CN.md) |
| UC3 | 制造·分析 | 1 | Step Functions 图 (质量管理负责人工作流可视化) | [`manufacturing-analytics/docs/demo-guide.zh-CN.md`](manufacturing-analytics/docs/demo-guide.zh-CN.md) |
| UC4 | 媒体·VFX | 未刊载 | (渲染负责人界面, 计划拍摄) | [`media-vfx/docs/demo-guide.zh-CN.md`](media-vfx/docs/demo-guide.zh-CN.md) |
| UC5 | 医疗·DICOM | 1 | Step Functions 图 (医疗信息管理员工作流可视化) | [`healthcare-dicom/docs/demo-guide.zh-CN.md`](healthcare-dicom/docs/demo-guide.zh-CN.md) |
| UC6 | 半导体·EDA | 4 | FSx Volumes / S3 输出桶 / Athena 查询结果 / Bedrock 设计审查报告 | [`semiconductor-eda/docs/demo-guide.zh-CN.md`](semiconductor-eda/docs/demo-guide.zh-CN.md) |
| UC7 | 基因组学流水线 | 1 | Step Functions 图 (研究者工作流可视化) | [`genomics-pipeline/docs/demo-guide.zh-CN.md`](genomics-pipeline/docs/demo-guide.zh-CN.md) |
| UC8 | 能源·地震勘探 | 1 | Step Functions 图 (地质解析负责人工作流可视化) | [`energy-seismic/docs/demo-guide.zh-CN.md`](energy-seismic/docs/demo-guide.zh-CN.md) |
| UC9 | 自动驾驶 | 未刊载 | (ADAS 分析负责人界面, 计划拍摄) | [`autonomous-driving/docs/demo-guide.zh-CN.md`](autonomous-driving/docs/demo-guide.zh-CN.md) |
| UC10 | 建筑·BIM | 1 | Step Functions 图 (BIM 管理员 / 安全负责人工作流可视化) | [`construction-bim/docs/demo-guide.zh-CN.md`](construction-bim/docs/demo-guide.zh-CN.md) |
| UC11 | 零售·目录 | 2 | 产品标签结果 / S3 输出桶 (EC 负责人用) | [`retail-catalog/docs/demo-guide.zh-CN.md`](retail-catalog/docs/demo-guide.zh-CN.md) |
| UC12 | 物流·OCR | 1 | Step Functions 图 (配送负责人工作流可视化) | [`logistics-ocr/docs/demo-guide.zh-CN.md`](logistics-ocr/docs/demo-guide.zh-CN.md) |
| UC13 | 教育·研究 | 1 | Step Functions 图 (研究事务负责人工作流可视化) | [`education-research/docs/demo-guide.zh-CN.md`](education-research/docs/demo-guide.zh-CN.md) |
| UC14 | 保险 | 2 | 理赔报告 / S3 输出桶 (保险理算员用) | [`insurance-claims/docs/demo-guide.zh-CN.md`](insurance-claims/docs/demo-guide.zh-CN.md) |
| UC15 | 国防·卫星图像 (Public Sector) | 4 | S3 上传 / 输出 / SNS 邮件 / JSON 成果物 (分析负责人用) | [`defense-satellite/README.md`](defense-satellite/README.md) |
| UC16 | 政府·FOIA (Public Sector) | 5 | 上传 / 编辑预览 / 元数据 / FOIA 提醒邮件 / DynamoDB 保留历史 (公文档负责人用) | [`government-archives/README.md`](government-archives/README.md) |
| UC17 | 智慧城市 (Public Sector) | 5 | GIS 上传 / Bedrock 报告 / 风险地图 / 土地利用分布 / 时序历史 (城市规划负责人用) | [`smart-city-geospatial/README.md`](smart-city-geospatial/README.md) |

**通用截图** (跨行业通用视图, `docs/screenshots/masked/common/`):
- `fsx-s3ap-detail.png` — FSxN S3 Access Point 详情视图 (存储管理员参考)
- `s3ap-list.png` — S3 Access Points 列表 (IT 管理员参考)

**按 Phase 视图** (`docs/screenshots/masked/phase{1..7}/`):
- Phase 1-6b: 基础设施构建 / 功能添加时的技术人员视图
- Phase 7: UC15/16/17 公共 FSx S3 Access Points 视图等

行业映射表 (8 语言): [`docs/screenshots/uc-industry-mapping.md`](docs/screenshots/uc-industry-mapping.md).
添加工作流: [`docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md`](docs/screenshots/SCREENSHOT_ADDITION_WORKFLOW.md).

> 所有文档均提供 8 种语言版本。
## AWS 规格约束及解决方案

### 输出目标选择 (OutputDestination 参数)

每个 UC 的 CloudFormation 模板都包含 `OutputDestination` 参数来选择
AI/ML 工件的写入目标（已在 UC9/10/11/12/14 实现,
其他 UC 由 Pattern A 或 Pattern C 覆盖 - 参见下面的 Pattern 表):

- **`STANDARD_S3`** (默认): 写入新的 S3 存储桶 (现有行为)
- **`FSXN_S3AP`**: 通过 S3 Access Point 将结果写回同一个 FSx for NetApp ONTAP 卷
  (**"no data movement" 模式**, 使 SMB/NFS 用户能够在现有目录结构中
  查看 AI 工件)

```bash
# 以 FSXN_S3AP 模式部署
aws cloudformation deploy \
  --template-file retail-catalog/template-deploy.yaml \
  --stack-name fsxn-retail-catalog-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    ... (其他必需参数)
```

### FSxN S3 Access Points 的 AWS 规格约束

FSxN S3 Access Points 仅支持 S3 API 的一部分
(参见 [Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html))。
由于以下约束,某些功能需要使用标准 S3 存储桶:

| AWS 规格约束 | 影响 | 项目解决方案 | 功能改进请求 (FR) |
|---|---|---|---|
| Athena 查询结果输出位置无法指定 S3AP<br>(Athena 无法 write back 到 S3AP) | UC6/7/8/13 的 Athena 结果需要标准 S3 | 每个模板创建专用于 Athena 结果的 S3 存储桶 | [FR-1](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-1) |
| S3AP 不发出 S3 Event Notifications / EventBridge 事件 | 无法实现事件驱动的工作流 | EventBridge Scheduler + Discovery Lambda 轮询方式 | [FR-2](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-2) |
| S3AP 不支持 Object Lifecycle 策略 | 7 年保留 (UC1 法务), 永久保留 (UC16 政府档案) 等自动化困难 | 定期删除的 Lambda 清理器 (未实现, 待办事项) | [FR-3](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-3) |
| S3AP 不支持 Object Versioning / Presigned URL | 文档版本管理, 外部审计员的限时共享不可能 | DynamoDB 用于版本管理, 标准 S3 复制 + Presign | [FR-4](docs/aws-feature-requests/fsxn-s3ap-improvements.md#fr-4) |
| 5GB 上传大小限制 | 大型二进制文件 (4K 视频, 未压缩 GeoTIFF 等) | `shared.s3ap_helper.multipart_upload()` 支持到 5GB | (接受的 AWS 规格) |
| 仅支持 SSE-FSX (不支持 SSE-KMS) | 无法使用自定义 KMS 密钥加密 | 通过 FSx 卷级别的 KMS 配置进行加密 | (接受的 AWS 规格) |

全部 4 个功能改进请求 (FR-1 ~ FR-4) 的详细内容和业务影响整理在
[`docs/aws-feature-requests/fsxn-s3ap-improvements.md`](docs/aws-feature-requests/fsxn-s3ap-improvements.md)
中。

3 种输出模式 (Pattern A/B/C) 的详细比较请参阅
[`docs/output-destination-patterns.md`](docs/output-destination-patterns.md)。

### 每个 UC 的输出目标约束

17 个 UC 分为 3 种输出模式:

- **🟢 UC1-5** (Pattern A, 2026-05-11 更新): `S3AccessPointOutputAlias` (legacy, optional) + 新增的 `OutputDestination` / `OutputS3APAlias` / `OutputS3APPrefix` 支持。默认 `OutputDestination=FSXN_S3AP` 保持现有行为
- **🟢🆕 UC9/10/11/12/14** (Pattern B, 2026-05-10 实现): `OutputDestination` 切换机制 (STANDARD_S3 ⇄ FSXN_S3AP)。默认 `OutputDestination=STANDARD_S3`。UC11/14 已在 AWS 上验证, UC9/10/12 仅完成单元测试
- **🟡 UC6/7/8/13**: 当前仅为 `OUTPUT_BUCKET` (固定为标准 S3)。Athena 结果在规格上需要标准 S3, 因此 `OutputDestination` 应用是部分性的
- **🟢 UC15-17**: Pattern A (write back 到 FSxN S3AP, Phase 7 的一部分)

| UC | 输入 | 输出 | 选择机制 | 备注 |
|----|------|------|----------|------|
| UC1 legal-compliance | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 合同元数据 / 审计日志 |
| UC2 financial-idp | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 发票 OCR 结果 |
| UC3 manufacturing-analytics | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 检查结果 / 异常检测 |
| UC4 media-vfx | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | 渲染元数据 |
| UC5 healthcare-dicom | S3AP | S3AP (现有) | ✅ `OutputDestination` + legacy `S3AccessPointOutputAlias` | DICOM 元数据 / 匿名化结果 |
| UC6 semiconductor-eda | S3AP | **标准 S3** | ⚠️ 未实现 | Bedrock/Athena 结果 (Athena 在规格上需要标准 S3) |
| UC7 genomics-pipeline | S3AP | **标准 S3** | ⚠️ 未实现 | Glue/Athena 结果 (Athena 在规格上需要标准 S3) |
| UC8 energy-seismic | S3AP | **标准 S3** | ⚠️ 未实现 | Glue/Athena 结果 (Athena 在规格上需要标准 S3) |
| UC9 autonomous-driving | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | ADAS 分析结果 |
| UC10 construction-bim | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | BIM 元数据 / 安全合规报告 |
| **UC11 retail-catalog** | S3AP | **可选择** | ✅ `OutputDestination` | AWS 实证完成 2026-05-10 |
| UC12 logistics-ocr | S3AP | **可选择** 🆕 | ✅ `OutputDestination` | 配送运单 OCR |
| UC13 education-research | S3AP | **标准 S3** | ⚠️ 未实现 | 包括 Athena 结果 (Athena 在规格上需要标准 S3) |
| **UC14 insurance-claims** | S3AP | **可选择** | ✅ `OutputDestination` | AWS 实证完成 2026-05-10 |
| UC15 defense-satellite | S3AP | S3AP | 现有模式 | 对象检测 / 变化检测结果 |
| UC16 government-archives | S3AP | S3AP | 现有模式 | FOIA 编辑结果 / 元数据 |
| UC17 smart-city-geospatial | S3AP | S3AP | 现有模式 | GIS 分析结果 / 风险地图 |

**路线图**:
- ~~Part B: UC1-5 现有 `S3AccessPointOutputAlias` 模式的文档整理~~ ✅ 完成 (`docs/output-destination-patterns.md`)
- UC6/7/8/13 的 Athena 输出在规格上需要标准 S3, 但 Bedrock 报告等非 Athena 工件可以通过 `OutputDestination=FSXN_S3AP` write back 的选项 (Pattern C → Pattern B 混合, 未来扩展)
- UC9/10/12 的 AWS 实际部署验证 (单元测试已完成, 部署未实施)
## 区域选择指南

本模式集在 **ap-northeast-1（东京）** 进行了验证，但可以部署到任何所需服务可用的 AWS 区域。

### 部署前检查清单

1. 在 [AWS Regional Services List](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/) 确认服务可用性
2. 确认 Phase 3 服务：
   - **Kinesis Data Streams**：几乎所有区域可用（分片定价因区域而异）
   - **SageMaker Batch Transform**：实例类型可用性因区域而异
   - **X-Ray / CloudWatch EMF**：几乎所有区域可用
3. 确认 Cross-Region 目标服务（Textract、Comprehend Medical）的目标区域

详情请参阅[区域兼容性矩阵](docs/region-compatibility.md)。

### Phase 3 功能概要

| 功能 | 说明 | 目标 UC |
|------|------|---------|
| Kinesis 流式处理 | 近实时文件变更检测和处理 | UC11（可选启用） |
| SageMaker Batch Transform | 点云分割推理（Callback Pattern） | UC9（可选启用） |
| X-Ray 追踪 | 分布式追踪实现执行路径可视化 | 全部 14 UC |
| CloudWatch EMF | 结构化指标输出（FilesProcessed、Duration、Errors） | 全部 14 UC |
| 可观测性仪表板 | 全 UC 横跨指标集中展示 | 共用 |
| 告警自动化 | 基于错误率阈值的 SNS 通知 | 共用 |

详情请参阅[流式处理 vs 轮询选择指南](docs/streaming-vs-polling-guide-zh-CN.md)。

### Phase 4 功能概要

| 功能 | 说明 | 目标 UC |
|------|------|---------|
| DynamoDB Task Token Store | SageMaker Callback Pattern 的生产安全 Token 管理（Correlation ID 方式） | UC9（可选启用） |
| Real-time Inference Endpoint | 通过 SageMaker Real-time Endpoint 实现低延迟推理 | UC9（可选启用） |
| A/B Testing | 通过 Multi-Variant Endpoint 进行模型版本比较 | UC9（可选启用） |
| Model Registry | 通过 SageMaker Model Registry 进行模型生命周期管理 | UC9（可选启用） |
| Multi-Account Deployment | 通过 StackSets / Cross-Account IAM / S3 AP 策略实现多账户支持 | 全部 UC（提供模板） |
| Event-Driven Prototype | S3 Event Notifications → EventBridge → Step Functions 管道 | 原型 |

Phase 4 的所有功能通过 CloudFormation Conditions 进行可选控制，未启用时不会产生额外费用。

详情请参阅以下文档：
- [推理成本比较指南](docs/inference-cost-comparison.md)
- [Model Registry 指南](docs/model-registry-guide.md)
- [Multi-Account PoC 结果](docs/multi-account/poc-results.md)
- [Event-Driven 架构设计](docs/event-driven/architecture-design.md)

### Phase 5 功能概要

| 功能 | 说明 | 目标 UC |
|------|------|---------|
| SageMaker Serverless Inference | 第3路由选项（Batch / Real-time / Serverless 三路选择） | UC9（可选启用） |
| Scheduled Scaling | 基于工作时间的 SageMaker Endpoint 自动扩缩 | UC9（可选启用） |
| CloudWatch Billing Alarms | Warning / Critical / Emergency 三级成本告警 | 通用（可选启用） |
| Auto-Stop Lambda | 自动检测并缩减闲置 SageMaker Endpoint | 通用（可选启用） |
| CI/CD Pipeline | GitHub Actions 工作流（cfn-lint → pytest → cfn-guard → Bandit → deploy） | 全部 UC |
| Multi-Region | DynamoDB Global Tables + CrossRegionClient 故障转移 | 通用（可选启用） |
| Disaster Recovery | DR Tier 1/2/3 定义、故障转移运行手册 | 通用（设计文档） |

Phase 5 的所有功能同样通过 CloudFormation Conditions 进行可选控制，未启用时不会产生额外费用。

详情请参阅以下文档：
- [Serverless Inference 冷启动特性](docs/serverless-inference-cold-start.md)
- [成本优化最佳实践指南](docs/cost-optimization-guide.md)
- [CI/CD 指南](docs/ci-cd-guide.md)
- [Multi-Region Step Functions 设计](docs/multi-region/step-functions-design.md)
- [Disaster Recovery 指南](docs/multi-region/disaster-recovery.md)

### 截图

> 以下为验证环境中的截图示例。环境特定信息（账户 ID 等）已进行脱敏处理。

#### 全部 5 个 UC 的 Step Functions 部署与执行确认

![Step Functions 全部工作流](docs/screenshots/masked/phase1/phase1-step-functions-all-succeeded.png)

> UC1 和 UC3 已完成完整的 E2E 验证，UC2、UC4 和 UC5 已完成 CloudFormation 部署和主要组件的功能验证。使用有区域限制的 AI/ML 服务（Textract、Comprehend Medical）时，需要跨区域调用至支持区域，请确认数据驻留和合规要求。

#### Phase 2: 全部 9 个 UC CloudFormation 部署・Step Functions 执行成功

![CloudFormation Phase 2 堆栈](docs/screenshots/masked/phase2/phase2-cloudformation-phase2-stacks.png)

> 全部 9 个堆栈（UC6–UC14）达到 CREATE_COMPLETE / UPDATE_COMPLETE。共 205 个资源。

![Step Functions Phase 2 工作流](docs/screenshots/masked/phase2/phase2-step-functions-phase2-all-workflows.png)

> 全部 9 个工作流已激活。投入测试数据后 E2E 执行全部 SUCCEEDED。

![UC6 执行 Graph View](docs/screenshots/masked/phase2/phase2-step-functions-uc6-execution-graph.png)

> UC6（半导体 EDA）Step Functions 执行详情。Discovery → ProcessObjects (Map) → DrcAggregation → ReportGeneration 全部状态成功。

![EventBridge Phase 2 调度](docs/screenshots/masked/phase2/phase2-eventbridge-phase2-schedules.png)

> 全部 9 个 UC 的 EventBridge Scheduler 调度（rate(1 hour)）已启用。

#### AI/ML 服务界面（Phase 1）

##### Amazon Bedrock — 模型目录

![Bedrock 模型目录](docs/screenshots/masked/phase1/phase1-bedrock-model-catalog.png)

##### Amazon Rekognition — 标签检测

![Rekognition 标签检测](docs/screenshots/masked/phase1/phase1-rekognition-label-detection.png)

##### Amazon Comprehend — 实体检测

![Comprehend 控制台](docs/screenshots/masked/phase1/phase1-comprehend-console.png)

#### AI/ML 服务界面（Phase 2）

##### Amazon Bedrock — 模型目录（UC6: 报告生成）

![Bedrock 模型目录 Phase 2](docs/screenshots/masked/phase2/phase2-bedrock-model-catalog.png)

> UC6（半导体 EDA）中使用 Nova Lite 模型生成 DRC 报告。

##### Amazon Athena — 查询执行历史（UC6: 元数据汇总）

![Athena 查询历史 Phase 2](docs/screenshots/masked/phase2/phase2-athena-query-history.png)

> UC6 的 Step Functions 工作流中执行 Athena 查询（cell_count, bbox, naming, invalid）。

##### Amazon Rekognition — 标签检测（UC11: 商品图片标记）

![Rekognition 标签检测 Phase 2](docs/screenshots/masked/phase2/phase2-rekognition-label-detection.png)

> UC11（零售目录）从商品图片中检测 15 个标签（Lighting 98.5%, Light 96.0%, Purple 92.0% 等）。

##### Amazon Textract — 文档 OCR（UC12: 配送单据读取）

![Textract 文档分析 Phase 2](docs/screenshots/masked/phase2/phase2-textract-analyze-document.png)

> UC12（物流 OCR）从配送单据 PDF 中提取文本。通过 Cross-Region（us-east-1）执行。

##### Amazon Comprehend Medical — 医疗实体检测（UC7: 基因组分析）

![Comprehend Medical 实时分析 Phase 2](docs/screenshots/masked/phase2/phase2-comprehend-medical-genomics-analysis.png)

> UC7（基因组管道）中使用 DetectEntitiesV2 API 从 VCF 分析结果中提取基因名（GC）。通过 Cross-Region（us-east-1）执行。

##### Lambda 函数列表（Phase 2）

![Lambda 函数列表 Phase 2](docs/screenshots/masked/phase2/phase2-lambda-phase2-functions.png)

> Phase 2 的全部 Lambda 函数（Discovery, Processing, Report 等）已成功部署。

#### Phase 3: 实时处理・SageMaker 集成・可观测性强化

##### Step Functions E2E 执行成功（UC11）

![Step Functions Phase 3 执行成功](docs/screenshots/masked/phase3/phase3-step-functions-uc11-succeeded.png)

> UC11 Step Functions 工作流 E2E 执行成功。Discovery → ImageTagging Map → CatalogMetadata Map → QualityCheck 全状态成功（8.974秒）。X-Ray 跟踪生成确认。

##### Kinesis Data Streams（UC11 流式模式）

![Kinesis Data Stream](docs/screenshots/masked/phase3/phase3-kinesis-stream-active.png)

> UC11 Kinesis Data Stream（1 分片，预置模式）处于活跃状态。显示监控指标。

##### DynamoDB 状态管理表（UC11 变更检测）

![DynamoDB State Tables](docs/screenshots/masked/phase3/phase3-dynamodb-state-tables.png)

> UC11 变更检测用 DynamoDB 表。streaming-state（状态管理）和 streaming-dead-letter（DLQ）两张表。

##### 可观测性堆栈

![X-Ray Traces](docs/screenshots/masked/phase3/phase3-xray-traces.png)

> X-Ray 跟踪。Stream Producer Lambda 1分钟间隔执行跟踪（全部 OK，延迟 7-11ms）。

![CloudWatch Dashboard](docs/screenshots/masked/phase3/phase3-cloudwatch-dashboard.png)

> 全 14 UC 横跨集中式 CloudWatch 仪表板。Step Functions 成功/失败、Lambda 错误率、EMF 自定义指标。

![CloudWatch Alarms](docs/screenshots/masked/phase3/phase3-cloudwatch-alarms.png)

> Phase 3 告警自动化。Step Functions 失败率、Lambda 错误率、Kinesis Iterator Age 阈值告警（全部 OK 状态）。

##### S3 Access Point 验证

![S3 AP Available](docs/screenshots/masked/phase3/phase3-s3ap-available.png)

> FSx for ONTAP S3 Access Point（fsxn-eda-s3ap）处于 Available 状态。通过 FSx 控制台卷 S3 选项卡确认。

#### Phase 4: 生产 SageMaker 集成、实时推理、多账户、事件驱动

##### DynamoDB Task Token Store

![DynamoDB Task Token Store](docs/screenshots/masked/phase4/phase4-dynamodb-task-token-store.png)

> DynamoDB Task Token Store 表。以 8 字符 hex Correlation ID 作为分区键存储 Task Token。TTL 已启用，PAY_PER_REQUEST 模式，GSI（TransformJobNameIndex）已配置。

##### SageMaker Real-time Endpoint（Multi-Variant A/B Testing）

![SageMaker Endpoint](docs/screenshots/masked/phase4/phase4-sagemaker-realtime-endpoint.png)

> SageMaker Real-time Inference Endpoint。Multi-Variant 配置（model-v1: 70%, model-v2: 30%）用于 A/B 测试。Auto Scaling 已配置。

##### Step Functions 工作流（Realtime/Batch 路由）

![Step Functions Phase 4](docs/screenshots/masked/phase4/phase4-step-functions-routing.png)

> UC9 Step Functions 工作流。Choice State 在 file_count < threshold 时路由到 Real-time Endpoint，否则路由到 Batch Transform。

##### Event-Driven Prototype — EventBridge Rule

![EventBridge Rule](docs/screenshots/masked/phase4/phase4-eventbridge-event-rule.png)

> Event-Driven Prototype EventBridge Rule。按 suffix (.jpg, .png) + prefix (products/) 过滤 S3 ObjectCreated 事件并触发 Step Functions。

##### Event-Driven Prototype — Step Functions 执行成功

![Event-Driven Step Functions](docs/screenshots/masked/phase4/phase4-event-driven-sfn-succeeded.png)

> Event-Driven Prototype Step Functions 执行成功。S3 PutObject → EventBridge → Step Functions → EventProcessor → LatencyReporter 所有状态成功。

##### CloudFormation Phase 4 堆栈

![CloudFormation Phase 4](docs/screenshots/masked/phase4/phase4-cloudformation-stacks.png)

> Phase 4 CloudFormation 堆栈。UC9 扩展（Task Token Store + Real-time Endpoint）及 Event-Driven Prototype CREATE_COMPLETE。

#### Phase 5: Serverless Inference·成本优化·Multi-Region

##### SageMaker Serverless Inference Endpoint

![SageMaker Serverless Endpoint 设置](docs/screenshots/masked/phase5/phase5-sagemaker-serverless-endpoint-settings.png)

> SageMaker Serverless Inference Endpoint 设置。内存 4096 MB，最大并发 5。

![SageMaker Serverless Endpoint Config](docs/screenshots/masked/phase5/phase5-sagemaker-serverless-endpoint-config.png)

> Serverless Endpoint Configuration 详情。无需预置，按需分配计算资源。

##### CloudWatch Billing Alarms（3 级成本告警）

![CloudWatch Billing Alarms](docs/screenshots/masked/phase5/phase5-cloudwatch-billing-alarms.png)

> Warning / Critical / Emergency 3 级 Billing Alarms。超阈值时 SNS 通知。

##### DynamoDB Global Table（Multi-Region）

![DynamoDB Global Table](docs/screenshots/masked/phase5/phase5-dynamodb-global-table.png)

> DynamoDB Global Table 配置。Multi-Region 复制已启用。

![DynamoDB Global Replicas](docs/screenshots/masked/phase5/phase5-dynamodb-global-replicas.png)

> Global Table 副本配置。多区域间数据同步。

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| IaC | CloudFormation (YAML) + SAM Transform |
| 计算 | AWS Lambda（生产: VPC 内 / PoC: VPC 外也可选择） |
| 编排 | AWS Step Functions |
| 调度 | Amazon EventBridge Scheduler |
| 存储 | FSx for ONTAP (S3 AP) + S3 输出桶 (SSE-KMS) |
| 通知 | Amazon SNS |
| 分析 | Amazon Athena + AWS Glue Data Catalog |
| AI/ML | Amazon Bedrock, Textract, Comprehend, Rekognition |
| 安全 | Secrets Manager, KMS, IAM 最小权限 |
| 测试 | pytest + Hypothesis (PBT), moto, cfn-lint, ruff |

## 前提条件

- **AWS 账户**: 有效的 AWS 账户和适当的 IAM 权限
- **FSx for NetApp ONTAP**: 已部署的文件系统
  - ONTAP 版本: 支持 S3 Access Points 的版本（已在 9.17.1P4D3 上验证）
  - 已关联 S3 Access Point 的 FSx for ONTAP 卷（network origin 根据用例选择。使用 Athena / Glue 时推荐 `internet`）
- **网络**: VPC、私有子网、路由表
- **Secrets Manager**: 预先注册 ONTAP REST API 凭证（格式: `{"username":"fsxadmin","password":"..."}`）
- **S3 存储桶**: 预先创建用于 Lambda 部署包的存储桶（例: `fsxn-s3ap-deploy-<account-id>`）
- **Python 3.12+**: 本地开发和测试用
- **AWS CLI v2**: 部署和管理用

### 准备命令

```bash
# 1. 创建部署用 S3 存储桶
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws s3 mb "s3://fsxn-s3ap-deploy-${ACCOUNT_ID}" --region $AWS_DEFAULT_REGION

# 2. 将 ONTAP 凭证注册到 Secrets Manager
aws secretsmanager create-secret \
  --name fsxn-ontap-credentials \
  --secret-string '{"username":"fsxadmin","password":"<your-ontap-password>"}' \
  --region $AWS_DEFAULT_REGION

# 3. 检查现有 S3 Gateway Endpoint（防止重复创建）
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" "Name=service-name,Values=com.amazonaws.${AWS_DEFAULT_REGION}.s3" \
  --query 'VpcEndpoints[*].{Id:VpcEndpointId,State:State}' \
  --output table
# → 如果有结果，使用 EnableS3GatewayEndpoint=false 部署
```

### Lambda 部署选择指南

| 用途 | 推荐部署 | 原因 |
|------|---------|------|
| 演示 / PoC | VPC 外 Lambda | 无需 VPC Endpoint，低成本、配置简单 |
| 生产 / 封闭网络要求 | VPC 内 Lambda | 可通过 PrivateLink 使用 Secrets Manager / FSx / SNS 等 |
| 使用 Athena / Glue 的 UC | S3 AP network origin: `internet` | 需要 AWS 托管服务的访问 |

### 从 VPC 内 Lambda 访问 S3 AP 的注意事项

> **UC1 部署验证（2026-05-03）中确认的重要事项**

- **S3 Gateway Endpoint 的路由表关联是必须的**: 如果未在 `RouteTableIds` 中指定私有子网的路由表 ID，VPC 内 Lambda 对 S3 / S3 AP 的访问将超时
- **确认 VPC DNS 解析**: 确保 VPC 的 `enableDnsSupport` / `enableDnsHostnames` 已启用
- **PoC / 演示环境建议在 VPC 外运行 Lambda**: 如果 S3 AP 的 network origin 为 `internet`，VPC 外 Lambda 可以正常访问。无需 VPC Endpoint，可降低成本并简化配置
- 详情请参阅[故障排除指南](docs/guides/troubleshooting-guide.md#6-lambda-vpc-内実行時の-s3-ap-タイムアウト)

### 所需 AWS 服务配额

| 服务 | 配额 | 推荐值 |
|------|------|--------|
| Lambda 并发执行数 | ConcurrentExecutions | 100 以上 |
| Step Functions 执行数 | StartExecution/秒 | 默认值 (25) |
| S3 Access Point | 每账户 AP 数 | 默认值 (10,000) |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns.git
cd FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. 运行测试

```bash
# 单元测试（含覆盖率）
pytest shared/tests/ --cov=shared --cov-report=term-missing -v

# 属性基测试
pytest shared/tests/test_properties.py -v

# 代码检查
ruff check .
ruff format --check .
```

### 4. 部署用例（示例: UC1 法务合规）

> ⚠️ **关于对现有环境影响的重要事项**
>
> 部署前请确认以下内容:
>
> | 参数 | 对现有环境的影响 | 确认方法 |
> |------|----------------|---------|
> | `VpcId` / `PrivateSubnetIds` | 将在指定的 VPC/子网中创建 Lambda ENI | `aws ec2 describe-network-interfaces --filters Name=group-id,Values=<sg-id>` |
> | `EnableS3GatewayEndpoint=true` | 将向 VPC 添加 S3 Gateway Endpoint。**如果同一 VPC 中已存在 S3 Gateway Endpoint，请设置为 `false`** | `aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc-id>` |
> | `PrivateRouteTableIds` | S3 Gateway Endpoint 将关联到路由表。不影响现有路由 | `aws ec2 describe-route-tables --route-table-ids <rtb-id>` |
> | `ScheduleExpression` | EventBridge Scheduler 将定期执行 Step Functions。**可在部署后禁用调度以避免不必要的执行** | AWS 控制台 → EventBridge → Schedules |
> | `NotificationEmail` | 将发送 SNS 订阅确认邮件 | 检查邮件收件箱 |
>
> **堆栈删除注意事项**:
> - 如果 S3 存储桶（Athena Results）中仍有对象，删除将失败。请先使用 `aws s3 rm s3://<bucket> --recursive` 清空
> - 启用版本控制的存储桶需要使用 `aws s3api delete-objects` 删除所有版本
> - VPC Endpoints 删除可能需要 5-15 分钟
> - Lambda ENI 释放可能需要时间，导致 Security Group 删除失败。请等待几分钟后重试

```bash
# 设置区域（通过环境变量管理）
export AWS_DEFAULT_REGION=us-east-1  # 推荐支持所有服务的区域

# Lambda 打包
./scripts/deploy_uc.sh legal-compliance package

# CloudFormation 部署
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-volume-ext-s3alias> \
    ParameterKey=S3AccessPointName,ParameterValue=<your-s3ap-name> \
    ParameterKey=S3AccessPointOutputAlias,ParameterValue=<your-output-volume-ext-s3alias> \
    ParameterKey=OntapSecretName,ParameterValue=<your-ontap-secret-name> \
    ParameterKey=OntapManagementIp,ParameterValue=<your-ontap-management-ip> \
    ParameterKey=SvmUuid,ParameterValue=<your-svm-uuid> \
    ParameterKey=VolumeUuid,ParameterValue=<your-volume-uuid> \
    ParameterKey=VpcId,ParameterValue=<your-vpc-id> \
    'ParameterKey=PrivateSubnetIds,ParameterValue=<subnet-1>,<subnet-2>' \
    'ParameterKey=PrivateRouteTableIds,ParameterValue=<rtb-1>,<rtb-2>' \
    ParameterKey=NotificationEmail,ParameterValue=<your-email@example.com> \
    ParameterKey=EnableVpcEndpoints,ParameterValue=true \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true
```

> **注意**: 请将 `<...>` 占位符替换为实际环境值。
>
> **关于 `EnableVpcEndpoints`**: Quick Start 中指定 `true` 以确保 VPC 内 Lambda 到 Secrets Manager / CloudWatch / SNS 的连通性。如果已有 Interface VPC Endpoints 或 NAT Gateway，可以指定 `false` 以降低成本。
> 
> **区域选择**: 推荐使用所有 AI/ML 服务均可用的 `us-east-1` 或 `us-west-2`。`ap-northeast-1` 不支持 Textract 和 Comprehend Medical（可通过跨区域调用解决）。详情请参阅[区域兼容性矩阵](docs/region-compatibility.md)。
>
> **VPC 连接性**: Discovery Lambda 部署在 VPC 内。访问 ONTAP REST API 和 S3 Access Point 需要 NAT Gateway 或 Interface VPC Endpoints。请设置 `EnableVpcEndpoints=true` 或使用现有的 NAT Gateway。

### 已验证环境

| 项目 | 值 |
|------|-----|
| AWS 区域 | ap-northeast-1 (东京) |
| FSx ONTAP 版本 | ONTAP 9.17.1P4D3 |
| FSx 配置 | SINGLE_AZ_1 |
| Python | 3.12 |
| 部署方式 | CloudFormation（使用 SAM Transform） |

已完成全部 5 个用例的 CloudFormation 堆栈部署和 Discovery Lambda 的功能验证。
详情请参阅[验证结果记录](docs/verification-results.md)。

## 成本结构摘要

### 各环境成本估算

| 环境 | 固定费/月 | 变动费/月 | 合计/月 |
|------|----------|----------|--------|
| 演示/PoC | ~$0 | ~$1〜$3 | **~$1〜$3** |
| 生产（1 UC） | ~$29 | ~$1〜$3 | **~$30〜$32** |
| 生产（全部 5 UC） | ~$29 | ~$5〜$15 | **~$34〜$44** |

### 成本分类

- **按请求计费（按量付费）**: Lambda, Step Functions, S3 API, Textract, Comprehend, Rekognition, Bedrock, Athena — 不使用则为 $0
- **常驻运行（固定费）**: Interface VPC Endpoints (~$28.80/月) — **可选（opt-in）**

> Quick Start 为优先确保 VPC 内 Lambda 的连通性而指定 `EnableVpcEndpoints=true`。如果优先考虑低成本 PoC，请考虑使用 VPC 外 Lambda 配置或利用现有的 NAT / Interface VPC Endpoints。

> 详细成本分析请参阅 [docs/cost-analysis.md](docs/cost-analysis.md)。

### 可选资源

高成本常驻资源通过 CloudFormation 参数设为可选。

| 资源 | 参数 | 默认值 | 月固定费 | 说明 |
|------|------|--------|---------|------|
| Interface VPC Endpoints | `EnableVpcEndpoints` | `false` | ~$28.80 | 用于 Secrets Manager、FSx、CloudWatch、SNS。生产环境推荐 `true`。Quick Start 中为确保连通性指定 `true` |
| CloudWatch Alarms | `EnableCloudWatchAlarms` | `false` | ~$0.10/告警 | 监控 Step Functions 失败率、Lambda 错误率 |

> **S3 Gateway VPC Endpoint** 无额外按时计费，因此在 VPC 内 Lambda 访问 S3 AP 的配置中推荐启用。但如果已存在 S3 Gateway Endpoint 或 PoC / 演示用途中 Lambda 部署在 VPC 外，请指定 `EnableS3GatewayEndpoint=false`。S3 API 请求、数据传输及各 AWS 服务使用费照常产生。

## 安全与授权模型

本方案组合了**多个授权层**，各层承担不同角色:

| 层级 | 角色 | 控制范围 |
|------|------|---------|
| **IAM** | AWS 服务和 S3 Access Points 的访问控制 | Lambda 执行角色、S3 AP 策略 |
| **S3 Access Point** | 通过与 S3 AP 关联的文件系统用户定义访问边界 | S3 AP 策略、network origin、关联用户 |
| **ONTAP 文件系统** | 强制执行文件级权限 | UNIX 权限 / NTFS ACL |
| **ONTAP REST API** | 仅公开元数据和控制平面操作 | Secrets Manager 认证 + TLS |

**重要设计注意事项**:

- S3 API 不公开文件级 ACL。文件权限信息**只能通过 ONTAP REST API** 获取（UC1 的 ACL Collection 使用此模式）
- 通过 S3 AP 的访问在 IAM / S3 AP 策略许可后，以与 S3 AP 关联的 UNIX / Windows 文件系统用户身份在 ONTAP 侧进行授权
- ONTAP REST API 凭证在 Secrets Manager 中管理，不存储在 Lambda 环境变量中

## 兼容性矩阵

| 项目 | 值 / 验证内容 |
|------|-------------|
| ONTAP 版本 | 已在 9.17.1P4D3 上验证（需要支持 S3 Access Points 的版本） |
| 已验证区域 | ap-northeast-1（东京） |
| 推荐区域 | us-east-1 / us-west-2（使用全部 AI/ML 服务时） |
| Python 版本 | 3.12+ |
| CloudFormation Transform | AWS::Serverless-2016-10-31 |
| 已验证卷 security style | UNIX, NTFS |

### FSx ONTAP S3 Access Points 支持的 API

通过 S3 AP 可用的 API 子集:

| API | 支持 |
|-----|------|
| ListObjectsV2 | ✅ |
| GetObject | ✅ |
| PutObject | ✅ (最大 5 GB) |
| HeadObject | ✅ |
| DeleteObject | ✅ |
| DeleteObjects | ✅ |
| CopyObject | ✅ (同一 AP 内、同一区域) |
| GetObjectAttributes | ✅ |
| GetObjectTagging / PutObjectTagging | ✅ |
| CreateMultipartUpload | ✅ |
| UploadPart / UploadPartCopy | ✅ |
| CompleteMultipartUpload | ✅ |
| AbortMultipartUpload | ✅ |
| ListParts / ListMultipartUploads | ✅ |
| HeadBucket / GetBucketLocation | ✅ |
| GetBucketNotificationConfiguration | ❌（不支持 → 轮询设计的原因） |
| Presign | ❌ |

### S3 Access Point 网络来源约束

| 网络来源 | Lambda (VPC 外) | Lambda (VPC 内) | Athena / Glue | 推荐 UC |
|---------|----------------|----------------|--------------|---------|
| **internet** | ✅ | ✅ (通过 S3 Gateway EP) | ✅ | UC1, UC3 (使用 Athena) |
| **VPC** | ❌ | ✅ (S3 Gateway EP 必须) | ❌ | UC2, UC4, UC5 (不使用 Athena) |

> **重要**: Athena / Glue 从 AWS 托管基础设施访问，因此无法访问 VPC origin 的 S3 AP。UC1（法务）和 UC3（制造业）使用 Athena，因此 S3 AP 必须以 **internet** network origin 创建。

### S3 AP 限制事项

- **PutObject 最大大小**: 5 GB。multipart upload API 受支持，但 5 GB 以上的上传可行性请按用例逐一验证。
- **加密**: 仅支持 SSE-FSX（FSx 透明处理，无需指定 ServerSideEncryption 参数）
- **ACL**: 仅支持 `bucket-owner-full-control`
- **不支持的功能**: Object Versioning, Object Lock, Object Lifecycle, Static Website Hosting, Requester Pays, Presigned URL

## 文档

详细指南和截图存储在 `docs/` 目录中。

| 文档 | 说明 |
|------|------|
| [docs/guides/deployment-guide.md](docs/guides/deployment-guide.md) | 部署指南（前提条件确认 → 参数准备 → 部署 → 功能验证） |
| [docs/guides/operations-guide.md](docs/guides/operations-guide.md) | 运维指南（调度变更、手动执行、日志确认、告警响应） |
| [docs/guides/troubleshooting-guide.md](docs/guides/troubleshooting-guide.md) | 故障排除（AccessDenied、VPC Endpoint、ONTAP 超时、Athena） |
| [docs/cost-analysis.md](docs/cost-analysis.md) | 成本结构分析 |
| [docs/references.md](docs/references.md) | 参考链接集 |
| [docs/extension-patterns.md](docs/extension-patterns.md) | 扩展模式指南 |
| [docs/region-compatibility.md](docs/region-compatibility.md) | AWS 区域 AI/ML 服务支持情况 |
| [docs/article-draft.md](docs/article-draft.md) | dev.to 文章原始草稿（已发布版本请参阅 README 顶部的相关文章） |
| [docs/verification-results.md](docs/verification-results.md) | AWS 环境验证结果记录 |
| [docs/screenshots/](docs/screenshots/README.md) | AWS 控制台截图（已脱敏） |

## 目录结构

```
fsxn-s3ap-serverless-patterns/
├── README.md                          # 本文件
├── LICENSE                            # MIT License
├── requirements.txt                   # 生产依赖
├── requirements-dev.txt               # 开发依赖
├── shared/                            # 共享模块
│   ├── __init__.py
│   ├── ontap_client.py               # ONTAP REST API 客户端
│   ├── fsx_helper.py                 # AWS FSx API 辅助工具
│   ├── s3ap_helper.py                # S3 Access Point 辅助工具
│   ├── exceptions.py                 # 共享异常与错误处理器
│   ├── discovery_handler.py          # 共享 Discovery Lambda 模板
│   ├── cfn/                          # CloudFormation 代码片段
│   └── tests/                        # 单元测试与属性测试
├── legal-compliance/                  # UC1: 法务合规
├── financial-idp/                     # UC2: 金融保险
├── manufacturing-analytics/           # UC3: 制造业
├── media-vfx/                         # UC4: 媒体
├── healthcare-dicom/                  # UC5: 医疗
├── scripts/                           # 验证与部署脚本
│   ├── deploy_uc.sh                  # UC 部署脚本（通用）
│   ├── verify_shared_modules.py      # 共享模块 AWS 环境验证
│   └── verify_cfn_templates.sh       # CloudFormation 模板验证
├── .github/workflows/                 # CI/CD (lint, test)
└── docs/                              # 文档
    ├── guides/                        # 操作指南
    │   ├── deployment-guide.md       # 部署指南
    │   ├── operations-guide.md       # 运维指南
    │   └── troubleshooting-guide.md  # 故障排除
    ├── screenshots/                   # AWS 控制台截图
    ├── cost-analysis.md               # 成本结构分析
    ├── references.md                  # 参考链接集
    ├── extension-patterns.md          # 扩展模式指南
    ├── region-compatibility.md        # 区域兼容性矩阵
    ├── verification-results.md        # 验证结果记录
    └── article-draft.md               # dev.to 文章原始草稿
```

## 共享模块 (shared/)

| 模块 | 说明 |
|------|------|
| `ontap_client.py` | ONTAP REST API 客户端（Secrets Manager 认证、urllib3、TLS、重试） |
| `fsx_helper.py` | AWS FSx API + CloudWatch 指标获取 |
| `s3ap_helper.py` | S3 Access Point 辅助工具（分页、后缀过滤） |
| `exceptions.py` | 共享异常类、`lambda_error_handler` 装饰器 |
| `discovery_handler.py` | 共享 Discovery Lambda 模板（Manifest 生成） |

## 开发

### 运行测试

```bash
# 全部测试
pytest shared/tests/ -v

# 含覆盖率
pytest shared/tests/ --cov=shared --cov-report=term-missing --cov-fail-under=80 -v

# 仅属性基测试
pytest shared/tests/test_properties.py -v
```

### 代码检查

```bash
# Python 代码检查
ruff check .
ruff format --check .

# CloudFormation 模板验证
cfn-lint */template.yaml */template-deploy.yaml
```

## 何时使用 / 何时不使用本模式集

### 适用场景

- 希望在不移动 FSx for ONTAP 上现有 NAS 数据的情况下进行无服务器处理
- 希望从 Lambda 无需 NFS / SMB 挂载即可获取文件列表和进行预处理
- 希望学习 S3 Access Points 和 ONTAP REST API 的职责分离
- 希望快速验证行业专属 AI / ML 处理模式作为 PoC
- 可以接受 EventBridge Scheduler + Step Functions 的轮询设计

### 不适用场景

- 需要实时文件变更事件处理（S3 Event Notification 不支持）
- 需要 Presigned URL 等完整的 S3 存储桶兼容性
- 已有基于 EC2 / ECS 的常驻批处理基础设施，且可以接受 NFS 挂载运维
- 文件数据已存在于 S3 标准存储桶中，可通过 S3 事件通知处理

## 生产部署的额外考虑事项

本仓库包含面向生产部署的设计决策，但在实际生产环境中请额外考虑以下事项。

- 与组织 IAM / SCP / Permission Boundary 的一致性
- S3 AP 策略和 ONTAP 侧用户权限的审查
- Lambda / Step Functions / Bedrock / Textract 等的审计日志和执行日志（CloudTrail / CloudWatch Logs）的启用
- CloudWatch Alarms / SNS / Incident Management 集成（`EnableCloudWatchAlarms=true`）
- 数据分类、个人信息、医疗信息等行业特定合规要求
- 区域限制和跨区域调用时的数据驻留确认
- Step Functions 执行历史保留期和日志级别设置
- Lambda 的 Reserved Concurrency / Provisioned Concurrency 设置

## 贡献

欢迎提交 Issue 和 Pull Request。详情请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

MIT License — 详情请参阅 [LICENSE](LICENSE)。
