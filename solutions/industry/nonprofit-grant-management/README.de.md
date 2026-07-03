# UC24: Gemeinnützige Organisationen — Klassifizierung von Förderanträgen / Ergebnisabgleich

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Übersicht

Ein serverloser Workflow, der die S3 Access Points von FSx for ONTAP nutzt, um Förderanträge automatisch zu klassifizieren, Antragstellerinformationen und Budgets zu extrahieren und Ergebnismetriken aus Tätigkeitsberichten mit den ursprünglichen Förderzielen abzugleichen.

## Success Metrics

### Outcome
Automatisierung der Dokumentenverarbeitung und -analyse zur Steigerung der betrieblichen Effizienz und der Compliance.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Genauigkeit der Förderantrags-Klassifizierung | ≥ 85% |
| Genauigkeit der Messung des Zielerreichungsgrads | ≥ 80% |
| Extraktionsrate der Antragsdaten | ≥ 90% |
| Zeit für die Berichtserstellung | < 5 Min. / Batch |
| Kosten / tägliche Ausführung | < $1.50 |
| Erforderliche Human-Review-Rate | > 25% (Klassifizierungsergebnisse mit geringer Konfidenz) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Extraktionsergebnisse der KI/ML-Dienste, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Ergebnisse mit geringer Konfidenz erfordern eine manuelle Überprüfung
- Critical-Warnungen werden von Fachexperten überprüft
- Regelmäßige Zusammenfassungsberichte werden vom Management überprüft

## Architektur

Ausführliche Datenflussdiagramme finden Sie im [Architekturdokument](docs/architecture.de.md).

## Voraussetzungen

> **Hinweis zu S3 AP NetworkOrigin**: Die Discovery-Lambda wird innerhalb einer VPC bereitgestellt. Wenn das NetworkOrigin des S3 Access Point `Internet` ist, kann nicht über einen S3 Gateway VPC Endpoint darauf zugegriffen werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen S3 AP mit NetworkOrigin=VPC oder konfigurieren Sie den Zugriff über ein NAT Gateway. Siehe [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- AWS-Konto mit geeigneten IAM-Berechtigungen
- FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- Volume mit aktiviertem S3 Access Point
- VPC, private Subnetze
- Aktivierter Zugriff auf Amazon-Bedrock-Modelle (Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1)-Aufrufkonfiguration

## Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build" paketiert Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-nonprofit-grants \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Hinweis**: `template.yaml` ist für die Verwendung mit SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Um direkt mit `aws cloudformation deploy` bereitzustellen, verwenden Sie stattdessen `template-deploy.yaml` (erfordert das Vorpaketieren der Lambda-ZIP-Dateien und deren Upload in einen S3-Bucket).

## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **zwischen NFS/SMB/S3 AP geteilt**. Eine parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinträchtigen.
- Prüfen Sie bei der Stapelverarbeitung großer Dateimengen die Throughput Capacity (MBps) von FSx for ONTAP und passen Sie MapConcurrency entsprechend an.
- Empfehlung: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken von FSx for ONTAP (ThroughputUtilization) und erhöhen Sie den Wert schrittweise.

## Bereinigung

```bash
aws s3 rm s3://fsxn-nonprofit-grants-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-nonprofit-grants --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-nonprofit-grants --region ap-northeast-1
```

## Kostenschätzung (monatlich)

> **Hinweis**: Schätzungen für ap-northeast-1. Die tatsächlichen Kosten variieren je nach Nutzung.

| Konfiguration | Monatliche Schätzung |
|------|---------|
| Minimal (täglich 1x) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Dieses Muster bietet technische Architekturhinweise. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Die Verarbeitung personenbezogener und organisationsbezogener Informationen in Förderanträgen muss den Vorschriften der jeweiligen Fördereinrichtung sowie den geltenden Datenschutzgesetzen entsprechen.

> **Zugehörige Vorschriften**: japanisches NPO-Gesetz (Gesetz zur Förderung spezifizierter gemeinnütziger Tätigkeiten), Gesetz zur Anerkennung gemeinnütziger Körperschaften

---

## S3AP Compatibility

Informationen zu Kompatibilitätseinschränkungen, Fehlerbehebung und Trigger-Mustern von FSx for ONTAP S3 AP finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
