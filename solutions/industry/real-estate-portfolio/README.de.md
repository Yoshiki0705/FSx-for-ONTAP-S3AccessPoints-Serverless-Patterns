# UC26: Immobilien — Immobilienbildanalyse / Vertragsextraktion

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Anleitung](docs/demo-guide.de.md)

## Überblick

Ein Serverless-Workflow, der die S3 Access Points von FSx for ONTAP nutzt, um Merkmale aus Immobilienbildern zu extrahieren, Exposé-Beschreibungen automatisch zu generieren, Bedingungen aus Mietverträgen zu extrahieren und PII zum Schutz der Privatsphäre zu erkennen.

## Success Metrics

### Outcome
Automatisierung der Dokumentenverarbeitung und -analyse zur Steigerung der betrieblichen Effizienz und der Compliance.

### Metrics
| Metrik | Zielwert (Beispiel) |
|--------|--------------------|
| Genauigkeit der Immobilienmerkmalsextraktion | ≥ 85% |
| PII-Erkennungsrate | ≥ 95% |
| Genauigkeit der Vertragsbedingungsextraktion | ≥ 90% |
| Berichtserstellungszeit | < 5 Min / Batch |
| Kosten / tägliche Ausführung | < $2.50 |
| Erforderliche Human-Review-Quote | > 20% (alle Bilder mit erkannten PII werden geprüft) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Extraktionsergebnisse der AI/ML-Dienste, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Ergebnisse mit geringer Konfidenz erfordern eine manuelle Überprüfung
- Critical-Alarme werden von Fachexperten geprüft
- Regelmäßige Zusammenfassungsberichte werden vom Management geprüft

## Architektur

Detaillierte Datenflussdiagramme finden Sie im [Architekturdokument](docs/architecture.de.md).

## Voraussetzungen

> **Hinweis zu S3 AP NetworkOrigin**: Die Discovery-Lambda wird innerhalb eines VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Point `Internet` ist, ist der Zugriff über den S3 Gateway VPC Endpoint nicht möglich (die Anfragen werden nicht an die Datenebene von FSx for ONTAP geroutet). Verwenden Sie einen S3 AP mit NetworkOrigin=VPC oder konfigurieren Sie den Zugriff über ein NAT Gateway. Weitere Informationen finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- AWS-Konto mit geeigneten IAM-Berechtigungen
- FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- Volume mit aktiviertem S3 Access Point
- VPC, private Subnetze
- Aktivierter Zugriff auf Amazon-Bedrock-Modelle (Claude / Nova)
- Amazon Textract — Cross-Region (us-east-1) Aufrufkonfiguration

## Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-real-estate \
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

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit dem Befehl `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Verpacken der Lambda-Zip-Dateien und deren Upload in einen S3-Bucket).

## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **über NFS/SMB/S3 AP hinweg gemeinsam genutzt**. Eine parallele Verarbeitung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinträchtigen.
- Prüfen Sie bei der Stapelverarbeitung großer Dateimengen die Throughput Capacity (MBps) von FSx for ONTAP und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken (ThroughputUtilization) von FSx for ONTAP und erhöhen Sie den Wert schrittweise.

## Bereinigung

```bash
aws s3 rm s3://fsxn-real-estate-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-real-estate --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-real-estate --region ap-northeast-1
```

## Kostenschätzung (monatlich)

> **Hinweis**: Schätzungen für die Region ap-northeast-1. Die tatsächlichen Kosten hängen von der Nutzung ab.

| Konfiguration | Monatliche Schätzung |
|---------------|---------------------|
| Minimal (1x täglich) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Dieses Pattern bietet technische Architekturhinweise. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Mieterinformationen in Mietverträgen müssen gemäß den geltenden Datenschutzgesetzen verwaltet werden. Beim Umgang mit PII, die in Immobilienbildern erscheinen, sind zudem die Vorschriften für Immobilientransaktionen zu beachten.

> **Zugehörige Vorschriften**: 宅地建物取引業法 (Immobilienmaklergesetz), 個人情報保護法 (Datenschutzgesetz)

---

## S3AP Compatibility

Informationen zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Mustern der S3 Access Points for FSx for ONTAP finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
