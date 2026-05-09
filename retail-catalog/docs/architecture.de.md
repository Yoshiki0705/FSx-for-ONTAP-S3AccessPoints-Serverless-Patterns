# UC11: Einzelhandel/E-Commerce — Automatisches Produkt-Tagging und Katalog-Metadaten-Generierung

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DATA["Produktbilder<br/>.jpg/.jpeg/.png/.webp"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(30 minutes)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• .jpg/.jpeg/.png/.webp Filter<br/>• Manifest-Generierung"]
        IT["2️⃣ Image Tagging Lambda<br/>• Bildabruf über S3 AP<br/>• Rekognition DetectLabels<br/>• Kategorie-, Farb-, Material-Labels<br/>• Konfidenz-Score-Bewertung<br/>• Manuelle Überprüfung Flag-Setzung"]
        QC["3️⃣ Quality Check Lambda<br/>• Bild-Metadaten-Analyse<br/>• Auflösungsprüfung (min 800x800)<br/>• Dateigrößen-Validierung<br/>• Seitenverhältnis-Prüfung<br/>• Qualitätsfehler Flag-Setzung"]
        CM["4️⃣ Catalog Metadata Lambda<br/>• Bedrock InvokeModel<br/>• Tags + Qualitätsinfo als Eingabe<br/>• Strukturierte Metadaten-Generierung<br/>• Produktbeschreibung-Generierung<br/>• product_category, color, material"]
        SP["5️⃣ Stream Producer/Consumer Lambda<br/>• Kinesis PutRecord<br/>• Echtzeit-Integration<br/>• Downstream-System-Benachrichtigung<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket + Kinesis"]
        TAGOUT["image-tags/*.json<br/>Bild-Tagging-Ergebnisse"]
        QCOUT["quality-check/*.json<br/>Qualitätsprüfungs-Ergebnisse"]
        CATOUT["catalog-metadata/*.json<br/>Katalog-Metadaten"]
        KINESIS["Kinesis Data Stream<br/>Echtzeit-Integration"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Verarbeitungsabschluss-Benachrichtigung)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> IT
    IT --> QC
    QC --> CM
    CM --> SP
    IT --> TAGOUT
    QC --> QCOUT
    CM --> CATOUT
    SP --> KINESIS
    SP --> SNS
```

---

## Datenfluss-Details

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .jpg/.jpeg/.png/.webp (Produktbilder) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | Vollständiger Bildabruf (erforderlich für Rekognition / Qualitätsprüfung) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Discovery | Lambda (VPC) | Produktbilder über S3 AP erkennen, Manifest generieren |
| Image Tagging | Lambda + Rekognition | DetectLabels zur Label-Erkennung (Kategorie, Farbe, Material), Konfidenz-Schwellenwert-Bewertung |
| Quality Check | Lambda | Bildqualitätsmetriken-Validierung (Auflösung, Dateigröße, Seitenverhältnis) |
| Catalog Metadata | Lambda + Bedrock | Strukturierte Katalog-Metadaten-Generierung (product_category, color, material, Produktbeschreibung) |
| Stream Producer/Consumer | Lambda + Kinesis | Echtzeit-Integration, Datenlieferung an Downstream-Systeme |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| Bild-Tags | `image-tags/YYYY/MM/DD/{sku}_{view}_tags.json` | Rekognition Label-Erkennungsergebnisse (mit Konfidenz-Scores) |
| Qualitätsprüfung | `quality-check/YYYY/MM/DD/{sku}_{view}_quality.json` | Qualitätsprüfungsergebnisse (Auflösung, Größe, Seitenverhältnis, Bestanden/Nicht bestanden) |
| Katalog-Metadaten | `catalog-metadata/YYYY/MM/DD/{sku}_metadata.json` | Strukturierte Metadaten (product_category, color, material, description) |
| Kinesis Stream | `retail-catalog-stream` | Echtzeit-Integrationsdatensätze (für Downstream PIM/EC-Systeme) |
| SNS-Benachrichtigung | Email | Verarbeitungsabschluss-Benachrichtigung und Qualitätswarnungen |

---

## Wichtige Designentscheidungen

1. **Rekognition Auto-Tagging** — DetectLabels zur automatischen Kategorie-/Farb-/Material-Erkennung. Manuelle Überprüfung Flag wird gesetzt, wenn die Konfidenz unter dem Schwellenwert liegt (Standard: 70%)
2. **Bildqualitäts-Gate** — Auflösung (min 800x800), Dateigröße und Seitenverhältnis-Validierung zur automatischen Prüfung der E-Commerce-Listing-Standards
3. **Bedrock für Metadaten-Generierung** — Tags + Qualitätsinfo als Eingabe zur automatischen Generierung strukturierter Katalog-Metadaten und Produktbeschreibungen
4. **Kinesis Echtzeit-Integration** — PutRecord an Kinesis Data Streams nach der Verarbeitung für Echtzeit-Integration mit Downstream PIM/EC-Systemen
5. **Sequenzielle Pipeline** — Step Functions verwaltet Reihenfolge-Abhängigkeiten: Tagging → Qualitätsprüfung → Metadaten-Generierung → Stream-Lieferung
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen; 30-Minuten-Intervall für schnelle Verarbeitung neuer Produkte

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Produktbild-Speicherung |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser (30-Minuten-Intervall) |
| Step Functions | Workflow-Orchestrierung (sequenziell) |
| Lambda | Compute (Discovery, Image Tagging, Quality Check, Catalog Metadata, Stream Producer/Consumer) |
| Amazon Rekognition | Produktbild-Label-Erkennung (DetectLabels) |
| Amazon Bedrock | Katalog-Metadaten- und Produktbeschreibung-Generierung (Claude / Nova) |
| Kinesis Data Streams | Echtzeit-Integration (für Downstream PIM/EC-Systeme) |
| SNS | Verarbeitungsabschluss-Benachrichtigung und Qualitätswarnungen |
| Secrets Manager | ONTAP REST API Anmeldedaten-Verwaltung |
| CloudWatch + X-Ray | Observability |
