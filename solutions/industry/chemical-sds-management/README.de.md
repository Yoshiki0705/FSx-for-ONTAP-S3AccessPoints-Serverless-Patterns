# UC28: Chemie und Werkstoffe — SDS-Gefahrenextraktion / GHS-Validierung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architekturdiagramm](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Überblick

Ein Serverless-Workflow, der FSx for ONTAP S3 Access Points nutzt, um Gefahrenklassifizierungen und Handhabungshinweise aus Sicherheitsdatenblättern (SDS) zu extrahieren, die Vollständigkeit der GHS-Pflichtabschnitte zu validieren und Versuchsdaten aus Laborbuch-Bildern zu extrahieren.

## Success Metrics

### Outcome
Automatisierung der Dokumentenverarbeitung und -analyse zur Steigerung der Betriebseffizienz und Compliance.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Vollständigkeit der GHS-Abschnittsvalidierung | 100 % (8 Pflichtabschnitte geprüft) |
| Erkennungsrate abgelaufener SDS | 100 % |
| Genauigkeit der Gefahrenklassifizierungsextraktion | ≥ 90 % |
| Zeit für die Berichterstellung | < 5 Min / Batch |
| Kosten / tägliche Ausführung | < $2.50 |
| Erforderliche Human-Review-Quote | > 25 % (alle Alarme mit Priorität Critical geprüft) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Extraktionsergebnisse der AI/ML-Services, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Ergebnisse mit geringer Konfidenz erfordern eine manuelle Prüfung
- Critical-Alarme werden von Fachexperten geprüft
- Regelmäßige Zusammenfassungsberichte werden vom Management geprüft

## Architektur

Ausführliche Datenflussdiagramme finden Sie im [Architekturdokument](docs/architecture.de.md).

## Voraussetzungen

> **Hinweis zu S3 AP NetworkOrigin**: Die Discovery-Lambda wird innerhalb einer VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Point `Internet` ist, ist kein Zugriff über den S3 Gateway VPC Endpoint möglich (Anfragen werden nicht an die FSx-Datenebene geroutet). Verwenden Sie einen S3 AP mit NetworkOrigin=VPC oder konfigurieren Sie den Zugriff über ein NAT Gateway. Siehe [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- AWS-Konto mit geeigneten IAM-Berechtigungen
- FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- S3 Access Point auf dem Volume aktiviert
- VPC, private Subnetze
- Amazon-Bedrock-Modellzugriff aktiviert (Claude / Nova)
- Amazon Textract — Cross-Region-Aufrufkonfiguration (us-east-1)

## Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. "sam build" verpackt den Code und den Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-chemical-sds \
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

> **Hinweis**: `template.yaml` ist für die Verwendung mit der SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Verpacken der Lambda-Zip-Dateien und deren Upload in einen S3-Bucket).

## ⚠️ Leistungshinweise

- Die Durchsatzkapazität von FSx for ONTAP wird **gemeinsam über NFS/SMB/S3 AP genutzt**. Eine parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinträchtigen.
- Prüfen Sie bei der Stapelverarbeitung großer Dateimengen die Throughput Capacity (MBps) von FSx for ONTAP und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken von FSx for ONTAP (ThroughputUtilization) und erhöhen Sie den Wert schrittweise.

## Bereinigung

```bash
aws s3 rm s3://fsxn-chemical-sds-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-chemical-sds --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-chemical-sds --region ap-northeast-1
```

## Kostenschätzung (monatlich)

> **Hinweis**: Schätzung für die Region ap-northeast-1. Die tatsächlichen Kosten variieren je nach Nutzung.

| Konfiguration | Monatliche Schätzung |
|------|---------|
| Minimalkonfiguration (1x täglich) | ~$8-20 |
| Standardkonfiguration | ~$20-50 |

---

## Governance Note

> Dieses Muster bietet technische Architekturleitlinien. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Die Handhabung von Informationen zu chemischen Stoffen in SDS muss den geltenden Gesetzen zum Chemikalienmanagement und zum Arbeitsschutz entsprechen. Die endgültige GHS-Klassifizierung muss von qualifizierten Fachkräften für Chemikaliensicherheit vorgenommen werden.

> **Zugehörige Vorschriften**: Gesetz zur Förderung des Managements chemischer Stoffe (PRTR-Gesetz), Arbeitsschutzgesetz, Brandschutzgesetz

---

## S3AP Compatibility

Informationen zu Kompatibilitätseinschränkungen, Fehlerbehebung und Trigger-Mustern von FSx for ONTAP S3 Access Points finden Sie unter [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
