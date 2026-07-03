# UC25: Energie & Versorgung — Drohnen-Bildinspektion / SCADA-Anomalieerkennung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Leitfaden](docs/demo-guide.de.md)

## Überblick

Ein Serverless-Workflow, der FSx for ONTAP S3 Access Points nutzt, um Anlagendefekte aus Drohnen-Inspektionsbildern von Übertragungsanlagen zu erkennen, Anomalien in SCADA-Zeitreihenprotokollen zu identifizieren und Hotspots aus FLIR-Wärmebildern zu analysieren.

## Success Metrics

### Outcome
Dokumentenverarbeitung und -analyse automatisieren, um die betriebliche Effizienz und Compliance zu verbessern.

### Metrics
| Kennzahl | Zielwert (Beispiel) |
|-----------|------------|
| Fehlererkennungsrate | ≥ 85% |
| Falsch-Positiv-Rate bei SCADA-Anomalien | < 10% |
| Genauigkeit der thermischen Hotspot-Erkennung | ≥ 90% |
| Berichterstellungszeit | < 5 Min / Batch |
| Kosten / tägliche Ausführung | < $3.00 |
| Erforderliche Human-Review-Rate | > 30% (alle Erkennungen der Schwere Critical werden geprüft) |

### Measurement Method
Step-Functions-Ausführungsverlauf, Extraktionsergebnisse der AI/ML-Dienste, CloudWatch EMF Metrics (ProcessingDuration, SuccessCount, ErrorCount).

### Human Review Requirements
- Ergebnisse mit niedriger Konfidenz erfordern eine manuelle Überprüfung
- Critical-Warnungen werden von Fachexperten geprüft
- Regelmäßige Zusammenfassungsberichte werden vom Management geprüft

## Architektur

Ausführliche Datenflussdiagramme finden Sie im [Architekturdokument](docs/architecture.de.md).

## Voraussetzungen

> **Hinweis zu S3 AP NetworkOrigin**: Die Discovery-Lambda wird innerhalb einer VPC bereitgestellt. Wenn der NetworkOrigin des S3 Access Point `Internet` ist, kann er nicht über den S3 Gateway VPC Endpoint erreicht werden (Anfragen werden nicht an die FSx-Datenebene weitergeleitet). Verwenden Sie einen S3 AP mit NetworkOrigin=VPC oder konfigurieren Sie den Zugriff über ein NAT Gateway. Siehe [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).

- AWS-Konto mit geeigneten IAM-Berechtigungen
- FSx for ONTAP-Dateisystem (ONTAP 9.17.1P4D3 oder höher)
- S3 Access Point auf dem Volume aktiviert
- VPC mit privaten Subnetzen
- Zugriff auf Amazon Bedrock-Modelle aktiviert (Claude / Nova)

## Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. 'sam build' paketiert den Code und den Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-utilities-inspection \
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

> **Hinweis**: `template.yaml` ist für die Verwendung mit der SAM CLI (`sam build` + `sam deploy`) konzipiert.
> Für die direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das Vorpaketieren der Lambda-Zip-Dateien und deren Upload in einen S3-Bucket).

## ⚠️ Hinweise zur Performance

- Die Durchsatzkapazität von FSx for ONTAP wird **über NFS/SMB/S3 AP gemeinsam genutzt**. Die parallele Ausführung mit MapConcurrency=10 kann andere Workloads auf demselben Volume beeinträchtigen.
- Prüfen Sie bei der Stapelverarbeitung großer Dateimengen die Throughput Capacity (MBps) von FSx for ONTAP und passen Sie MapConcurrency entsprechend an.
- Empfohlen: Beginnen Sie in der Produktion mit MapConcurrency=5, überwachen Sie die CloudWatch-Metriken von FSx for ONTAP (ThroughputUtilization) und erhöhen Sie den Wert schrittweise.

## Bereinigung

```bash
aws s3 rm s3://fsxn-utilities-inspection-output-${AWS_ACCOUNT_ID} --recursive
aws cloudformation delete-stack --stack-name fsxn-utilities-inspection --region ap-northeast-1
aws cloudformation wait stack-delete-complete --stack-name fsxn-utilities-inspection --region ap-northeast-1
```

## Kostenschätzung (monatlich)

> **Anmerkung**: Schätzungen für ap-northeast-1. Die tatsächlichen Kosten variieren je nach Nutzung.

| Konfiguration | Monatliche Schätzung |
|------|---------|
| Minimal (täglich 1x) | ~$8-20 |
| Standard | ~$20-50 |

---

## Governance Note

> Dieses Pattern bietet technische Architekturhinweise. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. SCADA-Daten sind Informationen kritischer Infrastruktur. Zugriffsverwaltung und die Aufbewahrung von Audit-Protokollen müssen den geltenden Vorschriften für das Elektrizitätsgeschäft und den Richtlinien zum Schutz kritischer Infrastrukturen entsprechen.

> **Zugehörige Vorschriften**: Elektrizitätswirtschaftsgesetz (電気事業法), Technische Normen für elektrische Anlagen (電気設備技術基準)

---

## S3AP Compatibility

Informationen zu Kompatibilitätseinschränkungen, Fehlerbehebung und Trigger-Mustern von FSx for ONTAP S3 Access Points finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
