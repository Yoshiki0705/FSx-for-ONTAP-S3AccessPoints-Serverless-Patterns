# UC15 Demo Script (30-minute slot)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | English | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | [Deutsch](demo-guide.de.md) | [Español](demo-guide.es.md)

> Note: This translation is produced by Amazon Bedrock Claude. Contributions to improve translation quality are welcome.

## Prerequisites

- AWS account, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `defense-satellite/template-deploy.yaml` already deployed (`EnableSageMaker=false`)

## Timeline

### 0:00 - 0:05 Intro (5 min)

- Use case background: Growth of satellite imagery data (Sentinel, Landsat, commercial SAR)
- Challenges with traditional NAS: Copy-based workflows are time-consuming and costly
- Benefits of FSxN S3AP: zero-copy, NTFS ACL integration, serverless processing

### 0:05 - 0:10 Architecture Overview (5 min)

- Introduce Step Functions workflow with Mermaid diagram
- Rekognition / SageMaker switching logic based on image size
- Change detection mechanism using geohash

### 0:10 - 0:15 Live Deployment (5 min)

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

### 0:15 - 0:20 Sample Image Processing (5 min)

```bash
# Upload sample GeoTIFF
aws s3 cp sample-satellite.tif \
  s3://<s3-ap-arn>/satellite/2026/05/tokyo_bay.tif

# Execute Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <uc15-StateMachineArn> \
  --input '{}'
```

- Show Step Functions graph in AWS Console (Discovery → Map → Tiling → ObjectDetection → ChangeDetection → GeoEnrichment → AlertGeneration)
- Check execution time until SUCCEEDED (typically 2-3 minutes)

### 0:20 - 0:25 Result Verification (5 min)

- Show S3 output bucket hierarchy:
  - `tiles/YYYY/MM/DD/<basename>/metadata.json`
  - `detections/<tile_key>_detections.json`
  - `enriched/YYYY/MM/DD/<tile_id>.json`
- Check EMF metrics in CloudWatch Logs
- View change detection history in DynamoDB `change-history` table

### 0:25 - 0:30 Q&A + Wrap-up (5 min)

- Public Sector regulatory compliance (DoD CC SRG, CSfC, FedRAMP)
- GovCloud migration path (same template from `ap-northeast-1` → `us-gov-west-1`)
- Cost optimization (enable SageMaker Endpoint only for production use)
- Next steps: Multi-satellite provider integration, Sentinel-1/2 Hub integration

## Frequently Asked Questions

**Q. How to handle SAR data (Sentinel-1 HDF5)?**  
A. Discovery Lambda classifies as `image_type=sar`, Tiling can implement HDF5 parser (rasterio or h5py). Object Detection requires dedicated SAR analysis model (SageMaker).

**Q. What is the rationale for the image size threshold (5MB)?**  
A. Rekognition DetectLabels API Bytes parameter limit. Up to 15MB is possible via S3. Prototype adopts the Bytes route.

**Q. What is the accuracy of change detection?**  
A. Current implementation uses simple bbox area-based comparison. For production use, SageMaker semantic segmentation is recommended.

---

## About Output Destination: Selectable via OutputDestination (Pattern B)

UC15 defense-satellite now supports the `OutputDestination` parameter as of the 2026-05-11 update
(see `docs/output-destination-patterns.md`).

**Target workload**: Satellite imagery tiling / object detection / Geo enrichment

**Two modes**:

### STANDARD_S3 (default, traditional behavior)
Creates a new S3 bucket (`${AWS::StackName}-output-${AWS::AccountId}`) and
writes AI artifacts there. Only the Discovery Lambda manifest is written to the S3 Access Point
(as before).

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (other required parameters)
```

### FSXN_S3AP ("no data movement" pattern)
Writes tiling metadata, object detection JSON, and Geo enrichment results back to the **same FSx ONTAP volume**
as the original satellite imagery via FSxN S3 Access Point.
Analysts can directly reference AI artifacts within the existing SMB/NFS directory structure.
No standard S3 bucket is created.

```bash
aws cloudformation deploy \
  --template-file defense-satellite/template-deploy.yaml \
  --stack-name fsxn-defense-satellite-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (other required parameters)
```

**Notes**:

- Strongly recommend specifying `S3AccessPointName` (grant IAM permissions for both Alias and ARN formats)
- Objects over 5GB are not supported by FSxN S3AP (AWS specification), multipart upload required
- ChangeDetection Lambda uses only DynamoDB, so it is not affected by `OutputDestination`
- AlertGeneration Lambda uses only SNS, so it is not affected by `OutputDestination`
- For AWS specification constraints, see
  [the "AWS Specification Constraints and Workarounds" section in the project README](../../README.md#aws-仕様上の制約と回避策)
  and [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verified UI/UX Screenshots

Following the same policy as Phase 7 UC15/16/17 and UC6/11/14 demos, targeting **UI/UX screens that
end users actually see in daily operations**. Technical views (Step Functions graph, CloudFormation
stack events, etc.) are consolidated in `docs/verification-results-*.md`.

### Verification Status for This Use Case

- ✅ **E2E Verification**: SUCCEEDED (Phase 7 Extended Round, commit b77fc3b)
- 📸 **UI/UX Capture**: ✅ Complete (Phase 8 Theme D, commit d7ebabd)

### Existing Screenshots (Phase 7 verification)

![Step Functions Graph view (SUCCEEDED)](../../docs/screenshots/masked/uc15-demo/step-functions-graph-succeeded.png)

![S3 output bucket](../../docs/screenshots/masked/uc15-demo/s3-output-bucket.png)

![S3 Enriched output](../../docs/screenshots/masked/uc15-demo/s3-enriched-output.png)

![DynamoDB change history table](../../docs/screenshots/masked/uc15-demo/dynamodb-change-history-table.png)

![SNS notification topics](../../docs/screenshots/masked/uc15-demo/sns-notification-topics.png)
### UI/UX Target Screens for Re-verification (Recommended Capture List)

- S3 output bucket (detections/, geo-enriched/, alerts/)
- Rekognition satellite imagery object detection result JSON preview
- GeoEnrichment coordinate-annotated detection results
- SNS alert notification email
- AI artifacts on FSx ONTAP volume (when in FSXN_S3AP mode)

### Capture Guide

1. **Preparation**:
   - Check prerequisites with `bash scripts/verify_phase7_prerequisites.sh` (common VPC/S3 AP existence)
   - Package Lambda with `UC=defense-satellite bash scripts/package_generic_uc.sh`
   - Deploy with `bash scripts/deploy_generic_ucs.sh UC15`

2. **Sample Data Placement**:
   - Upload sample GeoTIFF to `satellite-imagery/` prefix via S3 AP Alias
   - Start Step Functions `fsxn-defense-satellite-demo-workflow` (input `{}`)

3. **Capture** (close CloudShell/terminal, mask username in browser top-right):
   - Overview of S3 output bucket `fsxn-defense-satellite-demo-output-<account>`
   - AI/ML output JSON preview (detections, geo-enriched)
   - SNS email notification (notification from AlertGeneration)

4. **Masking**:
   - Auto-mask with `python3 scripts/mask_uc_demos.py defense-satellite-demo`
   - Apply additional masking as needed following `docs/screenshots/MASK_GUIDE.md`

5. **Cleanup**:
   - Delete with `bash scripts/cleanup_generic_ucs.sh UC15`
   - VPC Lambda ENI release takes 15-30 minutes (AWS specification)
