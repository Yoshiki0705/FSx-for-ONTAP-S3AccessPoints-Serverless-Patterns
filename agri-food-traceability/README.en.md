# UC21: Agriculture & Food — Farmland Aerial Imagery / Traceability Document Management

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to analyze farmland drone/aerial imagery for crop health monitoring and automate traceability document (harvest records, shipping manifests, inspection certificates) structured data extraction and lot classification.

### Key Features

- Auto-detection of GeoTIFF/JPEG images with GPS metadata (max 500 MB/image) via S3 AP
- Rekognition + Bedrock vegetation index analysis and anomaly classification (confidence ≥ 0.70)
- Textract + Comprehend traceability document extraction with lot classification (confidence ≥ 0.80)
- Crop health report (per-field anomaly count, types, affected coordinates)
- Traceability audit summary (document count per lot, confidence distribution)

## Success Metrics

| Metric | Target |
|--------|--------|
| Crop anomaly detection accuracy | ≥ 70% confidence |
| Traceability classification rate | ≥ 80% confidence |
| Geolocation verification rate | ≥ 90% |
| Report generation time | < 120 seconds |
| Human review rate | > 20% |


## ⚠️ Performance Considerations

- FSx for ONTAP throughput capacity is **shared across NFS/SMB/S3 AP**. Running MapConcurrency=10 in parallel may impact other workloads on the same volume.
- For large batch processing, check FSx ONTAP Throughput Capacity (MBps) and adjust MapConcurrency accordingly.
- Recommended: Start with MapConcurrency=5 in production, monitor FSx ONTAP CloudWatch metrics (ThroughputUtilization), and increase gradually.

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. Food traceability data handling must comply with applicable food safety and labeling regulations.

> **S3 AP NetworkOrigin Note**: The Discovery Lambda is deployed inside a VPC. If the S3 Access Point's NetworkOrigin is `Internet`, it cannot be accessed via S3 Gateway VPC Endpoint (requests are not routed to the FSx data plane). Use a VPC-origin S3 AP or configure NAT Gateway access. See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 食品衛生法 (Food Sanitation Act), 食品表示法 (Food Labeling Act), JAS 法
