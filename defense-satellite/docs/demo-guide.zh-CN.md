# UC15 演示脚本（30分钟版）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## 前提条件

- AWS 账户，ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- 已部署 `defense-satellite/template-deploy.yaml`（`EnableSageMaker=false`）

## 时间线

### 0:00 - 0:05 简介（5 分钟）

- 用例背景：卫星图像数据的增长（Sentinel、Landsat、商用 SAR）
- 传统 NAS 的挑战：基于复制的工作流程耗时且成本高
- FSxN S3AP 的优势：零复制、NTFS ACL 联动、无服务器处理

### 0:05 - 0:10 架构说明（5 分钟）

- 通过 Mermaid 图介绍 Step Functions 工作流程
- 根据图像大小切换 Rekognition / SageMaker 的逻辑
- 基于 geohash 的变化检测机制

### 0:10 - 0:15 实时部署（5 分钟）

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-uc15-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:20 示例图像处理（5 分钟）

```bash
# 上传示例 GeoTIFF
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# 执行 Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- 在 AWS 控制台展示 Step Functions 图（Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration）
- 确认执行到 SUCCEEDED 的时间（通常 2-3 分钟）

### 0:20 - 0:25 结果确认（5 分钟）

- 展示 S3 输出存储桶的层次结构：
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- 在 CloudWatch Logs 中确认 EMF 指标
- 在 DynamoDB `change-history` 表中查看变化检测历史

### 0:25 - 0:30 问答 + 总结（5 分钟）

- 公共部门合规对应（DoD CC SRG、CSfC、FedRAMP）
- GovCloud 迁移路径（使用相同模板从 `ap-northeast-1` → `us-gov-west-1`）
- 成本优化（SageMaker Endpoint 仅在实际运营时启用）
- 下一步：多卫星提供商集成、Sentinel-1/2 Hub 联动

## 常见问题与解答

**Q. 如何处理 SAR 数据（Sentinel-1 的 HDF5）？**  
A. Discovery Lambda 将其分类为 `image_type=sar`，Tiling 可实现 HDF5 解析器（rasterio 或 h5py）。Object Detection 需要专用 SAR 分析模型（SageMaker）。

**Q. 图像大小阈值（5MB）的依据是什么？**  
A. Rekognition DetectLabels API 的 Bytes 参数上限。通过 S3 可达 15MB。原型采用 Bytes 路由。

**Q. 变化检测的精度如何？**  
A. 当前实现是基于 bbox 面积的简单比较。正式运营建议使用 SageMaker 的语义分割。

---

## 关于输出目标：可通过 OutputDestination 选择（模式 B）

UC15 defense-satellite 在 2026-05-11 的更新中支持了 `OutputDestination` 参数
（参见 `docs/output-destination-patterns.md`）。

**目标工作负载**：卫星图像切片 / 物体检测 / Geo enrichment

**两种模式**：

### STANDARD_S3（默认，与以往相同）
创建新的 S3 存储桶（`${AWS::StackName}-output-${AWS::AccountId}`），
并将 AI 成果写入其中。Discovery Lambda 的 manifest 仅写入 S3 Access Point
（与以往相同）。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (其他必需参数)
```

### FSXN_S3AP（"无数据移动"模式）
将切片 metadata、物体检测 JSON、Geo enrichment 后的检测结果通过 FSxN S3 Access Point
写回到与原始卫星图像**相同的 FSx ONTAP 卷**。
分析人员可以在 SMB/NFS 的现有目录结构中直接引用 AI 成果。
不会创建标准 S3 存储桶。

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
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
- AlertGeneration Lambda 仅使用 SNS，因此不受 `OutputDestination` 影响
- AWS 规范上的限制请参见
  [项目 README 的"AWS 规范上的限制与解决方法"部分](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)
