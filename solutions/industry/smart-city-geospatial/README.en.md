# UC17: Smart City — Geospatial Analytics & Urban Planning

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)
📚 **Documentation**: [Architecture](docs/architecture.md) | [Demo Script](docs/demo-guide.md) | [Troubleshooting](../docs/phase7-troubleshooting.md)

## Overview

An automated analysis pipeline for geospatial (GIS) data built on
FSx for ONTAP S3 Access Points. It integrates satellite imagery, LiDAR, and
IoT sensor data for urban planning, infrastructure monitoring, and disaster response.

## Use Case

Local governments and urban planning agencies integrate geospatial data from
multiple sources to automate urban infrastructure monitoring, change detection,
and disaster risk assessment.

### Processing Flow

```
FSx for ONTAP (GIS data storage — department-level access control)
  → S3 Access Point
    → Step Functions workflow
      → Discovery: detect new data (GeoTIFF, Shapefile, GeoJSON, LAS)
      → Preprocessing: coordinate system conversion / normalization (EPSG unification, EPSG:4326)
      → LandUseClassification: land use classification (ML inference)
      → ChangeDetection: time-series change detection (new buildings, green area reduction)
      → InfraAssessment: infrastructure deterioration assessment (roads, bridges, LAS point clouds)
      → RiskMapping: disaster risk map generation (flood, earthquake, landslide)
      → ReportGeneration: urban planning report generation (Bedrock Nova Lite)
```

### Target Data

| Data format | Description | Typical size |
|-----------|------|-----------|
| GeoTIFF | Aerial / satellite imagery | 100 MB – 10 GB |
| Shapefile (.shp) | Vector data (roads, buildings, parcels) | 1 – 500 MB |
| GeoJSON | Lightweight vector data | 1 KB – 100 MB |
| LAS / LAZ | LiDAR point clouds (terrain / building 3D) | 100 MB – 5 GB |
| GeoPackage (.gpkg) | OGC-standard GIS database | 10 MB – 2 GB |

### AWS Services

| Service | Purpose |
|---------|------|
| FSx for ONTAP | Persistent storage for GIS data (department-level NTFS ACL) |
| S3 Access Points | Data access from serverless components |
| Step Functions | Workflow orchestration |
| Lambda | Preprocessing, coordinate conversion, metadata extraction |
| SageMaker (Batch Transform) | Land use classification, change detection ML inference (optional) |
| Amazon Rekognition | Object detection from aerial imagery (buildings, vehicles) |
| Amazon Bedrock Nova Lite | Japanese-language urban planning report generation |
| DynamoDB | Time-series land use history, change detection |
| SNS | Anomaly detection alerts |
| CloudWatch | Observability |

### Public Sector Alignment

- **INSPIRE Directive support** (EU geospatial data infrastructure)
- **OGC standards compliance**: WMS, WFS, WCS, GeoPackage
- **Open data**: processing results can be published to citizen-facing portals
- **Disaster response**: real-time damage-situation mapping
- **Data sovereignty**: municipal data stays within the region

### Usage Scenarios

| Scenario | Input data | Output |
|---------|-----------|------|
| Urban greening monitoring | Satellite imagery (time series) | Green area change report |
| Illegal dumping detection | Drone imagery | Alert + location information |
| Road deterioration assessment | Vehicle-mounted camera imagery | Repair priority map |
| Flood risk assessment | LiDAR + rainfall data | Inundation prediction map |
| Building permit support | Aerial imagery + building application | Difference detection report |

## Verified Screens (Screenshots)

### 1. GIS Data Storage (via S3 Access Point)

The data placement confirmation screen as seen by a municipal GIS officer.
GeoTIFF / Shapefile / LAS are placed under the `gis/YYYY/MM/` prefix.

<!-- SCREENSHOT: phase7-uc17-s3-gis-uploaded.png
     Content: S3 AP gis/ prefix listing, mixed file formats
     Mask: account ID, S3 AP ARN, file names derived from real coordinates -->
![UC17: GIS data storage confirmation](../docs/screenshots/masked/phase7/phase7-uc17-s3-gis-uploaded.png)

### 2. Bedrock-Generated Urban Planning Report (Markdown view)

**UC17's flagship feature**: integrating land use distribution, change detection,
and risk assessment, Bedrock Nova Lite automatically generates a Japanese-language
report for municipal staff.

