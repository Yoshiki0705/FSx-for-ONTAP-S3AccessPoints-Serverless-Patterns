# UC15: Defense / Space — Satellite Imagery Analytics Pipeline

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Script](docs/demo-guide.en.md) | [Troubleshooting](../docs/phase7-troubleshooting.md)

## Overview

An automated analytics pipeline for satellite imagery (SAR / optical) leveraging
Amazon FSx for NetApp ONTAP S3 Access Points. Large-volume satellite imagery data
is stored on FSx for ONTAP, and serverless processing is executed via S3 Access Points.

## Use Case

Defense and intelligence agencies and space-related organizations automatically
process and analyze Earth Observation data acquired from satellites.

### Processing Flow

```
FSx for ONTAP (satellite imagery storage)
  → S3 Access Point
    → Step Functions workflow
      → Discovery: detect new images (GeoTIFF, NITF, HDF5)
      → Tiling: split large images into tiles (Cloud Optimized GeoTIFF conversion)
      → ObjectDetection: object detection with Rekognition / SageMaker
      → ChangeDetection: change detection via time-series comparison
      → GeoEnrichment: metadata enrichment (coordinates, capture datetime, resolution)
      → AlertGeneration: alert generation on anomaly detection
```

### Target Data

| Data Format | Description | Typical Size |
|-----------|------|-----------|
| GeoTIFF | Optical satellite imagery | 100 MB – 10 GB |
| NITF | Military standard image format | 500 MB – 50 GB |
| HDF5 | SAR data (Sentinel-1 etc.) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | Pre-tiled imagery | 10 – 500 MB |

### AWS Services

| Service | Purpose |
|---------|------|
| FSx for ONTAP | Persistent storage for satellite imagery (access control via NTFS ACL) |
| S3 Access Points | Image access from serverless |
| Step Functions | Workflow orchestration |
| Lambda | Tiling, metadata extraction, alert generation |
| SageMaker (Batch Transform) | Object detection / change detection ML inference |
| Amazon Rekognition | Label detection (vehicles, buildings, vessels) |
| Amazon Bedrock | Image caption generation, report summarization |
| DynamoDB | Processing state management, detection result index |
| SNS | Alert notification |
| CloudWatch | Observability |

### Public Sector Suitability

- **DoD CC SRG**: FSx for ONTAP is Impact Level 2/4/5 certified (GovCloud)
- **CSfC**: NetApp ONTAP is Commercial Solutions for Classified certified
- **FedRAMP**: FedRAMP High compliant in AWS GovCloud
- **Data sovereignty**: Data stays within the region (ap-northeast-1 / us-gov-west-1)

## Verified Screens (Screenshots)

Focusing on **the UI general staff operate day-to-day**, based on a live run verified
in ap-northeast-1 on 2026-05-10. For engineer-facing console screens (Step Functions
graphs, etc.), see
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md).

### 1. Satellite Imagery Placement (via FSx for ONTAP / S3 Access Point)

The placement confirmation screen for satellite imagery to be analyzed, as seen by the
file server administrator. Simply place new images under the `satellite/YYYY/MM/` prefix,
and the periodic Step Functions workflow automatically picks them up.

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     Content: List satellite/2026/05/*.tif via S3 AP (object name, size, last modified)
     Mask: account ID, Access Point ARN, real satellite image names -->
![UC15: Satellite imagery placement](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. Viewing Analysis Results (S3 Output Bucket)

Detection results (`detections/*.json`), geo metadata (`enriched/*.json`), and
tile information (`tiles/*/metadata.json`) are organized and stored.

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     Content: Overview of the 3 prefixes detections/, enriched/, tiles/ in the S3 console
     Mask: account ID, bucket name prefix -->
![UC15: S3 output bucket](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. Change Detection Alert (SNS Email Notification)

The SNS alert email received by general staff (operators). Automatically sent when the
changed area exceeds the threshold (default 1 km²).

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     Content: Show alert_type=SATELLITE_CHANGE_DETECTED in an email client (Gmail/Outlook)
     Mask: recipient email address, sender address, real coordinates, tile_id -->
![UC15: SNS alert email](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. Contents of the Detection Result JSON

A clean JSON viewer of detection results (labels, confidence, bbox).

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     Content: Object preview in the S3 console, contents of the detections JSON
     Mask: account ID -->
![UC15: Detection results JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
By automating satellite imagery analytics (object detection, change detection, alerts), achieve faster intelligence analysis.

### Metrics
| Metric | Target (example) |
|-----------|------------|
| Processed images / run | > 50 images |
| Object detection accuracy | > 80% |
| Change detection success rate | > 85% |
| Alert generation time | < 5 min |
| Cost / run | < $15 |
| Human Review mandatory rate | 100% (human approval required before alert dispatch) |

> **Reason for 100% Human Review**: Because the business impact of a false or missed alert is extremely large, human approval of all items is mandatory.

### Measurement Method
Step Functions execution history, Rekognition detection results, Bedrock analysis reports, SNS notification logs, and CloudWatch Metrics. Approval records are stored in DynamoDB so that "who approved what and when" can be traced during an audit.

## Deployment

### Pre-verification

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-shot Deployment

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### Manual Deployment

```bash
# Prerequisite: AWS SAM CLI required. sam build packages the code and shared layer automatically.
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

