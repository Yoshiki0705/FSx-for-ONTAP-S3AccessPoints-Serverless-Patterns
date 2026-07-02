# UC17：智慧城市 — 地理空间数据分析·城市规划

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **文档**: [架构](docs/architecture.md) | [演示脚本](docs/demo-guide.md) | [故障排查](../docs/phase7-troubleshooting.md)

## 概述

基于 FSx for ONTAP S3 Access Points 的地理空间数据（GIS）
自动分析管道。为城市规划、基础设施监控、灾害应对而
整合处理卫星图像·LiDAR·IoT 传感器数据。

## 用例

地方政府·城市规划机构整合来自多个来源的地理空间数据，
自动化城市基础设施状态监控、变化检测和灾害风险评估。

### 处理流程

```
FSx for ONTAP (GIS 数据存储 — 按部门访问控制)
  → S3 Access Point
    → Step Functions 工作流
      → Discovery：检测新数据（GeoTIFF, Shapefile, GeoJSON, LAS）
      → Preprocessing：坐标系转换·归一化（EPSG 统一，EPSG:4326）
      → LandUseClassification：土地利用分类（ML 推理）
      → ChangeDetection：时间序列变化检测（新建建筑、绿地减少）
      → InfraAssessment：基础设施劣化评估（道路、桥梁、LAS 点云）
      → RiskMapping：灾害风险地图生成（洪水、地震、滑坡）
      → ReportGeneration：城市规划报告生成（Bedrock Nova Lite）
```

### 目标数据

| 数据格式 | 说明 | 典型大小 |
|-----------|------|-----------|
| GeoTIFF | 航空照片·卫星图像 | 100 MB – 10 GB |
| Shapefile (.shp) | 矢量数据（道路、建筑、地块） | 1 – 500 MB |
| GeoJSON | 轻量矢量数据 | 1 KB – 100 MB |
| LAS / LAZ | LiDAR 点云（地形·建筑 3D） | 100 MB – 5 GB |
| GeoPackage (.gpkg) | OGC 标准 GIS 数据库 | 10 MB – 2 GB |

### AWS 服务

| 服务 | 用途 |
|---------|------|
| FSx for ONTAP | GIS 数据的持久化存储（按部门 NTFS ACL） |
| S3 Access Points | 从无服务器组件访问数据 |
| Step Functions | 工作流编排 |
| Lambda | 预处理、坐标转换、元数据提取 |
| SageMaker (Batch Transform) | 土地利用分类、变化检测 ML 推理（可选） |
| Amazon Rekognition | 从航空照片进行物体检测（建筑、车辆） |
| Amazon Bedrock Nova Lite | 日语城市规划报告生成 |
| DynamoDB | 时间序列土地利用历史、变化检测 |
| SNS | 异常检测告警 |
| CloudWatch | 可观测性 |

### Public Sector 适配性

- **INSPIRE 指令支持**（EU 地理空间数据基础设施）
- **OGC 标准合规**：WMS, WFS, WCS, GeoPackage
- **开放数据**：处理结果可发布至面向市民的门户
- **灾害应对**：实时受灾状况映射
- **数据主权**：自治体数据在区域内完成闭环

### 应用场景

| 场景 | 输入数据 | 输出 |
|---------|-----------|------|
| 城市绿化监控 | 卫星图像（时间序列） | 绿地面积变化报告 |
| 非法倾倒检测 | 无人机图像 | 告警 + 位置信息 |
| 道路劣化评估 | 车载摄像头图像 | 修复优先级地图 |
| 洪水风险评估 | LiDAR + 降雨数据 | 淹没预测地图 |
| 建筑审查支持 | 航空照片 + 建筑申请 | 差异检测报告 |

## 已验证的画面（截图）

### 1. GIS 数据存储（经由 S3 Access Point）

从自治体 GIS 负责人视角看到的分析对象数据的放置确认画面。
在 `gis/YYYY/MM/` 前缀下放置 GeoTIFF / Shapefile / LAS。

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     内容：S3 AP 的 gis/ 前缀列表，文件格式混合
     掩码：账户 ID、S3 AP ARN、源自真实坐标的文件名 -->
