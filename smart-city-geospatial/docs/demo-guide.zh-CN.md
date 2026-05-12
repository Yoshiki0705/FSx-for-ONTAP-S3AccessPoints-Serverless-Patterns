# UC17 演示脚本（30分钟版）

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | 简体中文 | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> 注意：此翻译由 Amazon Bedrock Claude 生成。欢迎对翻译质量提出改进建议。

## 前提条件

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
- 风险模型（洪水·地震·滑坡）的计算公式

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
- 洪水·地震·滑坡风险评分的可视化

### 0:27 - 0:30 总结（3 分钟）

- 与 Amazon Location Service 的集成可能性
- 正式运营时的点云处理（LAS Layer 部署）
- 下一步：MapServer 集成、面向市民的门户网站

## 常见问题与解答

**Q. CRS 转换是否实际执行？**  
A. 仅在 rasterio / pyproj Layer 部署时执行。通过 `PYPROJ_AVAILABLE` 检查进行回退。

**Q. Bedrock 模型的选择标准？**  
A. Nova Lite 在成本/精度平衡方面表现良好。如需长文本则推荐 Claude Sonnet。
A. Nova Lite 在日语报告生成方面成本效率高。Claude 3 Haiku 是优先考虑精度时的替代方案。

---

## 关于输出目标：可通过 OutputDestination 选择（模式 B）

UC17 smart-city-geospatial 在 2026-05-11 的更新中支持了 `OutputDestination` 参数
（参见 `docs/output-destination-patterns.md`）。

**目标工作负载**：CRS 标准化元数据 / 土地利用分类 / 基础设施评估 / 风险地图 / Bedrock 生成报告

**两种模式**：

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
将 CRS 标准化元数据、土地利用分类结果、基础设施评估、风险地图、Bedrock 生成的
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
- Bedrock 报告以 Markdown（`text/markdown; charset=utf-8`）形式写出，因此可通过 SMB/NFS
  客户端的文本编辑器直接查看
- AWS 规范上的限制请参见
  [项目 README 的"AWS 规范上的限制与规避措施"部分](../../README.md#aws-仕様上の制約と回避策)
  以及 [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## 已验证的 UI/UX 截图

与 Phase 7 UC15/16/17 和 UC6/11/14 的演示相同方针，以**最终用户在日常业务中实际
看到的 UI/UX 界面**为对象。面向技术人员的视图（Step Functions 图、CloudFormation
堆栈事件等）汇总在 `docs/verification-results-*.md` 中。

### 本用例的验证状态

- ✅ **E2E 验证**：SUCCEEDED（Phase 7 Extended Round，commit b77fc3b）
- 📸 **UI/UX 截图**：✅ 已完成（Phase 8 Theme D，commit d7ebabd）

### 现有截图（Phase 7 验证时）

![Step Functions Graph view（SUCCEEDED）](../../docs/screenshots/masked/uc17-demo/step-functions-graph-succeeded.png)

![S3 输出存储桶](../../docs/screenshots/masked/uc17-demo/s3-output-bucket.png)

![DynamoDB landuse_history 表](../../docs/screenshots/masked/uc17-demo/dynamodb-landuse-history-table.png)
### 重新验证时的 UI/UX 目标界面（推荐截图列表）

- S3 输出存储桶（tiles/、land-use/、change-detection/、risk-maps/、reports/）
- Bedrock 生成的城市规划报告（Markdown 预览）
- DynamoDB landuse_history 表（土地利用分类历史）
- 风险地图 JSON 预览（CRITICAL/HIGH/MEDIUM/LOW 分类）
- FSx ONTAP 卷上的 AI 成果（FSXN_S3AP 模式时 — 可通过 SMB/NFS 查看的 Markdown 报告）

### 截图指南

1. **事前准备**：
   - 通过 `bash scripts/verify_phase7_prerequisites.sh` 确认前提条件（共享 VPC/S3 AP 是否存在）
   - 通过 `UC=smart-city-geospatial bash scripts/package_generic_uc.sh` 打包 Lambda
   - 通过 `bash scripts/deploy_generic_ucs.sh UC17` 部署

2. **放置示例数据**：
   - 通过 S3 AP Alias 将示例 GeoTIFF 上传到 `gis/` 前缀
   - 启动 Step Functions `fsxn-smart-city-geospatial-demo-workflow`（输入 `{}`）

3. **截图**（关闭 CloudShell·终端，浏览器右上角的用户名涂黑）：
   - S3 输出存储桶 `fsxn-smart-city-geospatial-demo-output-<account>` 的概览
   - Bedrock 报告 Markdown 的浏览器预览
   - DynamoDB landuse_history 表的项目列表
   - 风险地图 JSON 的结构确认

4. **遮罩处理**：
   - 通过 `python3 scripts/mask_uc_demos.py smart-city-geospatial-demo` 自动遮罩
   - 根据 `docs/screenshots/MASK_GUIDE.md` 进行额外遮罩（如有必要）

5. **清理**：
   - 通过 `bash scripts/cleanup_generic_ucs.sh UC17` 删除
   - VPC Lambda ENI 释放需要 15-30 分钟（AWS 规范）
