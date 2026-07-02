# UC16: Behörden — Digitales Archiv öffentlicher Akten & FOIA-Bearbeitung

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)
📚 **Dokumentation**: [Architektur](docs/architecture.md) | [Demo-Skript](docs/demo-guide.md) | [Fehlerbehebung](../docs/phase7-troubleshooting.md)

## Überblick

Automatisierte Pipeline für die digitale Archivierung öffentlicher Akten
von Behörden und die Bearbeitung von Anträgen auf Informationsfreiheit
(FOIA: Freedom of Information Act), aufbauend auf
FSx for ONTAP S3 Access Points.

## Anwendungsfall

Die große Menge öffentlicher Akten (PDF, Scan-Bilder, E-Mails) im Besitz
von Behörden automatisch digitalisieren, klassifizieren und schwärzen
(Redaction), um Anträge auf Informationsfreiheit schnell zu bearbeiten.

### Verarbeitungsablauf

```
FSx for ONTAP (Speicher öffentlicher Akten — NTFS-ACL je Abteilung)
  → S3 Access Point
    → Step Functions-Workflow
      → Discovery: Erkennung neuer Dokumente (PDF, TIFF, EML, MSG)
      → OCR: Dokumentdigitalisierung mit Textract (regionsübergreifend, da ap-northeast-1 nicht unterstützt)
      → Classification: Dokumentklassifizierung mit Comprehend (Bestimmung der Vertraulichkeitsstufe)
      → EntityExtraction: PII-Erkennung (Name, Adresse, SSN, Telefonnummer)
      → Redaction: Automatische Schwärzung vertraulicher Informationen (Redaction)
      → IndexGeneration: Erzeugung eines Volltext-Suchindex (OpenSearch, deaktivierbar)
      → ComplianceCheck: Prüfung von Aufbewahrungsfrist / Vernichtungsplan (NARA GRS)
```

### Zieldaten

| Datenformat | Beschreibung | Typische Größe |
|-----------|------|-----------|
| PDF | Öffentliche Akten, Berichte, Verträge | 100 KB – 50 MB |
| TIFF | Gescannte Dokumente | 1 – 100 MB |
| EML / MSG | E-Mail-Archive | 10 KB – 10 MB |
| DOCX / XLSX | Office-Dokumente | 50 KB – 20 MB |

### AWS-Services

| Service | Zweck |
|---------|------|
| FSx for ONTAP | Persistenter Speicher für öffentliche Akten (NTFS-ACL je Abteilung) |
| S3 Access Points | Dokumentzugriff aus Serverless |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Dokumentklassifizierung, PII-Erkennung, Schwärzung |
| Amazon Textract ⚠️ | Dokument-OCR (regionsübergreifend über us-east-1) |
| Amazon Comprehend | Entitätsextraktion, Dokumentklassifizierung, PII-Erkennung |
| Amazon Bedrock | Dokumentzusammenfassung, Erzeugung von FOIA-Antwortentwürfen |
| Amazon Macie | Automatische Erkennung sensibler Daten |
| DynamoDB | Dokument-Metadaten, Verwaltung des Verarbeitungsstatus |
| OpenSearch Serverless | Volltext-Suchindex (optional, standardmäßig deaktiviert) |
| SNS | FOIA-Fristwarnungen |

### Eignung für den öffentlichen Sektor

- **NARA-Konformität (National Archives and Records Administration)**: Erfüllt die Anforderungen an das elektronische Aktenmanagement
- **FOIA-Bearbeitung**: Verfolgt automatisch die Antwortfrist von 20 Werktagen
- **FedRAMP High**: Konform in AWS GovCloud
- **Section 508**: Barrierefreiheit (OCR + Erzeugung von Alternativtexten)
- **Records Management**: Automatische Verwaltung von Aufbewahrungsfristen und Vernichtungsplänen

### FOIA-Bearbeitungsablauf

```
FOIA-Antrag eingegangen
  → Zieldokumente suchen (OpenSearch)
  → Bestimmung der Vertraulichkeitsstufe passender Dokumente
  → Automatische Schwärzung (PII, Informationen zur nationalen Sicherheit)
  → Benachrichtigung an Prüfer
  → Verfolgung der Antwortfrist (20 Werktage)
  → Erzeugung des Pakets veröffentlichbarer Dokumente
```

## Verifizierte Bildschirme (Screenshots)

