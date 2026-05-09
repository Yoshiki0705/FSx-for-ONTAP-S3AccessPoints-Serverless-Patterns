# UC10: Bauwesen/AEC — BIM-Modellverwaltung, Zeichnungs-OCR & Sicherheitskonformität

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Übergeordneter Ablauf

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FSx for NetApp ONTAP                                 │
│                                                                              │
│  /vol/bim_projects/                                                          │
│  ├── models/building_A_v3.ifc         (IFC BIM model)                        │
│  ├── models/building_A_v3.rvt         (Revit file)                           │
│  ├── drawings/floor_plan_1F.dwg       (AutoCAD drawing)                      │
│  └── drawings/safety_plan.pdf         (Safety plan drawing PDF)              │
│                                                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      S3 Access Point (Data Path)                              │
│                                                                              │
│  Alias: fsxn-bim-vol-ext-s3alias                                             │
│  • ListObjectsV2 (BIM/CAD file discovery)                                    │
│  • GetObject (IFC/RVT/DWG/PDF retrieval)                                     │
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
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Discovery  │─▶│ BIM Parse    │─▶│    OCR       │─▶│  Safety Check    │   │
│  │ Lambda     │  │ Lambda       │  │ Lambda       │  │  Lambda          │   │
│  │           │  │             │  │             │  │                 │   │
│  │ • VPC内    │  │ • IFC meta- │  │ • Textract   │  │ • Bedrock        │   │
│  │ • S3 AP   │  │   data      │  │ • Drawing    │  │ • Safety         │   │
│  │ • IFC/RVT │  │   extraction│  │   text       │  │   compliance     │   │
│  │   /DWG/PDF│  │ • Version   │  │   extraction │  │   check          │   │
│  └───────────┘  │   diff      │  │             │  │                 │   │
│                  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Output (S3 Bucket)                                    │
│                                                                              │
│  s3://{stack}-output-{account}/                                              │
│  ├── bim-metadata/YYYY/MM/DD/                                                │
│  │   └── building_A_v3.json          ← BIM metadata + diff                  │
│  ├── ocr-text/YYYY/MM/DD/                                                    │
│  │   └── safety_plan.json            ← OCR extracted text & tables          │
│  └── compliance/YYYY/MM/DD/                                                  │
│      └── building_A_v3_safety.json   ← Safety compliance report             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Mermaid-Diagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        BIM["BIM / CAD-Dateien<br/>.ifc, .rvt, .dwg, .pdf"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• .ifc/.rvt/.dwg/.pdf Filter<br/>• Manifest-Generierung"]
        BP["2️⃣ BIM Parse Lambda<br/>• IFC/Revit-Abruf über S3 AP<br/>• Metadaten-Extraktion<br/>  (Projektname, Elementanzahl, Stockwerke,<br/>   Koordinatensystem, IFC-Schema-Version)<br/>• Versionsdifferenz-Erkennung"]
        OCR["3️⃣ OCR Lambda<br/>• Zeichnungs-PDF-Abruf über S3 AP<br/>• Textract (regionsübergreifend)<br/>• Text- und Tabellenextraktion<br/>• Strukturierte Datenausgabe"]
        SC["4️⃣ Safety Check Lambda<br/>• Bedrock InvokeModel<br/>• Sicherheitskonformitätsregeln<br/>  (Brandschutzevakuierung, Traglasten, Materialstandards)<br/>• Verstoßerkennung und Berichtgenerierung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        META["bim-metadata/*.json<br/>BIM-Metadaten + Differenzen"]
        TEXT["ocr-text/*.json<br/>OCR-extrahierter Text"]
        COMP["compliance/*.json<br/>Sicherheitskonformitätsbericht"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Verstoßerkennungs-Benachrichtigung"]
    end

    BIM --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> BP
    DISC --> OCR
    BP --> SC
    OCR --> SC
    BP --> META
    OCR --> TEXT
    SC --> COMP
    SC --> SNS
```

---

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .ifc, .rvt, .dwg, .pdf (BIM-Modelle, CAD-Zeichnungen, Zeichnungs-PDFs) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger Dateiabruf (erforderlich für Metadaten-Extraktion und OCR) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Erkennung | Lambda (VPC) | BIM/CAD-Dateien über S3 AP erkennen, Manifest generieren |
| BIM-Analyse | Lambda | IFC/Revit-Metadaten-Extraktion, Versionsdifferenz-Erkennung |
| OCR | Lambda + Textract | Zeichnungs-PDF Text- und Tabellenextraktion (regionsübergreifend) |
| Sicherheitsprüfung | Lambda + Bedrock | Sicherheitskonformitätsregeln prüfen, Verstoßerkennung |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| BIM-Metadaten | `bim-metadata/YYYY/MM/DD/{stem}.json` | Metadaten + Versionsdifferenzen |
| OCR-Text | `ocr-text/YYYY/MM/DD/{stem}.json` | Textract-extrahierter Text und Tabellen |
| Konformitätsbericht | `compliance/YYYY/MM/DD/{stem}_safety.json` | Sicherheitskonformitätsbericht |
| SNS-Benachrichtigung | Email / Slack | Sofortige Benachrichtigung bei Verstoßerkennung |

---

## Wichtige Designentscheidungen

1. **S3 AP statt NFS** — Kein NFS-Mount von Lambda erforderlich; BIM/CAD-Dateien werden über die S3-API abgerufen
2. **BIM Parse + OCR parallele Ausführung** — IFC-Metadaten-Extraktion und Zeichnungs-OCR laufen parallel, beide Ergebnisse werden für die Sicherheitsprüfung aggregiert
3. **Textract regionsübergreifend** — Regionsübergreifender Aufruf für Regionen, in denen Textract nicht verfügbar ist
4. **Bedrock für Sicherheitskonformität** — LLM-basierte Regelprüfung für Brandschutzevakuierung, Traglasten und Materialstandards
5. **Versionsdifferenz-Erkennung** — Automatische Erkennung von Element-Hinzufügungen/-Löschungen/-Änderungen in IFC-Modellen für effizientes Änderungsmanagement
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | BIM/CAD-Projektspeicher |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Compute (Discovery, BIM Parse, OCR, Safety Check) |
| Amazon Textract | Zeichnungs-PDF OCR Text- und Tabellenextraktion |
| Amazon Bedrock | Sicherheitskonformitätsprüfung (Claude / Nova) |
| SNS | Verstoßerkennungs-Benachrichtigung |
| Secrets Manager | ONTAP REST API Anmeldedatenverwaltung |
| CloudWatch + X-Ray | Observability |
