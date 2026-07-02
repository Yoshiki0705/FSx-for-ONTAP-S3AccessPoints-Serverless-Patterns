# UC27: Personalwesen — Lebenslauf-Screening / PII-Striktmodus

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Anleitung](docs/demo-guide.de.md)

## Overview

A serverless workflow leveraging FSx for ONTAP S3 Access Points to extract structured skills and experience from resumes, with PII strict mode that excludes protected characteristics from scoring.

## Success Metrics

| Metric | Target |
|--------|--------|
| Resume data extraction rate | ≥ 90% |
| Scoring fairness | No protected characteristic bias (age/gender/nationality excluded) |
| PII compliance | 100% (zero PII in logs) |
| Report generation time | < 5 min / batch |
| Cost / daily execution | < $2.00 |
| Human review required rate | > 30% (all scoring results reviewed by HR team) |

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
  --stack-name fsxn-hr-screening \
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

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket).

## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **zwischen NFS/SMB/S3 AP geteilt**. Die parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinflussen.
- Bei der Verarbeitung großer Dateien prüfen Sie die FSx for ONTAP Throughput Capacity (MBps) und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken (ThroughputUtilization) und erhöhen Sie schrittweise.

## Cleanup

```bash
aws s3 rm s3://fsxn-hr-screening-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-hr-screening --region ap-northeast-1
```

---

## Governance Note

> This pattern provides technical architecture guidance only. It does not constitute legal, compliance, or regulatory advice. AI usage in recruitment screening must comply with employment laws and equal opportunity regulations, excluding bias based on protected characteristics (age, gender, nationality). AI scoring is advisory only; final decisions must be made by HR professionals.

> **Related Regulations**: 職業安定法 (Employment Security Act), 個人情報保護法 (APPI), 労働基準法 (Labor Standards Act)

---

## S3AP Compatibility

See [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