### 1. Ablage öffentlicher Akten (über S3 Access Point)

Nach Eingang eines FOIA-Antrags werden die Zieldokumente unter dem Präfix `archives/YYYY/MM/` abgelegt.

<!-- SCREENSHOT: phase7-uc16-s3-archives-uploaded.png
     Inhalt: Liste der PDF-Dokumente unter dem Präfix archives/ auf dem S3 AP
     Maskierung: Konto-ID, S3-AP-ARN, Dokumentnamen -->
![UC16: Bestätigung der Aktenablage](../docs/screenshots/masked/phase7/phase7-uc16-s3-archives-uploaded.png)

### 2. Ansicht geschwärzter Dokumente

Text, der nach der Verarbeitung unter dem Präfix `redacted/` gespeichert wird, wobei PII
durch den Marker `[REDACTED]` ersetzt wurde. **Der Bildschirm, den allgemeine Mitarbeitende vor der Veröffentlichung prüfen.**

<!-- SCREENSHOT: phase7-uc16-redacted-text-preview.png
     Inhalt: Vorschau des redacted-Textes in der S3-Konsole, [REDACTED]-Marker sichtbar
     Maskierung: Konto-ID, Namen geschwärzter Dokumente (nur Beispielnamen) -->
![UC16: Vorschau des geschwärzten Dokuments](../docs/screenshots/masked/phase7/phase7-uc16-redacted-text-preview.png)

### 3. Schwärzungs-Metadaten (Sidecar-JSON)

Sidecar-Daten für die Prüfung. Ursprüngliche PII werden nicht gespeichert — nur SHA-256-Hashes.
Offsets, Entitätstypen (NAME / EMAIL / SSN usw.) und Konfidenz werden erfasst.