<!-- SCREENSHOT: phase7-uc17-bedrock-report.png
     Content: reports/*.md rendered in the S3 console
     Actual sample content:
       ### Findings report for municipal staff
       #### Points of note for urban planning
       According to the GIS data, the land use distribution in the city is stable...
       #### Priority measures to consider
       1. Strengthen flood countermeasures ... 2. Strengthen earthquake countermeasures ... 3. Strengthen slope-failure countermeasures ...
     Mask: account ID, municipality name (only the sample name is shown) -->
![UC17: Bedrock-generated report](../docs/screenshots/masked/phase7/phase7-uc17-bedrock-report.png)

### 3. Disaster Risk Map JSON

Three types of risk scores — flood, earthquake, and landslide — are classified
into four levels: CRITICAL / HIGH / MEDIUM / LOW.

<!-- SCREENSHOT: phase7-uc17-risk-map-json.png
     Content: formatted view of risk-maps/*.json (flood, earthquake, landslide levels highlighted)
     Mask: account ID -->
![UC17: Disaster risk map](../docs/screenshots/masked/phase7/phase7-uc17-risk-map-json.png)

### 4. Land Use Distribution (JSON)

The land use class distribution derived from Rekognition / SageMaker inference results.
Ratios of residential / commercial / forest / water / road, etc.

<!-- SCREENSHOT: phase7-uc17-landuse-distribution.png
     Content: contents of landuse/*.json (residential: 0.5, forest: 0.3, etc.)
     Mask: account ID -->
![UC17: Land use distribution](../docs/screenshots/masked/phase7/phase7-uc17-landuse-distribution.png)

### 5. Time-Series Change Visualization (DynamoDB Explorer)

The `fsxn-uc17-demo-landuse-history` table. For each area_id, past land use
distributions are compared with current values to compute change_magnitude.

<!-- SCREENSHOT: phase7-uc17-dynamodb-landuse-history.png
     Content: time-series items of the landuse-history table in DynamoDB Explorer
     Mask: account ID, area_id -->
![UC17: Time-series change table](../docs/screenshots/masked/phase7/phase7-uc17-dynamodb-landuse-history.png)


## Success Metrics

### Outcome
By automating geospatial analysis (CRS normalization, land use classification, disaster risk mapping), it supports urban planning decision-making.

### Metrics
| Metric | Target (example) |
|-----------|------------|
| Datasets processed / run | > 100 files |
| CRS normalization success rate | > 95% |
| Land use classification accuracy | > 80% |
| Risk map generation time | < 10 min |
| Cost / run | < $10 |
| Human Review target rate | < 20% (classification-uncertain areas) |

### Measurement Method
Step Functions execution history, Bedrock analysis reports, Rekognition detection results, S3 output GeoJSON, CloudWatch Metrics.

## Deploy

### Prerequisite Verification

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-Shot Deployment

```bash
bash scripts/deploy_phase7.sh smart-city-geospatial
```

### Manual Deployment

```bash
# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.
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

**Important**: Enable model access for `amazon.nova-lite-v1:0` in the Bedrock console.

## Directory Structure

```
smart-city-geospatial/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── preprocessing/handler.py          # CRS normalization (EPSG:4326)
│   ├── land_use_classification/handler.py
│   ├── change_detection/handler.py
│   ├── infra_assessment/handler.py       # LAS/LAZ point cloud analysis
│   ├── risk_mapping/handler.py           # flood/earthquake/landslide risk
│   └── report_generation/handler.py      # Bedrock Nova Lite
├── tests/                                # 34 pytest + resilience tests
└── README.md
```


---

## AWS Documentation Links

| Service | Documentation |
|---------|------------|
| FSx for ONTAP | [User Guide](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Developer Guide](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon SageMaker | [Developer Guide](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| Amazon Location Service | [Developer Guide](https://docs.aws.amazon.com/location/latest/developerguide/welcome.html) |
| Amazon Bedrock | [User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) |

### Well-Architected Framework Alignment

| Pillar | Alignment |
|----|------|
| Operational Excellence | X-Ray, EMF, land use change tracking, resilience tests |
| Security | Least-privilege IAM, KMS, department-level NTFS ACL, INSPIRE compliance |
| Reliability | Step Functions Retry/Catch, CRS normalization, resilience tests |
| Performance Efficiency | GeoTIFF tiling, SageMaker Batch Transform |
| Cost Optimization | Serverless, SageMaker Spot, DynamoDB time series |
| Sustainability | Incremental change detection, OGC standards compliance |





---

## Cost Estimate (Approximate Monthly)

> **Note**: The following is an estimate for the ap-northeast-1 region; actual costs vary with usage. Check the latest pricing with the [AWS Pricing Calculator](https://calculator.aws/).

### Serverless Components (Pay-as-you-go)

| Service | Unit price | Assumed usage | Approx. monthly |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 7 functions × 20 datasets/day | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/day | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/day | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~40K tokens/run | ~$3-10 |
| Athena | $5/TB scanned | ~30 MB/query | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/day | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/month | ~$0.76 |

### Fixed Costs (FSx for ONTAP — assumes existing environment)

| Component | Monthly |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (shared existing environment) |
| S3 Access Point | No additional charge (S3 API charges only) |

### Total Estimate

| Configuration | Approx. monthly |
|------|---------|
| Minimal (once daily) | ~$5-15 |
| Standard (hourly) | ~$15-50 |
| Large scale (high frequency + alarms) | ~$50-150 |

> **Governance Caveat**: Cost estimates are approximate and not guaranteed. Actual billing varies with usage patterns, data volume, and region.

---

## Local Testing

### Prerequisites Check

```bash
# Verify prerequisites
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (for sam local)
aws sts get-caller-identity  # AWS credentials
```

### sam local invoke

```bash
# Build
# Prerequisite: AWS SAM CLI required. 'sam build' packages the code and shared layer automatically.
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

See the [Local Testing Quick Start](../docs/local-testing-quick-start.md) for details.

---

## Output Sample

Example output of the geospatial data analysis pipeline:

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

> **Note**: The above is sample output; actual values vary with the environment and input data. Benchmark figures are a sizing reference, not a service limit.

---

## Governance Note

> This pattern provides technical architecture guidance. It is not legal, compliance, or regulatory advice. Organizations should consult qualified professionals.

---

## S3AP Compatibility

For compatibility constraints, troubleshooting, and trigger patterns for S3 Access Points for FSx for ONTAP, see the [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