**Important**: `S3AccessPointName` is required for granting IAM permissions to the S3 AP.
For details, see [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md).

## Directory Structure

```
defense-satellite/
├── template.yaml              # SAM template (development)
├── template-deploy.yaml       # CloudFormation template (deployment)
├── functions/
│   ├── discovery/handler.py   # New satellite image detection
│   ├── tiling/handler.py      # Tiling + COG conversion
│   ├── object_detection/handler.py  # Object detection (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # Time-series change detection
│   ├── geo_enrichment/handler.py    # Geo metadata enrichment
│   └── alert_generation/handler.py  # Alert generation
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## AWS Documentation Links

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Developer Guide](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [Developer Guide](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [Developer Guide](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [User Guide](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Well-Architected Framework Alignment

| Pillar | Alignment |
|----|------|
| Operational Excellence | X-Ray, EMF, alert generation, 100% Human Review |
| Security | DoD CC SRG, FedRAMP, least-privilege IAM, KMS, VPC isolation |
| Reliability | Step Functions Retry/Catch, resilience tests, fallback |
| Performance Efficiency | COG tiling, parallel object detection, SageMaker Batch |
| Cost Optimization | Serverless, SageMaker Spot, per-tile processing |
| Sustainability | On-demand execution, differential change detection |





---

## Cost Estimate (Monthly Approximate)

> **Note**: The following are approximate figures for the ap-northeast-1 region; actual costs vary by usage. Check the latest pricing at the [AWS Pricing Calculator](https://calculator.aws/).

### Serverless Components (Pay-as-you-go)

| Service | Unit Price | Assumed Usage | Monthly Approx. |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 functions × 10 scenes/day | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/day | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/day | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/run | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/query | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/day | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/month | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### Fixed Cost (FSx for ONTAP — existing environment assumed)

| Component | Monthly |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (shared existing environment) |
| S3 Access Point | No additional charge (S3 API charges only) |

### Total Approximate

| Configuration | Monthly Approx. |
|------|---------|
| Minimal (daily, once) | ~$5-15 |
| Standard (hourly) | ~$15-50 |
| Large-scale (high frequency + alarms) | ~$50-150 |

> **Governance Caveat**: Cost estimates are approximate, not guaranteed values. The actual billed amount varies by usage pattern, data volume, and region.

---

## Local Testing

### Prerequisites Check

```bash
# Check prerequisites
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (for sam local)
aws sts get-caller-identity  # AWS credentials
```

### sam local invoke

```bash
# Build
# Prerequisite: AWS SAM CLI required. sam build packages the code and shared layer automatically.
sam build

# Run the Discovery Lambda locally
sam local invoke DiscoveryFunction --event events/discovery-event.json

# With environment variable overrides
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit Tests

```bash
python3 -m pytest tests/ -v
```

For details, see [Local Testing Quick Start](../docs/local-testing-quick-start.md).

---

## Output Sample

Example output of the satellite imagery analytics pipeline (Human Review required):

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

> **Note**: The above is a sample output; actual values vary by environment and input data. Benchmark figures are a sizing reference, not a service limit.

---

## Governance Note

> This pattern provides technical architecture guidance. It is not legal, compliance, or regulatory advice. Organizations should consult qualified professionals.

---

## S3AP Compatibility

For compatibility constraints, troubleshooting, and trigger patterns of S3 Access Points for FSx for ONTAP, see [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