<!-- SCREENSHOT: phase7-uc16-redaction-metadata-json.png
     Inhalt: Formatierte Ansicht von redaction-metadata/*.json
     Maskierung: Konto-ID, Namen der Originaldokumente -->
![UC16: Schwärzungs-Metadaten JSON](../docs/screenshots/masked/phase7/phase7-uc16-redaction-metadata-json.png)

### 4. FOIA-Fristerinnerung (SNS-E-Mail-Benachrichtigung)

Erinnerungs-E-Mail, die FOIA-Verantwortliche 3 Werktage vor der Frist erhalten.
Bei Überschreitung eine OVERDUE-Benachrichtigung mit severity=HIGH.

<!-- SCREENSHOT: phase7-uc16-foia-reminder-email.png
     Inhalt: FOIA_DEADLINE_APPROACHING-E-Mail in einem E-Mail-Client angezeigt
     Maskierung: Empfänger-/Absender-E-Mails, request_id (nur Beispiel-ID) -->
![UC16: FOIA-Fristerinnerungs-E-Mail](../docs/screenshots/masked/phase7/phase7-uc16-foia-reminder-email.png)

### 5. NARA-GRS-Aufbewahrungsplan (DynamoDB Explorer)

Tabelle `fsxn-uc16-demo-retention`. Für jedes Dokument werden der NARA-GRS-Code
(GRS 2.1 / 2.2 / 1.1), die Aufbewahrungsdauer (3 / 7 / 30 Jahre) und das geplante Vernichtungsdatum erfasst.

<!-- SCREENSHOT: phase7-uc16-dynamodb-retention.png
     Inhalt: Liste der Einträge in der retention-Tabelle im DynamoDB Explorer
     Maskierung: Konto-ID, document_key (nur Beispielnamen) -->
![UC16: Tabelle des Aufbewahrungsplans](../docs/screenshots/masked/phase7/phase7-uc16-dynamodb-retention.png)


## Success Metrics

### Outcome
Beschleunigung der FOIA-Bearbeitung durch Automatisierung von Aktenarchivierung und FOIA-Bearbeitung (OCR, Klassifizierung, Schwärzung, Verwaltung von Aufbewahrungsfristen).

### Metrics
| Metrik | Zielwert (Beispiel) |
|-----------|------------|
| Verarbeitete Dokumente / Lauf | > 500 documents |
| Erfolgsrate der OCR-Textextraktion | > 95% |
| Genauigkeit der PII-Erkennung | > 95% |
| Schwärzungszeit / Dokument | < 30 Sekunden |
| Verkürzung der FOIA-Bearbeitungszeit | > 50% |
| Pflichtquote der Human Review | 100% (alle Schwärzungsergebnisse erfordern menschliche Bestätigung) |

> **Warum 100% Human Review**: Da eine übersehene Schwärzung die Informationsfreigabe und den Schutz personenbezogener Daten direkt betrifft, ist die menschliche Bestätigung jedes Elements verpflichtend.

### Measurement Method
Step-Functions-Ausführungsverlauf, Comprehend-PII-Erkennungsergebnisse, Diff vor/nach der Schwärzung, DynamoDB-Aufbewahrungsverlauf, CloudWatch Metrics. Prüfergebnisse werden in DynamoDB erfasst, sodass bei Audits „wer wann was bestätigt/genehmigt hat" nachvollziehbar ist.

### Sample Run Results (Messbeispiel)

**Umgebung**: FSx for ONTAP Single-AZ, 128 MBps, ap-northeast-1, S3AP Internet Origin

| Indikator | Before (manuell) | After (S3AP-Automatisierung) |
|------|-------------|-------------------|
| FOIA-Bearbeitungszeit | Tage bis Wochen | 389 ms (10 docs, sequential) |
| Dokumenterkennung | Manuelle Suche | 32 ms (10 documents) |
| Dateizugriff | Einzelzugriff | avg 36 ms / document |
| Schwärzungsqualität | Von Mitarbeitenden abhängig, inkonsistent | Comprehend-PII-Erkennung + automatische Schwärzung |
| Human Review | Keine oder unregelmäßig | 100% (alle Elemente erfordern menschliche Bestätigung) |
| Prüfpfad | Persönliche Aufzeichnungen | DynamoDB (who/when/what) + S3 Object Lock |
| Verwaltung der Aufbewahrungsfristen | Manuell | Automatische Verfolgung + Warnungen |

> **Hinweis**: Der Sample Run von UC16 ist eine Validierung mit synthetischen oder nicht sensiblen Beispieldokumenten und stellt keine echten Verwaltungsakten oder Produktionsdaten dar. Dieser Sample Run validiert nur den Verarbeitungspfad. Schwärzungsqualität, Vollständigkeit der Human Review und die Bewertung des Prüfpfads sollten separat in einem kundenspezifischen PoC durchgeführt werden.

## Bereitstellung

### Vorabvalidierung

```bash
bash scripts/verify_phase7_prerequisites.sh
```

### One-Shot-Bereitstellung

```bash
bash scripts/deploy_phase7.sh government-archives
```

### Manuelle Bereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. sam build verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-gov-archives \
  --parameter-overrides \
    S3AccessPointAlias=<alias> \
    S3AccessPointName=<name> \
    OpenSearchMode=none \
    CrossRegion=us-east-1 \
    UseCrossRegion=true \
    OntapSecretName=<secret> \
    OntapManagementIp=<ip> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3
```

### OpenSearch-Modi

| Modus | Zweck | Monatliche Kosten (Schätzung) |
|--------|------|-------------------|
| `none` | Validierung / kostengünstiger Betrieb (Standard) | $0 |
| `serverless` | Variable Workloads, nutzungsbasiert | $350 – $700 |
| `managed` | Feste Workloads, günstig | $35 – $100 |

## Verzeichnisstruktur

```
government-archives/
├── template.yaml
├── template-deploy.yaml
├── functions/
│   ├── discovery/handler.py
│   ├── ocr/handler.py                # Regionsübergreifendes Textract
│   ├── classification/handler.py
│   ├── entity_extraction/handler.py
│   ├── redaction/handler.py
│   ├── index_generation/handler.py
│   ├── compliance_check/handler.py   # NARA-GRS-Aufbewahrungsfrist
│   └── foia_deadline_reminder/handler.py  # Verfolgung über 20 Werktage
├── tests/                            # 52 pytest (inkl. Hypothesis)
└── README.md
```


---

## AWS-Dokumentationslinks

| Service | Dokumentation |
|---------|------------|
| FSx for ONTAP | [Benutzerhandbuch](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) |
| S3 Access Points | [S3 AP for FSx for ONTAP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) |
| Step Functions | [Entwicklerhandbuch](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html) |
| Amazon Textract | [Entwicklerhandbuch](https://docs.aws.amazon.com/textract/latest/dg/what-is.html) |
| Amazon Comprehend | [Entwicklerhandbuch](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html) |
| Amazon Macie | [Benutzerhandbuch](https://docs.aws.amazon.com/macie/latest/user/what-is-macie.html) |
| Amazon OpenSearch | [Entwicklerhandbuch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/what-is.html) |

### Ausrichtung am Well-Architected Framework

| Säule | Ausrichtung |
|----|------|
| Operative Exzellenz | X-Ray, EMF, FOIA-Fristverfolgung, 52+ Tests |
| Sicherheit | PII-Schwärzung, SHA-256-Audit-Sidecar, Macie, 100% Human Review |
| Zuverlässigkeit | Step Functions Retry/Catch, regionsübergreifendes OCR, Resilienztests |
| Leistungseffizienz | Parallele PII-Erkennung, OpenSearch-Index, Stapelverarbeitung |
| Kostenoptimierung | Serverless, OpenSearch Serverless, bedingte Indexierung |
| Nachhaltigkeit | NARA-GRS-Konformität, Aufbewahrungsverwaltung, automatischer Vernichtungsplan |





---

## Kostenschätzung (monatlicher Näherungswert)

> **Hinweis**: Die folgenden Angaben sind Näherungswerte für die Region ap-northeast-1; die tatsächlichen Kosten variieren je nach Nutzung. Prüfen Sie die aktuellen Preise im [AWS Pricing Calculator](https://calculator.aws/).

### Serverless-Komponenten (nutzungsbasiert)

| Service | Einzelpreis | Angenommene Nutzung | Monatl. Näherung |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 8 Funktionen × 100 docs/Tag | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/Tag | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/Tag | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~80K tokens/Lauf | ~$3-10 |
| Athena | $5/TB scanned | ~50 MB/Abfrage | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/Tag | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/Monat | ~$0.76 |
| OpenSearch Serverless | $0.24/OCU-hour |


### Fixkosten (FSx for ONTAP — setzt bestehende Umgebung voraus)

| Komponente | Monatlich |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (teilt bestehende Umgebung) |
| S3 Access Point | Keine zusätzlichen Gebühren (nur S3-API-Gebühren) |

### Gesamtschätzung

| Konfiguration | Monatl. Näherung |
|------|---------|
| Minimal (einmal täglich) | ~$5-15 |
| Standard (stündlich) | ~$15-50 |
| Große Skalierung (hohe Frequenz + Alarme) | ~$50-150 |

> **Governance Caveat**: Kostenschätzungen sind Näherungswerte und nicht garantiert. Die tatsächliche Abrechnung variiert je nach Nutzungsmuster, Datenvolumen und Region.

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

# Lokale Ausführung der Discovery-Lambda
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Mit Überschreibung der Umgebungsvariablen
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit-Tests

```bash
python3 -m pytest tests/ -v
```

Weitere Details finden Sie im [Schnellstart für lokales Testen](../docs/local-testing-quick-start.md).

---

## Ausgabebeispiel (Output Sample)

Beispielausgabe der Verarbeitung von Aktenarchivierung / FOIA:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 25,
    "prefix": "archives/incoming/"
  },
  "classification": [
    {
      "key": "archives/incoming/memo-2026-001.pdf",
      "record_type": "memorandum",
      "retention_schedule": "GRS 5.2 - 7 years",
      "sensitivity": "CUI",
      "pii_detected": true
    }
  ],
  "redaction": {
    "total_redacted": 25,
    "pii_fields_removed": 89,
    "redaction_types": {"name": 34, "ssn": 12, "address": 28, "phone": 15},
    "audit_hash": "sha256:d4e5f6..."
  },
  "foia_tracking": {
    "request_id": "FOIA-2026-0042",
    "deadline_date": "2026-06-12",
    "business_days_remaining": 15,
    "status": "IN_PROCESSING"
  },
  "search_index": {
    "documents_indexed": 25,
    "opensearch_collection": "gov-archives-collection"
  }
}
```

> **Hinweis**: Die obige Ausgabe ist ein Beispiel; die tatsächlichen Werte variieren je nach Umgebung und Eingabedaten. Benchmark-Zahlen sind eine Dimensionierungsreferenz, keine Service-Limit-Angabe.

---

## Governance Note

> Dieses Muster bietet technische Architekturhinweise. Es handelt sich nicht um rechtliche, Compliance- oder regulatorische Beratung. Organisationen sollten qualifizierte Fachleute konsultieren.

---

## S3AP Compatibility

Informationen zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Mustern für S3 Access Points for FSx for ONTAP finden Sie in den [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