![UC17：GIS 数据存储确认](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Bedrock 生成的城市规划报告（Markdown 显示）

**UC17 的核心功能**：整合土地利用分布·变化检测·风险评估，
由 Bedrock Nova Lite 面向自治体负责人自动生成日语报告。

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     内容：在 S3 控制台渲染显示 reports/*.md
     实际样本内容：
       ### 面向自治体负责人的所见报告
       #### 城市规划上的关注点
       根据 GIS 数据，市内的土地利用分布稳定……
       #### 应优先的对策方案
       1. 加强洪水对策 …… 2. 加强地震对策 …… 3. 加强斜坡崩塌对策 ……
     掩码：账户 ID、自治体名称（仅显示样本名称） -->
![UC17：Bedrock 生成报告](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. 灾害风险地图 JSON

将洪水·地震·滑坡 3 种风险评分按 CRITICAL / HIGH / MEDIUM / LOW
4 个等级判定。

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     内容：risk-maps/*.json 的格式化视图（强调 flood, earthquake, landslide 的 level）
     掩码：账户 ID -->
![UC17：灾害风险地图](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. 土地利用分布（JSON）

从 Rekognition / SageMaker 推理结果导出的土地利用类别分布。
residential / commercial / forest / water / road 等的比例。

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     内容：landuse/*.json 的内容（residential: 0.5, forest: 0.3 等）
     掩码：账户 ID -->
![UC17：土地利用分布](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. 时间序列变化可视化（DynamoDB Explorer）

`fsxn-uc17-demo-landuse-history` 表。按 area_id 将过去的土地利用分布与
当前值比较，计算 change_magnitude。

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     内容：在 DynamoDB Explorer 中 landuse-history 表的时间序列项
     掩码：账户 ID、area_id -->
![UC17：时间序列变化表](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
通过自动化地理空间分析（CRS 归一化·土地利用分类·灾害风险映射），支持城市规划的决策。

### Metrics
| 指标 | 目标值（示例） |
|-----------|------------|
| 已处理数据集数 / 执行 | > 100 files |
| CRS 归一化成功率 | > 95% |
| 土地利用分类精度 | > 80% |
| 风险地图生成时间 | < 10 分钟 |
| 成本 / 执行 | < $10 |
| Human Review 对象率 | < 20%（分类不确定区域） |

### Measurement Method
Step Functions 执行历史、Bedrock 分析报告、Rekognition 检测结果、S3 输出 GeoJSON、CloudWatch Metrics。

## 部署

### 事前验证

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### 一次性部署

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### 手动部署

```bash
# 前提：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
sam build

sam deploy \
  --stack-name fsxn-smart-city \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**重要**：请在 Bedrock 控制台启用 `amazon.nova-lite-v1:0` 的模型访问权限。

## 目录结构

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS 归一化（EPSG:4326）
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ 点云分析
│   ├── risk_mapping/handler.py           # 洪水/地震/滑坡风险
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## AWS 文档链接

| 服务 | 文档 |
|---------|------------|
| FSx for ONTAP | [用户指南](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [开发者指南](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [开发者指南](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [开发者指南](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [用户指南](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework 对应

| 支柱 | 对应 |
|----|------|
| 卓越运营 | X-Ray、EMF、土地利用变化追踪、resilience 测试 |
| 安全性 | 最小权限 IAM、KMS、按部门 NTFS ACL、INSPIRE 合规 |
| 可靠性 | Step Functions Retry/Catch、CRS 归一化、resilience 测试 |
| 性能效率 | GeoTIFF 分块、SageMaker Batch Transform |
| 成本优化 | 无服务器、SageMaker Spot、DynamoDB 时间序列 |
| 可持续性 | 差分变化检测、OGC 标准合规 |





---

## 成本估算（每月概算）

> **备注**：以下为 ap-northeast-1 区域的概算，实际成本因使用量而异。最新价格请在 [AWS Pricing Calculator](https://calculator.aws/) 确认。

### 无服务器组件（按量计费）

| 服务 | 单价 | 预计使用量 | 每月概算 |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 函数 × 20 datasets/天 | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/天 | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/天 | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/执行 | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/查询 | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/天 | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/月 | ~$0.76 |

### 固定成本（FSx for ONTAP — 假设已有环境）

| 组件 | 每月 |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (共享已有环境) |
| S3 Access Point | 无额外费用（仅 S3 API 费用） |

### 合计概算

| 配置 | 每月概算 |
|------|---------|
| 最小配置（每日 1 次执行） | ~$5-15 |
| 标准配置（每小时执行） | ~$15-50 |
| 大规模配置（高频 + 告警） | ~$50-150 |

> **Governance Caveat**：成本估算为概算，非保证值。实际账单因使用模式、数据量和区域而异。

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
# 前提：需要 AWS SAM CLI。sam build 会自动打包代码和共享层。
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

详情请参阅 [本地测试快速入门](../docs/local-testing-quick-start.md)。

---

## 输出样本 (Output Sample)

地理空间数据分析管道的输出示例：

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 10,
    "formats": {"geotiff": 4, "shapefile": 3, "geojson": 2, "geopackage": 1}
  },
  "crs_normalization": {
    "converted": 7,
    "target_crs": "EPSG:4326",
    "already_correct": 3
  },
  "land_use_classification": {
    "total_area_km2": 45.2,
    "categories": {
      "residential": 18.5,
      "commercial": 8.2,
      "industrial": 5.1,
      "green_space": 10.4,
      "water": 3.0
    }
  },
  "risk_mapping": {
    "flood_risk_zones": 3,
    "earthquake_risk_zones": 2,
    "landslide_risk_zones": 1,
    "output_geojson": "s3://output-bucket/risk-maps/combined-2026-05-23.geojson"
  },
  "inspire_compliance": true
}
```

> **备注**：以上为样本输出，实际值因环境·输入数据而异。基准数值为 sizing reference，而非 service limit。

---

## Governance Note

> 本模式提供技术架构指导。并非法律·合规·监管建议。组织应咨询合格的专业人士。

---

## S3AP Compatibility

关于 S3 Access Points for FSx for ONTAP 的兼容性约束、故障排查和触发模式，请参阅 [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md)。
