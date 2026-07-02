# UC20: Reise & Gastgewerbe — Reservierungsdokumentverarbeitung / Gebäudeinspektions-Bildanalyse

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Überblick

Ein serverloser Workflow, der FSx for ONTAP S3 Access Points nutzt, um automatisch strukturierte Daten aus Hotel-Reservierungsdokumenten (PDF, gescannte Bilder) zu extrahieren und Gebäudezustandsanalysen sowie Wartungsempfehlungen aus Inspektionsbildern zu generieren.

### Hauptfunktionen

- Automatische Erkennung von Reservierungsdokumenten und Inspektionsbildern über S3 AP
- Textract + Comprehend strukturierte Datenextraktion (Gastname, Daten, Zimmertyp, Betrag)
- Mehrsprachige Unterstützung (Spracherkennung → Textract-Hinweise + automatische Comprehend-Modellauswahl)
- Rekognition Gebäudezustandsanalyse (Schadenserkennung, Sauberkeitsbewertung 0–100)
- Bedrock Wartungsempfehlungsgenerierung

## Success Metrics

| Metrik | Zielwert |
|--------|----------|
| Genauigkeit der Reservierungsdatenextraktion | ≥ 90% |
| Erkennungsrate des Gebäudezustands | ≥ 85% |
| Mehrsprachige Abdeckung | ≥ 5 Sprachen |
| Berichtserstellungszeit | < 5 Min / Batch |
| Quote menschlicher Überprüfung | > 15% |


## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **zwischen NFS/SMB/S3 AP geteilt**. Die parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinflussen.
- Bei der Verarbeitung großer Dateien prüfen Sie die FSx for ONTAP Throughput Capacity (MBps) und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken (ThroughputUtilization) und erhöhen Sie schrittweise.

## Bereitstellung

Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter-Parameter für Ihre Umgebung):

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-travel-processing \
  --parameter-overrides \
    S3AccessPointAlias=<your-volume-ext-s3alias> \
    S3AccessPointName=<your-s3ap-name> \
    VpcId=<your-vpc-id> \
    PrivateSubnetIds=<subnet-1>,<subnet-2> \
    ScheduleExpression="cron(0 0 * * ? *)" \
    NotificationEmail=<your-email@example.com> \
    EnableVpcEndpoints=false \
    EnableCloudWatchAlarms=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region ap-northeast-1
```

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket).

## Governance-Hinweis

> Dieses Muster bietet technische Architekturberatung. Es stellt keine Rechts-, Compliance- oder Regulierungsberatung dar.

> **S3 AP NetworkOrigin Hinweis**: Die Discovery Lambda wird innerhalb eines VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Points `Internet` ist, kann über S3 Gateway VPC Endpoint nicht zugegriffen werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen VPC-origin S3 AP oder konfigurieren Sie NAT Gateway-Zugriff. Siehe [S3AP-Kompatibilitätshinweise](../docs/s3ap-compatibility-notes.md).

> **Related Regulations**: 旅行業法 (Travel Agency Act), 個人情報保護法 (APPI)
