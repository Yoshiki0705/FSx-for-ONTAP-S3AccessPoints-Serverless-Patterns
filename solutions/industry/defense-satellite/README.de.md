# UC15: Verteidigung / Raumfahrt — Pipeline zur Satellitenbildanalyse

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)
📚 **Dokumentation**: [Architektur](docs/architecture.de.md) | [Demo-Skript](docs/demo-guide.de.md) | [Fehlerbehebung](../docs/phase7-troubleshooting.md)

## Überblick

Automatisierte Analysepipeline für Satellitenbilder (SAR / optisch), die
Amazon FSx for NetApp ONTAP S3 Access Points nutzt. Große Satellitenbilddaten werden
auf FSx for ONTAP gespeichert, und die serverlose Verarbeitung wird über
S3 Access Points ausgeführt.

## Anwendungsfall

Verteidigungs- und Nachrichtendienste sowie raumfahrtbezogene Organisationen
verarbeiten und analysieren automatisch die von Satelliten erfassten
Erdbeobachtungsdaten (Earth Observation).

### Verarbeitungsablauf

```
FSx for ONTAP (Satellitenbild-Speicher)
  → S3 Access Point
    → Step Functions Workflow
      → Discovery: neue Bilder erkennen (GeoTIFF, NITF, HDF5)
      → Tiling: große Bilder in Kacheln aufteilen (Cloud Optimized GeoTIFF-Konvertierung)
      → ObjectDetection: Objekterkennung mit Rekognition / SageMaker
      → ChangeDetection: Veränderungserkennung durch Zeitreihenvergleich
      → GeoEnrichment: Metadaten anreichern (Koordinaten, Aufnahmezeitpunkt, Auflösung)
      → AlertGeneration: Alarmerzeugung bei Anomalieerkennung
```

### Zieldaten

| Datenformat | Beschreibung | Typische Größe |
|-----------|------|-----------|
| GeoTIFF | Optisches Satellitenbild | 100 MB – 10 GB |
| NITF | Militärisches Standard-Bildformat | 500 MB – 50 GB |
| HDF5 | SAR-Daten (Sentinel-1 usw.) | 1 – 5 GB |
| Cloud Optimized GeoTIFF (COG) | Bereits gekacheltes Bild | 10 – 500 MB |

### AWS-Services

| Service | Verwendung |
|---------|------|
| FSx for ONTAP | Persistenter Speicher für Satellitenbilder (Zugriffssteuerung über NTFS ACL) |
| S3 Access Points | Bildzugriff aus dem Serverless |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Kachelaufteilung, Metadatenextraktion, Alarmerzeugung |
| SageMaker (Batch Transform) | ML-Inferenz für Objekt- / Veränderungserkennung |
| Amazon Rekognition | Labelerkennung (Fahrzeuge, Gebäude, Schiffe) |
| Amazon Bedrock | Bildunterschrift-Erzeugung, Berichtszusammenfassung |
| DynamoDB | Verwaltung des Verarbeitungsstatus, Index der Erkennungsergebnisse |
| SNS | Alarmbenachrichtigung |
| CloudWatch | Observability |

### Public-Sector-Eignung

- **DoD CC SRG**: FSx for ONTAP ist Impact Level 2/4/5 zertifiziert (GovCloud)
- **CSfC**: NetApp ONTAP ist Commercial Solutions for Classified zertifiziert
- **FedRAMP**: FedRAMP High konform in AWS GovCloud
- **Datensouveränität**: Daten bleiben innerhalb der Region (ap-northeast-1 / us-gov-west-1)

## Verifizierte Bildschirme (Screenshots)

Mit Fokus auf **die UI, die allgemeine Mitarbeitende im Alltag bedienen**, basierend auf
einer am 2026-05-10 in ap-northeast-1 verifizierten Live-Ausführung. Für technische
Konsolenansichten (Step-Functions-Graphen usw.) siehe
[docs/verification-results-phase7.md](../docs/verification-results-phase7.md).

### 1. Satellitenbild-Platzierung (über FSx for ONTAP / S3 Access Point)

Der Bestätigungsbildschirm für die Platzierung der zu analysierenden Satellitenbilder aus
Sicht des Dateiserver-Administrators. Es genügt, neue Bilder unter dem Präfix
`satellite/YYYY/MM/` abzulegen, und der periodische Step Functions Workflow nimmt sie
automatisch auf.

