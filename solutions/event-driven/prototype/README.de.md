🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

# Event-Driven Prototype (ereignisgesteuerter Prototyp)

## Überblick

Dieser Prototyp ist eine Referenzimplementierung einer ereignisgesteuerten
Dateiverarbeitungspipeline, die die künftige native Benachrichtigungsfunktion
von FSx for ONTAP S3 Access Points (FSx for ONTAP S3 AP) vorwegnimmt.

Er verwendet die Event Notifications eines regulären S3-Buckets, um das
künftige Verhalten der nativen Benachrichtigung von FSx for ONTAP S3 AP zu simulieren.

## Architektur

```
S3 Bucket (PutObject)
  → S3 Event Notification (EventBridge aktiviert)
    → EventBridge Rule (suffix: .jpg/.png, prefix: products/)
      → Step Functions (StartExecution)
        → Event Processor Lambda (Bildkennzeichnung + Metadatengenerierung)
          → Latency Reporter Lambda (EMF-Metrikausgabe)
```

## Zuordnung zur künftigen Unterstützung von FSx for ONTAP S3 AP

| Aktueller Prototyp | Künftiges FSx for ONTAP S3 AP |
|---|---|
| S3 Bucket + Event Notifications | FSx for ONTAP S3 AP + Native Notifications |
| Ereignisquelle `aws.s3` | Ereignisquelle `aws.fsx` (geplant) |
| Filterung nach S3-Bucket-Namen | Filterung nach S3-AP-Alias |
| Lesen über S3 GetObject | Lesen über S3 AP |

## Erforderliche Änderungen (bei Unterstützung nativer Benachrichtigungen)

Änderungen, die erforderlich sind, sobald FSx for ONTAP S3 AP native Benachrichtigungen unterstützt:

### 1. Vorlagenänderungen

```yaml
# Vorher (Prototyp)
SourceBucket:
  Type: AWS::S3::Bucket
  Properties:
    NotificationConfiguration:
      EventBridgeConfiguration:
        EventBridgeEnabled: true

# Nachher (FSx for ONTAP S3 AP)
# Die S3-Bucket-Ressource entfernen und das vorhandene FSx for ONTAP S3 AP referenzieren
# Den Quellfilter der EventBridge Rule aktualisieren
```

### 2. Änderungen an der EventBridge-Regel

```json
// Vorher
{"source": ["aws.s3"], "detail": {"bucket": {"name": ["prototype-bucket"]}}}

// Nachher (geplant)
{"source": ["aws.fsx"], "detail": {"bucket": {"name": ["fsxn-s3ap-alias"]}}}
```

### 3. Änderungen an den Lambda-Umgebungsvariablen

```yaml
# Vorher
SOURCE_BUCKET: !Ref SourceBucket

# Nachher
S3_ACCESS_POINT: !Ref S3AccessPointAlias
```

### 4. Änderungen am Lambda-Code

```python
# Vorher (Prototyp)
response = s3_client.get_object(Bucket=source_bucket, Key=file_key)

# Nachher (FSx for ONTAP S3 AP)
from shared.s3ap_helper import S3ApHelper
s3ap = S3ApHelper(os.environ["S3_ACCESS_POINT"])
response = s3ap.get_object(file_key)
```

## Bereitstellungsschritte

### Voraussetzungen

- AWS CLI konfiguriert
- Python 3.12
- S3-Bucket für das Lambda-Bereitstellungspaket

### Bereitstellung

```bash
# 1. Lambda-Paket erstellen und hochladen
# (ausgelassen: durch die CI/CD-Pipeline automatisiert)

# 2. SAM-Stack bereitstellen
# Voraussetzung: AWS SAM CLI ist erforderlich. sam build paketiert den Code und die gemeinsamen Layer automatisch.
sam build

sam deploy \
  --stack-name event-driven-prototype \
  --parameter-overrides \
    NotificationEmail=<email> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3

# 3. Testdatei hochladen
aws s3 cp test-image.jpg \
  s3://<source-bucket>/products/test-image.jpg
```

### Tests ausführen

```bash
# Unittests
pytest event-driven-prototype/tests/ -v

# Latenzvergleichstest (nach der Bereitstellung)
python scripts/compare_polling_vs_event.py \
  --polling-bucket <uc11-source> \
  --event-bucket <prototype-source> \
  --output-bucket <output-bucket> \
  --test-files 10
```

## Verzeichnisstruktur

```
event-driven-prototype/
├── template-deploy.yaml          # CloudFormation-Vorlage
├── lambdas/
│   ├── event_processor/
│   │   └── handler.py            # Ereignisverarbeitungs-Lambda (UC11-kompatibel)
│   └── latency_reporter/
│       └── handler.py            # Latenzmessungs-Lambda
├── tests/
│   ├── test_event_processor.py   # Unittests der Ereignisverarbeitung
│   ├── test_latency_reporter.py  # Unittests der Latenzmessung
│   └── test_event_processing_properties.py  # Property-Based Tests
└── README.md                     # Dieses Dokument
```

## Metriken

Die folgenden Metriken werden im CloudWatch-EMF-Format ausgegeben:

| Metrikname | Einheit | Beschreibung |
|---|---|---|
| `EventToProcessingLatency` | Milliseconds | Ereigniseintritt → Verarbeitungsbeginn |
| `EndToEndDuration` | Milliseconds | Ereigniseintritt → Verarbeitungsabschluss |
| `ProcessingDuration` | Milliseconds | Ausführungszeit der Verarbeitung |
| `EventVolumePerMinute` | Count | Pro Minute verarbeitete Ereignisse |

## Zugehörige Dokumente

- [Entwurf der ereignisgesteuerten Architektur](../docs/event-driven/architecture-design.md)
- [Migrationsleitfaden](../docs/event-driven/migration-guide.md)
- [UC11 Retail Catalog](../retail-catalog/README.md)
