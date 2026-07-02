# UC15: 国防 / 航天 — 卫星图像分析管道

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文档**: [架构](docs/architecture.zh-CN.md) | [演示脚本](docs/demo-guide.zh-CN.md) | [故障排除](../docs/phase7-troubleshooting.md)

## 概述

利用 Amazon FSx for NetApp ONTAP S3 Access Points 的卫星图像（SAR / 光学）
自动分析管道。将大容量卫星图像数据存储在 FSx for ONTAP 中，
并通过 S3 Access Points 执行无服务器处理。

## 用例

国防·情报机构以及航天相关组织自动处理·分析从卫星获取的
地球观测数据（Earth Observation）。

### 处理流程

```
FSx for ONTAP (卫星图像存储)
  → S3 Access Point
    → Step Functions 工作流
      → Discovery: 检测新图像 (GeoTIFF, NITF, HDF5)
      → Tiling: 将大图像分割为瓦片 (Cloud Optimized GeoTIFF 转换)
      → ObjectDetection: 使用 Rekognition / SageMaker 进行物体检测
      → ChangeDetection: 通过时间序列比较进行变化检测
      → GeoEnrichment: 附加元数据 (坐标、拍摄时间、分辨率)
      → AlertGeneration: 检测到异常时生成告警
```

### 目标数据

| 数据格式 | 说明 | 典型大小 |
|-----------|------|-----------|
| GeoTIFF | 光学卫星图像 | 100 MB – 10 GB |
| NITF | 军事标准图像格式 | 500 MB – 50 GB |
| HDF5 | SAR 数据 (Sentinel-1 等) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | 已瓦片化图像 | 10 – 500 MB |

### AWS 服务

| 服务 | 用途 |
|---------|------|
| FSx for ONTAP | 卫星图像的持久化存储 (通过 NTFS ACL 进行访问控制) |
| S3 Access Points | 从无服务器访问图像 |
| Step Functions | 工作流编排 |
| Lambda | 瓦片分割、元数据提取、告警生成 |
| SageMaker (Batch Transform) | 物体检测·变化检测 ML 推理 |
| Amazon Rekognition | 标签检测 (车辆、建筑、船舶) |
| Amazon Bedrock | 图像标题生成、报告摘要 |
| DynamoDB | 处理状态管理、检测结果索引 |
| SNS | 告警通知 |
| CloudWatch | 可观测性 |

### Public Sector 适配性

- **DoD CC SRG**: FSx for ONTAP 已通过 Impact Level 2/4/5 认证 (GovCloud)
- **CSfC**: NetApp ONTAP 已通过 Commercial Solutions for Classified 认证
- **FedRAMP**: 在 AWS GovCloud 中符合 FedRAMP High
- **数据主权**: 数据在区域内完结 (ap-northeast-1 / us-gov-west-1)

## 已验证的界面（截图）

以 2026-05-10 在 ap-northeast-1 实际确认运行时**一般人员日常操作的 UI**
为中心进行展示。面向技术人员的控制台界面（Step Functions 图形等）请参见
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md)。

### 1. 卫星图像存储（通过 FSx for ONTAP / S3 Access Point）

从文件服务器管理员角度看到的、待分析卫星图像的放置确认界面。
只需在 `satellite/YYYY/MM/` 前缀下放置新图像，
定期的 Step Functions 工作流就会自动拾取。

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     内容: 通过 S3 AP 列表显示 satellite/2026/05/*.tif (对象名、大小、更新时间)
     掩码: 账户 ID、Access Point ARN、真实卫星图像名 -->
![UC15: 卫星图像放置](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. 分析结果查看（S3 输出桶）

检测结果（`detections/*.json`）、地理元数据（`enriched/*.json`）、
瓦片信息（`tiles/*/metadata.json`）经整理后存储。

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     内容: 在 S3 控制台俯瞰 detections/、enriched/、tiles/ 三个前缀
     掩码: 账户 ID、桶名前缀 -->
![UC15: S3 输出桶](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. 变化检测告警（SNS 电子邮件通知）

一般人员（运维负责人）接收的 SNS 告警邮件。
当变化面积超过阈值（默认 1 km²）时自动发送。

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     内容: 在邮件客户端 (Gmail/Outlook) 显示 alert_type=SATELLITE_CHANGE_DETECTED
     掩码: 收件人邮箱地址、发件人地址、真实坐标、tile_id -->
![UC15: SNS 告警通知邮件](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. 检测结果 JSON 的内容

检测结果（标签、置信度、bbox）的清晰 JSON 查看器。

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     内容: 在 S3 控制台预览对象，detections JSON 的内容
     掩码: 账户 ID -->
![UC15: 检测结果 JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
通过卫星图像分析（物体检测·变化检测·告警）的自动化，实现情报分析的提速。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| 已处理图像数 / 执行 | > 50 images |
| 物体检测精度 | > 80% |
| 变化检测成功率 | > 85% |
| 告警生成时间 | < 5 分钟 |
| 成本 / 执行 | < $15 |
| Human Review 必需率 | 100%（告警发出前必须人工审批） |

> **100% Human Review 的理由**: 由于告警误报·漏报的业务影响极大，因此要求对全部项目进行人工审批。

### Measurement Method
Step Functions 执行历史、Rekognition 检测结果、Bedrock 分析报告、SNS 通知日志、CloudWatch Metrics。审批记录保存在 DynamoDB 中，以便审计时可追踪"谁·何时·审批了什么"。

## 部署

### 事前验证

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一键部署

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### 手动部署

```bash
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**重要**: `S3AccessPointName` 是为 S3 AP 授予 IAM 权限所必需的。
详情请参见 [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md)。

