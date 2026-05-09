# UC5: Gesundheitswesen — Automatische DICOM-Bildklassifizierung und Anonymisierung

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Übergeordneter Ablauf

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/pacs_archive/                                                          │
│  ├── CT/patient_001/study_20240315/series_001.dcm    (CT scan)               │
│  ├── MR/patient_002/study_20240316/brain_t1.dcm      (MRI)                   │
│  ├── XR/patient_003/study_20240317/chest_pa.dcm      (X-ray)                 │
│  └── US/patient_004/study_20240318/abdomen.dicom     (Ultrasound)            │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-dicom-vol-ext-s3alias                                           │
│  • ListObjectsV2 (DICOM file discovery)                                      │
│  • GetObject (DICOM file retrieval)                                          │
│  • No NFS/SMB mount required from Lambda                                     │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler (Trigger)                            │
│                                                                              │
│  Schedule: rate(1 hour) — configurable                                       │
│  Target: Step Functions State Machine                                        │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    AWS Step Functions (Orchestration)                         │
│                                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │  Discovery   │───▶│ DICOM Parse  │───▶│PII Detection │───▶│Anonymiza- │  │
│  │  Lambda      │    │  Lambda      │    │  Lambda      │    │tion Lambda│  │
│  │             │    │             │    │             │    │           │  │
│  │  • VPC内     │    │  • Metadata  │    │  • Comprehend│    │  • PHI     │  │
│  │  • S3 AP List│    │    extraction│    │    Medical   │    │    removal │  │
│  │  • .dcm      │    │  • Patient   │    │  • PII       │    │  • Masking │  │
│  │    detection │    │    info      │    │    detection │    │    process │  │
│  └─────────────┘    └──────────────┘    └──────────────┘    └───────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── metadata/YYYY/MM/DD/                                                    │
│  │   └── patient_001_series_001.json   ← DICOM metadata                     │
│  ├── pii-reports/YYYY/MM/DD/                                                 │
│  │   └── patient_001_series_001_pii.json  ← PII detection results           │
│  └── anonymized/YYYY/MM/DD/                                                  │
│      └── anon_series_001.dcm           ← Anonymized DICOM                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid-Diagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DICOM["DICOM medizinische Bilder<br/>.dcm, .dicom"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• .dcm/.dicom Filter<br/>• Manifest-Generierung"]
        DP["2️⃣ DICOM Parse Lambda<br/>• DICOM-Abruf über S3 AP<br/>• Header-Metadaten-Extraktion<br/>  (Patientenname, Untersuchungsdatum, Modalität,<br/>   Körperteil, Einrichtung)<br/>• Modalitätsbasierte Klassifizierung"]
        PII["3️⃣ PII Detection Lambda<br/>• Comprehend Medical<br/>• DetectPHI API<br/>• Erkennung geschützter Gesundheitsinformationen (PHI)<br/>• Erkennungsposition und Konfidenzwert"]
        ANON["4️⃣ Anonymization Lambda<br/>• PHI-Maskierungsverarbeitung<br/>• DICOM-Tag-Anonymisierung<br/>  (Patientenname→Hash, Geburtsdatum→Alter)<br/>• Anonymisierte DICOM-Ausgabe"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        META["metadata/*.json<br/>DICOM-Metadaten"]
        PIIR["pii-reports/*.json<br/>PII-Erkennungsergebnisse"]
        ANOND["anonymized/*.dcm<br/>Anonymisiertes DICOM"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Verarbeitungsabschluss-Benachrichtigung"]
    end

    DICOM --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> DP
    DP --> PII
    PII --> ANON
    DP --> META
    PII --> PIIR
    ANON --> ANOND
    ANON --> SNS
```

---

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .dcm, .dicom (DICOM medizinische Bilder) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger DICOM-Dateiabruf (Header + Pixeldaten) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Discovery | Lambda (VPC) | DICOM-Dateien über S3 AP erkennen, Manifest generieren |
| DICOM Parse | Lambda | Metadaten aus DICOM-Headern extrahieren (Patienteninfo, Modalität, Untersuchungsdatum usw.) |
| PII Detection | Lambda + Comprehend Medical | Geschützte Gesundheitsinformationen über DetectPHI erkennen |
| Anonymization | Lambda | PHI-Maskierung und Anonymisierung, anonymisiertes DICOM ausgeben |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| DICOM-Metadaten | `metadata/YYYY/MM/DD/{stem}.json` | Extrahierte Metadaten (Modalität, Körperteil, Untersuchungsdatum) |
| PII-Bericht | `pii-reports/YYYY/MM/DD/{stem}_pii.json` | PHI-Erkennungsergebnisse (Position, Typ, Konfidenz) |
| Anonymisiertes DICOM | `anonymized/YYYY/MM/DD/{stem}.dcm` | Anonymisierte DICOM-Datei |
| SNS-Benachrichtigung | E-Mail | Verarbeitungsabschluss-Benachrichtigung (Anzahl verarbeitet und anonymisiert) |

---

## Wichtige Designentscheidungen

1. **S3 AP statt NFS** — Kein NFS-Mount von Lambda erforderlich; DICOM-Dateien werden über die S3-API abgerufen
2. **Comprehend Medical Spezialisierung** — Hochpräzise PII-Identifikation durch domänenspezifische PHI-Erkennung im Gesundheitswesen
3. **Stufenweise Anonymisierung** — Drei Stufen (Metadaten-Extraktion → PII-Erkennung → Anonymisierung) gewährleisten Audit-Trail
4. **DICOM-Standardkonformität** — Anonymisierungsregeln basierend auf DICOM PS3.15 (Sicherheitsprofile)
5. **HIPAA / Datenschutzkonformität** — Safe-Harbor-Methode zur Anonymisierung (Entfernung von 18 Identifikatoren)
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | PACS/VNA medizinische Bildspeicherung |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Compute (Discovery, DICOM Parse, PII Detection, Anonymization) |
| Amazon Comprehend Medical | PHI-Erkennung (geschützte Gesundheitsinformationen) |
| SNS | Verarbeitungsabschluss-Benachrichtigung |
| Secrets Manager | ONTAP REST API Anmeldedatenverwaltung |
| CloudWatch + X-Ray | Observability |