<!-- SCREENSHOT: phase7-uc15-s3-satellite-uploaded.png
     Inhalt: satellite/2026/05/*.tif über S3 AP auflisten (Objektname, Größe, Änderungszeit)
     Maskieren: Konto-ID, Access-Point-ARN, echte Satellitenbildnamen -->
![UC15: Satellitenbild-Platzierung](../docs/screenshots/masked/phase7/phase7-uc15-s3-satellite-uploaded.png)

### 2. Anzeige der Analyseergebnisse (S3 Output-Bucket)

Erkennungsergebnisse (`detections/*.json`), Geo-Metadaten (`enriched/*.json`) und
Kachelinformationen (`tiles/*/metadata.json`) werden geordnet gespeichert.

<!-- SCREENSHOT: phase7-uc15-s3-output-bucket.png
     Inhalt: Überblick über die 3 Präfixe detections/, enriched/, tiles/ in der S3-Konsole
     Maskieren: Konto-ID, Bucket-Namenspräfix -->
![UC15: S3 Output-Bucket](../docs/screenshots/masked/phase7/phase7-uc15-s3-output-bucket.png)

### 3. Veränderungs-Alarm (SNS-E-Mail-Benachrichtigung)

Die SNS-Alarm-E-Mail, die allgemeine Mitarbeitende (Operatoren) erhalten. Wird automatisch
gesendet, wenn die Veränderungsfläche den Schwellenwert (Standard 1 km²) überschreitet.

<!-- SCREENSHOT: phase7-uc15-sns-alert-email.png
     Inhalt: alert_type=SATELLITE_CHANGE_DETECTED in einem E-Mail-Client (Gmail/Outlook) anzeigen
     Maskieren: E-Mail-Adresse des Empfängers, Absenderadresse, echte Koordinaten, tile_id -->
![UC15: SNS-Alarm-E-Mail](../docs/screenshots/masked/phase7/phase7-uc15-sns-alert-email.png)

### 4. Inhalt der Erkennungsergebnis-JSON

Ein sauberer JSON-Viewer der Erkennungsergebnisse (Label, Konfidenz, bbox).

<!-- SCREENSHOT: phase7-uc15-detections-json.png
     Inhalt: Objektvorschau in der S3-Konsole, Inhalt der detections-JSON
     Maskieren: Konto-ID -->
![UC15: Erkennungsergebnisse JSON](../docs/screenshots/masked/phase7/phase7-uc15-detections-json.png)


## Success Metrics

### Outcome
Durch die Automatisierung der Satellitenbildanalyse (Objekterkennung, Veränderungserkennung, Alarme) wird eine schnellere Nachrichtenanalyse erreicht.

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Verarbeitete Bilder / Ausführung | > 50 images |
| Objekterkennungsgenauigkeit | > 80% |
| Erfolgsrate der Veränderungserkennung | > 85% |
| Alarmerzeugungszeit | < 5 Min. |
| Kosten / Ausführung | < $15 |
| Human-Review-Pflichtquote | 100% (menschliche Freigabe vor Alarmversand erforderlich) |

> **Grund für 100% Human Review**: Da die geschäftlichen Auswirkungen eines Fehl- oder verpassten Alarms extrem groß sind, ist die menschliche Freigabe aller Elemente verpflichtend.

### Measurement Method
Step-Functions-Ausführungsverlauf, Rekognition-Erkennungsergebnisse, Bedrock-Analyseberichte, SNS-Benachrichtigungsprotokolle und CloudWatch Metrics. Freigabeeinträge werden in DynamoDB gespeichert, damit bei einem Audit nachvollziehbar ist, „wer wann was freigegeben hat".

## Bereitstellung

### Vorabprüfung

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-Shot-Bereitstellung

```bash
bash scripts/deploy_phase7.sh defense-satellite
```

### Manuelle Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. sam build verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-defense-satellite \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

**Wichtig**: `S3AccessPointName` ist für die Erteilung von IAM-Berechtigungen an den S3 AP erforderlich.
Details siehe [`docs/phase7-troubleshooting.md`](../docs/phase7-troubleshooting.md).

## Verzeichnisstruktur

```
defense-satellite/
├── template.yaml              # SAM-Vorlage (Entwicklung)
├── template-deploy.yaml       # CloudFormation-Vorlage (Bereitstellung)
├── functions/
│   ├── discovery/handler.py   # Erkennung neuer Satellitenbilder
│   ├── tiling/handler.py      # Kachelaufteilung + COG-Konvertierung
│   ├── object_detection/handler.py  # Objekterkennung (Rekognition / SageMaker)
│   ├── change_detection/handler.py  # Zeitreihen-Veränderungserkennung
│   ├── geo_enrichment/handler.py    # Anreicherung von Geo-Metadaten
│   └── alert_generation/handler.py  # Alarmerzeugung
├── tests/                     # 31 pytest + 3 resilience tests
└── README.md
```


---

## AWS-Dokumentationslinks

| Service | Dokumentation |
|---------|------------|
| FSx for ONTAP | [Benutzerhandbuch](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Entwicklerhandbuch](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Rekognition | [Entwicklerhandbuch](https://docs.aws.amazon.com/rekognition/latest/dg/what-is.html) |
| Amazon SageMaker | [Entwicklerhandbuch](https://docs.aws.amazon.com/sagemaker/latest/dg/whatis.html) |
| AWS GovCloud | [Benutzerhandbuch](https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/welcome.html) |

### Well-Architected-Framework-Ausrichtung

| Säule | Ausrichtung |
|----|------|
| Operative Exzellenz | X-Ray, EMF, Alarmerzeugung, 100% Human Review |
| Sicherheit | DoD CC SRG, FedRAMP, IAM mit geringsten Rechten, KMS, VPC-Isolation |
| Zuverlässigkeit | Step Functions Retry/Catch, Resilienztests, Fallback |
| Leistungseffizienz | COG-Kachelung, parallele Objekterkennung, SageMaker Batch |
| Kostenoptimierung | Serverless, SageMaker Spot, Verarbeitung pro Kachel |
| Nachhaltigkeit | On-Demand-Ausführung, differenzielle Veränderungserkennung |





---

## Kostenschätzung (monatlicher Näherungswert)

> **Hinweis**: Die folgenden Werte sind Näherungswerte für die Region ap-northeast-1; die tatsächlichen Kosten variieren je nach Nutzung. Prüfen Sie die aktuellen Preise im [AWS Pricing Calculator](https://calculator.aws/).

### Serverlose Komponenten (nutzungsbasierte Abrechnung)

| Service | Stückpreis | Angenommene Nutzung | Monatlicher Näherungswert |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 6 Funktionen × 10 scenes/Tag | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/Tag | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/Tag | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~30K tokens/Ausführung | ~$3-10 |
| Athena | $5/TB scanned | ~20 MB/Abfrage | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/Tag | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/Monat | ~$0.76 |
| SageMaker Inference | $0.046/hour (ml.m5.large) |


### Fixkosten (FSx for ONTAP — bestehende Umgebung vorausgesetzt)

| Komponente | Monatlich |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (gemeinsame bestehende Umgebung) |
| S3 Access Point | Keine zusätzlichen Gebühren (nur S3-API-Gebühren) |

### Gesamt-Näherungswert

| Konfiguration | Monatlicher Näherungswert |
|------|---------|
| Minimalkonfiguration (täglich einmal) | ~$5-15 |
| Standardkonfiguration (stündlich) | ~$15-50 |
| Großkonfiguration (hohe Frequenz + Alarme) | ~$50-150 |

> **Governance Caveat**: Kostenschätzungen sind Näherungswerte, keine garantierten Werte. Der tatsächlich abgerechnete Betrag variiert je nach Nutzungsmuster, Datenvolumen und Region.

---

## Lokales Testen

### Prüfung der Voraussetzungen

```bash
# Voraussetzungen prüfen
aws --version          # AWS CLI v2
sam --version          # SAM CLI
python3 --version      # Python 3.9+
docker --version       # Docker (für sam local)
aws sts get-caller-identity  # AWS-Anmeldeinformationen
```

### sam local invoke

```bash
# Build
# Voraussetzung: AWS SAM CLI erforderlich. sam build verpackt Code und Shared Layer automatisch.
sam build

