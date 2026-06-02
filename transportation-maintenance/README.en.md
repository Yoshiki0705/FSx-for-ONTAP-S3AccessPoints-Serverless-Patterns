# UC22: Transportation & Rail — Equipment Inspection Image Analysis / Maintenance Report Management

🌐 **Language / 言語**: [日本語](README.md) | English | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

📚 **Documentation**: [Architecture](docs/architecture.en.md) | [Demo Guide](docs/demo-guide.en.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to detect deterioration indicators (cracks, rust, displacement) from railway infrastructure inspection images, classify severity, and generate maintenance priority rankings. **Safety-critical infrastructure (bridges, signaling equipment, rail joints) uses a lower detection threshold with mandatory human review.**

### Key Features

- Auto-detection of inspection images (JPEG/PNG/TIFF) and maintenance reports (PDF/Excel) via S3 AP
- Rekognition dual-threshold detection: standard 80%, safety-critical 60%
- Bedrock severity classification: critical / major / minor / observation
- All detections < 90% confidence flagged for human review (safety-critical)
- Textract + Comprehend repair history and lifecycle data extraction
- 12-month deterioration trend analysis + priority ranking (severity x component age)
- Low-resolution images (< 1024x768) auto-marked as requires-reinspection

## Success Metrics

| Metric | Target |
|--------|--------|
| Defect detection rate (standard) | >= 85% |
| Defect detection rate (safety-critical) | >= 95% |
| Severity classification accuracy | >= 80% |
| False negative rate (safety-critical) | < 5% |
| Human review rate | > 30% |

## Safety-Critical Design

| Category | Threshold | Human Review |
|----------|-----------|-------------|
| Standard infrastructure | Rekognition >= 80% | Detection recorded |
| Safety-critical (bridges) | Rekognition >= 60% | All < 90% reviewed |
| Safety-critical (signaling) | Rekognition >= 60% | All < 90% reviewed |
| Safety-critical (rail joints) | Rekognition >= 60% | All < 90% reviewed |


## ⚠️ Performance Considerations

- FSx for ONTAP throughput capacity is **shared across NFS/SMB/S3 AP**. Running MapConcurrency=10 in parallel may impact other workloads on the same volume.
- For large batch processing, check FSx ONTAP Throughput Capacity (MBps) and adjust MapConcurrency accordingly.
- Recommended: Start with MapConcurrency=5 in production, monitor FSx ONTAP CloudWatch metrics (ThroughputUtilization), and increase gradually.

## Governance Note

> This pattern provides technical architecture guidance. It does not constitute legal, compliance, or regulatory advice. Railway infrastructure safety must comply with applicable railway regulations. AI detection results are not final judgments — qualified engineer confirmation is mandatory.

> **S3 AP NetworkOrigin Note**: The Discovery Lambda is deployed inside a VPC. If the S3 Access Point's NetworkOrigin is `Internet`, it cannot be accessed via S3 Gateway VPC Endpoint (requests are not routed to the FSx data plane). Use a VPC-origin S3 AP or configure NAT Gateway access. See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 鉄道事業法 (Railway Business Act), 運輸安全委員会設置法
