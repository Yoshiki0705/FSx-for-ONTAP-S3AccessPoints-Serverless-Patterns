# UC17 演示脚本（30分钟版）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## 前提

- AWS 账户，ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Bedrock Nova Lite v1:0 模型已启用

## 时间线

### 0:00 - 0:05 简介（5 分钟）

- 地方政府的挑战：城市规划、灾害应对、基础设施维护中 GIS 数据应用增加
- 传统挑战：GIS 分析以 ArcGIS / QGIS 等专业软件为中心
- 提案：FSxN S3AP + 无服务器实现自动化

### 0:05 - 0:10 架构（5 分钟）

- CRS 标准化的重要性（混合数据源）
- 通过 Bedrock 生成城市规划报告
- 风险模型（洪水、地震、滑坡）的计算公式

### 0:10 - 0:15 部署（5 分钟）

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-uc17-demo \
  --parameter-overrides \
    DeployBucket=<deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    BedrockModelId=amazon.nova-lite-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM
```

### 0:15 - 0:22 执行处理（7 分钟）

```bash
# 上传示例航空照片（仙台市某区域）
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# 执行 Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

确认结果：
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json`（CRS 信息）
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json`（土地利用分布）
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json`（灾害风险评分）
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md`（Bedrock 生成报告）

### 0:22 - 0:27 风险地图解说（5 分钟）

- 通过 DynamoDB `landuse-history` 表确认时间序列变化
- 显示 Bedrock 生成报告的 Markdown
- 洪水、地震、滑坡风险评分的可视化

### 0:27 - 0:30 总结（3 分钟）

- 与 Amazon Location Service 的集成可能性
- 正式运营时的点云处理（LAS Layer 部署）
- 下一步：MapServer 集成、面向市民的门户网站

## 常见问题与解答

**Q. CRS 转换实际会执行吗？**  
A. 仅在部署 rasterio / pyproj Layer 时执行。通过 `PYPROJ_AVAILABLE` 检查进行回退。

**Q. Bedrock 模型的选择标准？**  
A. Nova Lite 成本/精度平衡良好。如需长文本推荐 Claude Sonnet。
A. Nova Lite 在日语报告生成方面成本效率高。Claude 3 Haiku 是优先考虑精度时的替代方案。

---

## 关于输出目标：可通过 OutputDestination 选择（模式 B）

UC17 smart-city-geospatial 在 2026-05-11 的更新中支持了 `OutputDestination` 参数
（参见 `docs/output-destination-patterns.md`）。

**目标工作负载**：CRS 标准化元数据 / 土地利用分类 / 基础设施评估 / 风险地图 / Bedrock 生成报告

**2 种模式**：

### STANDARD_S3（默认，与以往相同）
创建新的 S3 存储桶（`${AWS::StackName}-output-${AWS::AccountId}`），
将 AI 成果写入其中。Discovery Lambda 的 manifest 仅写入 S3 Access Point
（与以往相同）。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必需参数)
```

### FSXN_S3AP（"no data movement" 模式）
CRS 标准化元数据、土地利用分类结果、基础设施评估、风险地图、Bedrock 生成的
城市规划报告（Markdown）通过 FSxN S3 Access Point 写回到与原始 GIS 数据
**相同的 FSx ONTAP 卷**中。
城市规划负责人可以在 SMB/NFS 的现有目录结构中直接引用 AI 成果。
不会创建标准 S3 存储桶。

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (其他必需参数)
```

**注意事项**：

- 强烈建议指定 `S3AccessPointName`（同时为 Alias 格式和 ARN 格式授予 IAM 权限）
- 超过 5GB 的对象在 FSxN S3AP 中不可用（AWS 规范），必须使用分段上传
- ChangeDetection Lambda 仅使用 DynamoDB，因此不受 `OutputDestination` 影响
- Bedrock 报告以 Markdown（`text/markdown; charset=utf-8`）形式写出，因此可以通过 SMB/NFS
  客户端的文本编辑器直接查看
- AWS 规范上的限制请参考
  [项目 README 的"AWS 规范上的限制与解决方法"部分](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)