# Discovery-Lambda lokal ausführen
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Mit Überschreibung von Umgebungsvariablen
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit-Tests

```bash
python3 -m pytest tests/ -v
```

Details siehe [Schnellstart für lokales Testen](../docs/local-testing-quick-start.md).

---

## Ausgabebeispiel (Output Sample)

Beispielausgabe der Satellitenbildanalyse-Pipeline (Human Review erforderlich):

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 4,
    "prefix": "satellite/imagery/"
  },
  "tiling": {
    "input_key": "satellite/imagery/scene-2026-05-23.nitf",
    "tiles_generated": 64,
    "tile_size_px": 512,
    "cog_output": "s3://output-bucket/tiles/scene-2026-05-23/"
  },
  "object_detection": {
    "objects_detected": 12,
    "categories": {"vehicle": 8, "structure": 3, "vessel": 1},
    "confidence_threshold": 0.85,
    "requires_human_review": true
  },
  "change_detection": {
    "baseline_date": "2026-05-16",
    "comparison_date": "2026-05-23",
    "changes_detected": 3,
    "change_areas_km2": [0.02, 0.05, 0.01]
  },
  "human_review_status": "PENDING",
  "classification_level": "UNCLASSIFIED_SAMPLE"
}
```

> **Hinweis**: Das Obige ist eine Beispielausgabe; die tatsächlichen Werte variieren je nach Umgebung und Eingabedaten. Benchmark-Zahlen sind eine Dimensionierungsreferenz, kein Service-Limit.

---

## Governance Note

> Dieses Pattern bietet technische Architektur-Empfehlungen. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Organisationen sollten qualifizierte Fachleute konsultieren.

---

## S3AP Compatibility

Zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Patterns von S3 Access Points for FSx for ONTAP siehe [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
