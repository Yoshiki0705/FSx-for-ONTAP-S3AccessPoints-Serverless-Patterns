# UC24: Gemeinnützige Organisationen — Förderantragsklassifizierung / Ergebniszuordnung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Anleitung](docs/demo-guide.de.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to automatically classify grant applications, extract applicant information and budgets, and match outcome metrics from activity reports against original grant objectives.

## Success Metrics

| Metric | Target |
|--------|--------|
| Grant application classification accuracy | ≥ 85% |
| Outcome achievement measurement accuracy | ≥ 80% |
| Application data extraction rate | ≥ 90% |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $1.50 |
| Human review required rate | > 25% (low-confidence classifications) |

## Architecture

See [Architecture Document](docs/architecture.de.md) for detailed data flow diagrams.

## Prerequisites

- AWS account with appropriate IAM permissions
- FSx for ONTAP file system (ONTAP 9.17.1P4D3+)
- S3 Access Point enabled on volume
- Amazon Bedrock model access enabled
- Amazon Textract — Cross-Region (us-east-1)

> **S3 AP NetworkOrigin Hinweis**: Die Discovery Lambda wird innerhalb eines VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Points `Internet` ist, kann über S3 Gateway VPC Endpoint nicht zugegriffen werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen VPC-origin S3 AP oder konfigurieren Sie NAT Gateway-Zugriff. Siehe [S3AP-Kompatibilitätshinweise](../docs/s3ap-compatibility-notes.md).

## Deployment

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```


## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **zwischen NFS/SMB/S3 AP geteilt**. Die parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinflussen.
- Bei der Verarbeitung großer Dateien prüfen Sie die FSx for ONTAP Throughput Capacity (MBps) und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken (ThroughputUtilization) und erhöhen Sie schrittweise.

## Cleanup

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. Handling of personal and organizational information in grant applications must comply with each funding agency's regulations and applicable privacy laws.

> **Related Regulations**: NPO 法, 公益法人認定法 (Public Interest Corporation Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