## 目录结构

```
defense-satellite/
├── template.yaml              # SAM 模板 (开发用)
├── template-deploy.yaml       # CloudFormation 模板 (部署用)
├── functions/
│   ├── discovery/handler.py   # 新卫星图像检测
│   ├── tiling/handler.py      # 瓦片分割 + COG 转换
│   ├── object_detection/handler.py  # 物体检测 (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # 时间序列变化检测
│   ├── geo_enrichment/handler.py    # 地理元数据附加
│   └── alert_generation/handler.py  # 告警生成
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## AWS 文档链接

| 服务 | 文档 |
|---------|------------|
| FSx for ONTAP | [用户指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [开发者指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [开发者指南](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [开发者指南](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [用户指南](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Well-Architected Framework 对应

| 支柱 | 对应 |
|----|------|
| 卓越运营 | X-Ray、EMF、告警生成、100% Human Review |
| 安全性 | DoD CC SRG、FedRAMP、最小权限 IAM、KMS、VPC 隔离 |
| 可靠性 | Step Functions Retry/Catch、resilience 测试、回退 |
| 性能效率 | COG 瓦片化、并行物体检测、SageMaker Batch |
| 成本优化 | 无服务器、SageMaker 竞价、瓦片单位处理 |
| 可持续性 | 按需执行、差分变化检测 |





---

## 成本估算（每月概算）

> **注意**: 以下为 ap-northeast-1 区域的概算，实际成本因使用量而异。最新价格请在 [AWS Pricing Calculator](https://calculator.aws/) 确认。

### 无服务器组件（按量计费）

| 服务 | 单价 | 假定使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 函数 × 10 scenes/天 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/天 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/天 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/执行 | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/查询 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/天 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### 固定成本（FSx for ONTAP — 以现有环境为前提）

| 组件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共享现有环境) |
| S3 Access Point | 无额外费用 (仅 S3 API 费用) |

### 合计概算

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次执行） | ~$5-15 |
| 标准配置（每小时执行） | ~$15-50 |
| 大规模配置（高频 + 告警） | ~$50-150 |

> **Governance Caveat**: 成本估算为概算，并非保证值。实际账单金额因使用模式、数据量、区域而异。

---

## 本地测试

### Prerequisites 检查

```bash
# 确认前提条件
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (sam local 用)
aws sts get-caller-identity  # AWS 凭证
```

### sam local invoke

```bash
# 构建
# 前提: 需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

# 本地运行 Discovery Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# 带环境变量覆盖
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### 单元测试

```bash
python3 -m pytest tests/ -v
```

详情请参见 [本地测试快速入门](../docs/local-testing-quick-start.md)。

---

## 输出示例 (Output Sample)

卫星图像分析管道的输出示例 (Human Review 必需):

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **注意**: 以上为示例输出，实际值因环境·输入数据而异。基准数值为 sizing reference，并非 service limit。

---

## Governance Note

> 本模式提供技术架构指导。它并非法律·合规·监管建议。组织应咨询合格的专业人士。

---

## S3AP Compatibility

关于 S3 Access Points for FSx for ONTAP 的兼容性约束、故障排除和触发模式，请参见 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
