# UC12: Logistik/Lieferkette — Lieferschein-OCR und Lagerbestandsanalyse

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Übergeordneter Ablauf

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/logistics_data/                                                        │
│  ├── slips/2024-03/slip_001.jpg            (Shipping slip image)             │
│  ├── slips/2024-03/slip_002.png            (Shipping slip image)             │
│  ├── slips/2024-03/slip_003.pdf            (Shipping slip PDF)               │
│  ├── inventory/warehouse_A/shelf_01.jpeg   (Warehouse inventory photo)       │
│  └── inventory/warehouse_B/shelf_02.png    (Warehouse inventory photo)       │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-logistics-vol-ext-s3alias                                       │
│  • ListObjectsV2 (slip image & inventory photo discovery)                    │
│  • GetObject (image & PDF retrieval)                                         │
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
│  ┌─────────────┐    ┌──────────────────────┐    ┌────────────────────┐      │
│  │  Discovery   │───▶│  OCR                 │───▶│  Data Structuring  │      │
│  │  Lambda      │    │  Lambda              │    │  Lambda            │      │
│  │             │    │                      │    │                   │      │
│  │  • VPC内     │    │  • Textract          │    │  • Bedrock         │      │
│  │  • S3 AP List│    │  • Text extraction   │    │  • Field normaliz  │      │
│  │  • Slips/Inv │    │  • Form analysis     │    │  • Structured rec  │      │
│  └──────┬──────┘    └──────────────────────┘    └────────────────────┘      │
│         │                                                    │               │
│         │            ┌──────────────────────┐                │               │
│         └───────────▶│  Inventory Analysis  │                │               │
│                      │  Lambda              │                ▼               │
│                      │                      │    ┌────────────────────┐      │
│                      │  • Rekognition       │───▶│  Report            │      │
│                      │  • Object detection  │    │  Lambda            │      │
│                      │  • Inventory count   │    │                   │      │
│                      └──────────────────────┘    │  • Bedrock         │      │
│                                                  │  • Optimization    │      │
│                                                  │    report          │      │
│                                                  │  • SNS notification│      │
│                                                  └────────────────────┘      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── ocr-results/YYYY/MM/DD/                                                 │
│  │   ├── slip_001_ocr.json                 ← OCR text extraction results    │
│  │   └── slip_002_ocr.json                                                   │
│  ├── structured-records/YYYY/MM/DD/                                          │
│  │   ├── slip_001_record.json              ← Structured shipping records    │
│  │   └── slip_002_record.json                                                │
│  ├── inventory-analysis/YYYY/MM/DD/                                          │
│  │   ├── warehouse_A_shelf_01.json         ← Inventory analysis results     │
│  │   └── warehouse_B_shelf_02.json                                           │
│  └── reports/YYYY/MM/DD/                                                     │
│      └── logistics_report.md               ← Delivery route optimization    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid-Diagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DATA["Logistikdaten<br/>.jpg/.jpeg/.png/.tiff/.pdf (Lieferscheine)<br/>.jpg/.jpeg/.png (Lagerbestandsfotos)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• Lieferschein-/Bestandstrennung<br/>• Manifest-Generierung"]
        OCR["2️⃣ OCR Lambda<br/>• Lieferscheinabruf über S3 AP<br/>• Textract (us-east-1 regionsübergreifend)<br/>• Text- und Formularextraktion<br/>• Markierung bei niedriger Konfidenz"]
        DS["3️⃣ Datenstrukturierung Lambda<br/>• Bedrock InvokeModel<br/>• Normalisierung extrahierter Felder<br/>• Zielort, Artikel, Menge, Sendungsnummer<br/>• Strukturierte Versanddatensätze"]
        IA["4️⃣ Bestandsanalyse Lambda<br/>• Bestandsfotos über S3 AP abrufen<br/>• Rekognition DetectLabels<br/>• Objekterkennung und Zählung<br/>• Paletten, Kartons, Regalbelegung"]
        RPT["5️⃣ Bericht Lambda<br/>• Bedrock InvokeModel<br/>• Versanddaten + Bestandsdaten Integration<br/>• Lieferroutenoptimierungsbericht<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        OCROUT["ocr-results/*.json<br/>OCR-Textextraktionsergebnisse"]
        STROUT["structured-records/*.json<br/>Strukturierte Versanddatensätze"]
        INVOUT["inventory-analysis/*.json<br/>Bestandsanalyseergebnisse"]
        REPORT["reports/*.md<br/>Optimierungsbericht"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Berichtsfertigstellungsbenachrichtigung)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> OCR
    DISC --> IA
    OCR --> DS
    DS --> RPT
    IA --> RPT
    OCR --> OCROUT
    DS --> STROUT
    IA --> INVOUT
    RPT --> REPORT
    RPT --> SNS
```

---

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .jpg/.jpeg/.png/.tiff/.pdf (Lieferscheine), .jpg/.jpeg/.png (Lagerbestandsfotos) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger Bild-/PDF-Abruf (erforderlich für Textract / Rekognition) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Erkennung | Lambda (VPC) | Erkennung von Lieferscheinbildern und Bestandsfotos über S3 AP, Manifest-Generierung nach Typ |
| OCR | Lambda + Textract | Lieferschein-Text- und Formularextraktion (Absender, Empfänger, Sendungsnummer, Artikel) |
| Datenstrukturierung | Lambda + Bedrock | Normalisierung extrahierter Felder, Generierung strukturierter Versanddatensätze (Zielort, Artikel, Menge usw.) |
| Bestandsanalyse | Lambda + Rekognition | Objekterkennung und Zählung auf Lagerbestandsbildern (Paletten, Kartons, Regalbelegung) |
| Bericht | Lambda + Bedrock | Integration von Versand- und Bestandsdaten für Lieferroutenoptimierungsbericht |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| OCR-Ergebnisse | `ocr-results/YYYY/MM/DD/{slip}_ocr.json` | Textract-Textextraktionsergebnisse (mit Konfidenzwerten) |
| Strukturierte Datensätze | `structured-records/YYYY/MM/DD/{slip}_record.json` | Strukturierte Versanddatensätze (Zielort, Artikel, Menge, Sendungsnummer) |
| Bestandsanalyse | `inventory-analysis/YYYY/MM/DD/{warehouse}_{shelf}.json` | Bestandsanalyseergebnisse (Objektanzahl, Regalbelegung) |
| Logistikbericht | `reports/YYYY/MM/DD/logistics_report.md` | Von Bedrock generierter Lieferroutenoptimierungsbericht |
| SNS-Benachrichtigung | Email | Berichtsfertigstellungsbenachrichtigung |

---

## Wichtige Designentscheidungen

1. **Parallelverarbeitung (OCR + Bestandsanalyse)** — Lieferschein-OCR und Lagerbestandsanalyse sind unabhängig; Parallelisierung über Step Functions Parallel State
2. **Textract regionsübergreifend** — Textract nur in us-east-1 verfügbar; regionsübergreifender Aufruf wird verwendet
3. **Feldnormalisierung durch Bedrock** — Normalisiert unstrukturierten OCR-Text über Bedrock zur Generierung strukturierter Versanddatensätze
4. **Bestandszählung durch Rekognition** — DetectLabels zur Objekterkennung, automatische Berechnung der Paletten-/Karton-/Regalbelegungsraten
5. **Verwaltung von Markierungen bei niedriger Konfidenz** — Manuelle Überprüfungsmarkierung wird gesetzt, wenn Textract-Konfidenzwerte unter dem Schwellenwert liegen
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Speicherung von Lieferscheinen und Lagerbestandsbildern |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser |
| Step Functions | Workflow-Orchestrierung (Unterstützung paralleler Pfade) |
| Lambda | Compute (Discovery, OCR, Datenstrukturierung, Bestandsanalyse, Bericht) |
| Amazon Textract | Lieferschein-OCR-Text- und Formularextraktion (us-east-1 regionsübergreifend) |
| Amazon Rekognition | Objekterkennung und Zählung auf Lagerbestandsbildern (DetectLabels) |
| Amazon Bedrock | Feldnormalisierung und Optimierungsberichtgenerierung (Claude / Nova) |
| SNS | Berichtsfertigstellungsbenachrichtigung |
| Secrets Manager | Verwaltung der ONTAP REST API-Anmeldeinformationen |
| CloudWatch + X-Ray | Observability |
