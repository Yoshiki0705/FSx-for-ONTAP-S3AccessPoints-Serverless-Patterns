# UC14: Versicherung/Schadenregulierung — Unfallbild-Schadensbewertung, Kostenvoranschlag-OCR und Gutachten

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DATA["Versicherungsschadendaten<br/>.jpg/.jpeg/.png (Unfallfotos)<br/>.pdf/.tiff (Kostenvoranschläge)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(1 hour)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• Foto/Kostenvoranschlag-Trennung<br/>• Manifest-Generierung"]
        DA["2️⃣ Schadensbewertung Lambda<br/>• Fotoabruf über S3 AP<br/>• Rekognition DetectLabels<br/>• Schadenslabel-Erkennung<br/>• severity_level Bewertung<br/>• affected_components Identifikation<br/>• Manuelle Prüfung Markierung"]
        EO["3️⃣ Kostenvoranschlag OCR Lambda<br/>• Abruf über S3 AP<br/>• Textract (us-east-1 regionsübergreifend)<br/>• Text- und Formularextraktion<br/>• Reparaturposten, Kosten, Arbeit, Teile<br/>• Niedrige Konfidenz Markierung"]
        CR["4️⃣ Gutachten Lambda<br/>• Bedrock InvokeModel<br/>• Schadensbewertung + Kostenvoranschlag Integration<br/>• Umfassende Gutachten-Generierung<br/>• JSON + menschenlesbares Format<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        DMGOUT["damage-assessment/*.json<br/>Schadensbewertungsergebnisse"]
        OCROUT["estimate-ocr/*.json<br/>Kostenvoranschlag OCR-Ergebnisse"]
        REPORT["reports/*.json + *.md<br/>Gutachten"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Gutachten-Abschlussbenachrichtigung)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> DA
    DISC --> EO
    DA --> CR
    EO --> CR
    DA --> DMGOUT
    EO --> OCROUT
    CR --> REPORT
    CR --> SNS
```

---

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .jpg/.jpeg/.png (Unfallfotos), .pdf/.tiff (Kostenvoranschläge) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger Bild-/PDF-Abruf (erforderlich für Rekognition / Textract) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Erkennung | Lambda (VPC) | Erkennung von Unfallfotos und Kostenvoranschlägen über S3 AP, Manifest-Generierung nach Typ |
| Schadensbewertung | Lambda + Rekognition | DetectLabels zur Schadenslabel-Erkennung, Schweregradbewertung, Identifikation betroffener Komponenten |
| Kostenvoranschlag OCR | Lambda + Textract | Text- und Formularextraktion aus Kostenvoranschlägen (Reparaturposten, Kosten, Arbeit, Teile) |
| Gutachten | Lambda + Bedrock | Integration von Schadensbewertung + Kostenvoranschlagsdaten für umfassendes Gutachten |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| Schadensbewertung | `damage-assessment/YYYY/MM/DD/{claim}_damage.json` | Schadensbewertungsergebnisse (damage_type, severity_level, affected_components) |
| Kostenvoranschlag OCR | `estimate-ocr/YYYY/MM/DD/{claim}_estimate.json` | Kostenvoranschlag OCR-Ergebnisse (Reparaturposten, Kosten, Arbeit, Teile) |
| Gutachten (JSON) | `reports/YYYY/MM/DD/{claim}_report.json` | Strukturiertes Gutachten |
| Gutachten (MD) | `reports/YYYY/MM/DD/{claim}_report.md` | Menschenlesbares Gutachten |
| SNS-Benachrichtigung | Email | Gutachten-Abschlussbenachrichtigung |

---

## Wichtige Designentscheidungen

1. **Parallelverarbeitung (Schadensbewertung + Kostenvoranschlag OCR)** — Unfallbild-Schadensbewertung und Kostenvoranschlag-OCR sind unabhängig; über Step Functions Parallel State parallelisiert für verbesserten Durchsatz
2. **Rekognition gestufte Schadensbewertung** — Markierung zur manuellen Prüfung wenn keine Schadenslabels erkannt werden, fördert menschliche Verifizierung
3. **Textract regionsübergreifend** — Textract nur in us-east-1 verfügbar; regionsübergreifender Aufruf verwendet
4. **Bedrock integriertes Gutachten** — Korreliert Schadensbewertungs- und Kostenvoranschlagsdaten zur Generierung eines umfassenden Gutachtens in JSON + menschenlesbarem Format
5. **Niedrige-Konfidenz-Markierung** — Markierung zur manuellen Prüfung wenn Rekognition / Textract Konfidenzwerte unter dem Schwellenwert liegen
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Speicherung von Unfallfotos und Kostenvoranschlägen |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser |
| Step Functions | Workflow-Orchestrierung (Unterstützung paralleler Pfade) |
| Lambda | Compute (Erkennung, Schadensbewertung, Kostenvoranschlag OCR, Gutachten) |
| Amazon Rekognition | Unfallbild-Schadenserkennung (DetectLabels) |
| Amazon Textract | Kostenvoranschlag OCR Text- und Formularextraktion (us-east-1 regionsübergreifend) |
| Amazon Bedrock | Gutachten-Generierung (Claude / Nova) |
| SNS | Gutachten-Abschlussbenachrichtigung |
| Secrets Manager | ONTAP REST API Anmeldedatenverwaltung |
| CloudWatch + X-Ray | Observability |
