# FSxN S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Sammlung branchenspezifischer serverloser Automatisierungsmuster auf Basis von Amazon FSx for NetApp ONTAP S3 Access Points.

## Überblick

Dieses Repository bietet **5 branchenspezifische Muster** für die serverlose Verarbeitung von Unternehmensdaten, die auf FSx for NetApp ONTAP über **S3 Access Points** gespeichert sind.

Jeder Anwendungsfall ist als eigenständiges CloudFormation-Template umgesetzt. Gemeinsam genutzte Module (ONTAP REST API Client, FSx Helper, S3 AP Helper) befinden sich in `shared/`.

### Hauptmerkmale

- **Polling-basierte Architektur**: EventBridge Scheduler + Step Functions (FSx ONTAP S3 AP unterstützt `GetBucketNotificationConfiguration` nicht)
- **Getrennte gemeinsame Module**: OntapClient / FsxHelper / S3ApHelper werden in allen Anwendungsfällen wiederverwendet
- **CloudFormation-nativ**: Jeder Anwendungsfall ist ein eigenständiges CloudFormation-Template
- **Sicherheit zuerst**: TLS-Verifizierung standardmäßig aktiviert, IAM mit minimalen Berechtigungen, KMS-Verschlüsselung
- **Kostenoptimiert**: Kostenintensive Dauerressourcen (VPC Endpoints usw.) sind optional

## Anwendungsfälle

| # | Verzeichnis | Branche | Muster | AI/ML-Dienste | Regionskompatibilität |
|---|-------------|---------|--------|---------------|----------------------|
| UC1 | `legal-compliance/` | Recht und Compliance | Dateiserver-Audit und Data Governance | Athena, Bedrock | Alle Regionen |
| UC2 | `financial-idp/` | Finanzdienstleistungen | Vertrags-/Rechnungsverarbeitung (IDP) | Textract ⚠️, Comprehend, Bedrock | Textract: regionsübergreifend |
| UC3 | `manufacturing-analytics/` | Fertigung | IoT-Sensorprotokolle und Qualitätsprüfung | Athena, Rekognition | Alle Regionen |
| UC4 | `media-vfx/` | Medien und Unterhaltung | VFX-Rendering-Pipeline | Rekognition, Deadline Cloud | Deadline Cloud-Regionen |
| UC5 | `healthcare-dicom/` | Gesundheitswesen | DICOM-Bildklassifizierung und Anonymisierung | Rekognition, Comprehend Medical ⚠️ | Comprehend Medical: regionsübergreifend |

> **Regionale Einschränkungen**: Amazon Textract und Amazon Comprehend Medical sind nicht in allen Regionen verfügbar (z. B. ap-northeast-1). Regionsübergreifende Aufrufe werden über die Parameter `TEXTRACT_REGION` und `COMPREHEND_MEDICAL_REGION` unterstützt. Siehe [Regionskompatibilitätsmatrix](docs/region-compatibility.md).

## Schnellstart

### Voraussetzungen

- AWS CLI v2
- Python 3.12+
- FSx for NetApp ONTAP mit aktivierten S3 Access Points
- ONTAP-Anmeldedaten in AWS Secrets Manager

### Bereitstellung

```bash
# Region festlegen
export AWS_DEFAULT_REGION=us-east-1

# Lambda-Funktionen paketieren
./scripts/deploy_uc.sh legal-compliance package

# CloudFormation-Stack bereitstellen
aws cloudformation create-stack \
  --stack-name fsxn-legal-compliance \
  --template-body file://legal-compliance/template-deploy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DeployBucket,ParameterValue=<your-deploy-bucket> \
    ParameterKey=S3AccessPointAlias,ParameterValue=<your-s3ap-alias> \
    ...
```

## Dokumentation

| Dokument | Beschreibung |
|----------|-------------|
| [Bereitstellungsleitfaden](docs/guides/deployment-guide.md) | Schritt-für-Schritt-Bereitstellungsanleitung |
| [Betriebsleitfaden](docs/guides/operations-guide.md) | Überwachungs- und Betriebsverfahren |
| [Fehlerbehebungsleitfaden](docs/guides/troubleshooting-guide.md) | Häufige Probleme und Lösungen |
| [Kostenanalyse](docs/cost-analysis.md) | Kostenstruktur und Optimierung |
| [Regionskompatibilität](docs/region-compatibility.md) | Dienstverfügbarkeit nach Region |
| [Erweiterungsmuster](docs/extension-patterns.md) | Bedrock KB, Transfer Family SFTP, EMR Serverless |
| [Verifizierungsergebnisse](docs/verification-results.md) | AWS-Umgebungstestergebnisse |

## Technologie-Stack

| Schicht | Technologie |
|---------|------------|
| Sprache | Python 3.12 |
| IaC | CloudFormation (YAML) |
| Compute | AWS Lambda |
| Orchestrierung | AWS Step Functions |
| Planung | Amazon EventBridge Scheduler |
| Speicher | FSx for ONTAP (S3 AP) |
| AI/ML | Bedrock, Textract, Comprehend, Rekognition |
| Sicherheit | Secrets Manager, KMS, IAM minimale Berechtigungen |
| Tests | pytest + Hypothesis (PBT) |

## Lizenz

MIT License. Siehe [LICENSE](LICENSE) für Details.
