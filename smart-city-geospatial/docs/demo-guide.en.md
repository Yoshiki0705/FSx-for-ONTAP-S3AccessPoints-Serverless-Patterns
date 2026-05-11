# UC17 Demo Script (30-minute slot)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Prerequisites

- AWS account, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- Bedrock Nova Lite v1:0 model enabled

## Timeline

### 0:00 - 0:05 Intro (5 min)

- Municipal challenges: increasing use of GIS data for urban planning, disaster response, infrastructure maintenance
- Traditional challenges: GIS analysis centered on specialized software like ArcGIS / QGIS
- Proposal: automation with FSxN S3AP + serverless

### 0:05 - 0:10 Architecture (5 min)

- Importance of CRS normalization (mixed data sources)
- Urban planning report generation with Bedrock
- Calculation formulas for risk models (flood, earthquake, landslide)

### 0:10 - 0:15 Deployment (5 min)

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

### 0:15 - 0:22 Execution (7 min)

```bash
# サンプル航空写真アップロード（仙台市の一画）
aws s3 cp sendai_district.tif \
  s3://<s3-ap-arn>/gis/2026/05/sendai.tif

# Step Functions 実行
aws stepfunctions start-execution \
  --state-machine-arn <uc17-StateMachineArn> \
  --input '{}'
```

Verify results:
- `s3://<out>/preprocessed/gis/2026/05/sendai.tif.metadata.json` (CRS information)
- `s3://<out>/landuse/gis/2026/05/sendai.tif.json` (land use distribution)
- `s3://<out>/risk-maps/gis/2026/05/sendai.tif.json` (disaster risk scores)
- `s3://<out>/reports/2026/05/10/gis/2026/05/sendai.tif.md` (Bedrock generated report)

### 0:22 - 0:27 Risk Map Explanation (5 min)

- Check time-series changes in DynamoDB `landuse-history` table
- Display Bedrock generated report markdown
- Visualize flood, earthquake, and landslide risk scores

### 0:27 - 0:30 Wrap-up (3 min)

- Potential integration with Amazon Location Service
- Point cloud processing for production use (LAS Layer deployment)
- Next steps: MapServer integration, citizen-facing portal

## FAQ

**Q. Is CRS conversion actually performed?**  
A. Only when rasterio / pyproj Layer is deployed. Fallback with `PYPROJ_AVAILABLE` check.

**Q. What are the criteria for selecting a Bedrock model?**  
A. Nova Lite offers a good cost/accuracy balance. Claude Sonnet is recommended for long documents.
A. Nova Lite is cost-efficient for Japanese report generation. Claude 3 Haiku is an alternative when accuracy is prioritized.

---

## About Output Destination: Selectable with OutputDestination (Pattern B)

UC17 smart-city-geospatial now supports the `OutputDestination` parameter as of the 2026-05-11 update
(see `docs/output-destination-patterns.md`).

**Target workloads**: CRS normalization metadata / land use classification / infrastructure assessment / risk maps / Bedrock generated reports

**Two modes**:

### STANDARD_S3 (default, traditional behavior)
Creates a new S3 bucket (`${AWS::StackName}-output-${AWS::AccountId}`) and
writes AI outputs there. Only the Discovery Lambda manifest is written to the S3 Access Point
(as before).

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (other required parameters)
```

### FSXN_S3AP ("no data movement" pattern)
Writes CRS normalization metadata, land use classification results, infrastructure assessments, risk maps, and Bedrock-generated
urban planning reports (Markdown) back to the **same FSx ONTAP volume** as the original GIS data via the FSxN S3 Access Point.
Urban planning staff can directly reference AI outputs within the existing SMB/NFS directory structure.
No standard S3 bucket is created.

```bash
aws cloudformation deploy \
  --template-file smart-city-geospatial/template-deploy.yaml \
  --stack-name fsxn-smart-city-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (other required parameters)
```

**Notes**:

- Strongly recommend specifying `S3AccessPointName` (grant IAM permissions for both Alias and ARN formats)
- Objects larger than 5GB are not supported by FSxN S3AP (AWS specification), multipart upload required
- ChangeDetection Lambda uses DynamoDB only, so it is not affected by `OutputDestination`
- Bedrock reports are written as Markdown (`text/markdown; charset=utf-8`), so they can be viewed directly
  in text editors on SMB/NFS clients
- For AWS specification constraints, see
  [the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
  and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verified UI/UX Screenshots

Following the same approach as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting
**UI/UX screens that end users actually see in daily operations**.
Technical views (Step Functions graph, CloudFormation stack events, etc.)
are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX Capture**: ✅ Complete (Phase 8 Theme D, commit d7ebabd)

### Existing Screenshots

![Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc17-demo/step-functions-graph-succeeded.png)

![S3 Output Bucket](../../docs/screenshots/masked/uc17-demo/s3-output-bucket.png)

![DynamoDB landuse_history Table](../../docs/screenshots/masked/uc17-demo/dynamodb-landuse-history-table.png)
### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (tiles/, land-use/, change-detection/, risk-maps/, reports/)
- Bedrock-generated urban planning report (Markdown preview)
- DynamoDB landuse_history table (land-use classification history)
- Risk map JSON preview (CRITICAL/HIGH/MEDIUM/LOW classification)
- FSx ONTAP volume AI artifacts (FSXN_S3AP mode — Markdown report viewable via SMB/NFS)

### Capture Guide

1. **Preparation**: Run `bash scripts/verify_phase7_prerequisites.sh` to check prerequisites
2. **Sample Data**: Upload sample files via S3 AP Alias, then start Step Functions workflow
3. **Capture** (close CloudShell/terminal, mask username in browser top-right)
4. **Mask**: Run `python3 scripts/mask_uc_demos.py <uc-dir>` for automated OCR masking
5. **Cleanup**: Run `bash scripts/cleanup_generic_ucs.sh <UC>` to delete stack
