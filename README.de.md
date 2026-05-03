# FSx for ONTAP S3 Access Points Serverless Patterns

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

Sammlung branchenspezifischer serverloser Automatisierungsmuster auf Basis von Amazon FSx for NetApp ONTAP S3 Access Points.

> **Positionierung dieses Repositories**: Dies ist eine „Referenzimplementierung zum Erlernen von Designentscheidungen". Einige Anwendungsfälle wurden in einer AWS-Umgebung vollständig E2E-verifiziert, während andere durch CloudFormation-Deployment, gemeinsames Discovery Lambda und Tests der Hauptkomponenten validiert wurden. Ziel ist es, Designentscheidungen zu Kostenoptimierung, Sicherheit und Fehlerbehandlung durch konkreten Code zu demonstrieren — mit einem Pfad vom PoC zur Produktion.

## Verwandter Artikel

Dieses Repository ist der praktische Begleiter zum folgenden Artikel:

- **FSx for ONTAP S3 Access Points as a Serverless Automation Boundary — AI Data Pipelines, Volume-Level SnapMirror DR, and Capacity Guardrails**
  https://dev.to/yoshikifujiwara/fsx-for-ontap-s3-access-points-as-a-serverless-automation-boundary-ai-data-pipelines-ili

Der Artikel erklärt die architektonischen Überlegungen und Kompromisse. Dieses Repository liefert konkrete, wiederverwendbare Implementierungsmuster.

## Überblick

Dieses Repository bietet **5 branchenspezifische Muster** für die serverlose Verarbeitung von Unternehmensdaten, die auf FSx for NetApp ONTAP über **S3 Access Points** gespeichert sind.

> Im Folgenden wird FSx for ONTAP S3 Access Points als **S3 AP** abgekürzt.

Jeder Anwendungsfall ist als eigenständiges CloudFormation-Template umgesetzt. Gemeinsam genutzte Module (ONTAP REST API Client, FSx Helper, S3 AP Helper) befinden sich in `shared/`.

### Hauptmerkmale

- **Polling-basierte Architektur**: EventBridge Scheduler + Step Functions (S3 AP unterstützt `GetBucketNotificationConfiguration` nicht)
- **Getrennte gemeinsame Module**: OntapClient / FsxHelper / S3ApHelper werden in allen Anwendungsfällen wiederverwendet
- **CloudFormation / SAM Transform basiert**: Jeder Anwendungsfall ist ein eigenständiges CloudFormation-Template mit SAM Transform
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

> ⚠️ **Auswirkungen auf die bestehende Umgebung**
>
> - `EnableS3GatewayEndpoint=true` fügt Ihrem VPC einen S3 Gateway Endpoint hinzu. Setzen Sie den Wert auf `false`, wenn bereits einer vorhanden ist.
> - `ScheduleExpression` löst periodische Step Functions-Ausführungen aus. Deaktivieren Sie den Zeitplan nach der Bereitstellung, wenn er nicht sofort benötigt wird.
> - Die Stack-Löschung kann fehlschlagen, wenn S3-Buckets Objekte enthalten. Leeren Sie die Buckets vor dem Löschen.
> - Die Löschung von VPC Endpoints dauert 5-15 Minuten. Die Freigabe von Lambda-ENIs kann die Löschung der Security Group verzögern.
>
> **Region**: Verwenden Sie `us-east-1` oder `us-west-2` für vollständige AI/ML-Dienstverfügbarkeit. Siehe [Regionskompatibilität](docs/region-compatibility.md).

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
    ParameterKey=PrivateRouteTableIds,ParameterValue=<your-route-table-ids> \
    ParameterKey=EnableS3GatewayEndpoint,ParameterValue=true \
    ParameterKey=EnableVpcEndpoints,ParameterValue=false
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
