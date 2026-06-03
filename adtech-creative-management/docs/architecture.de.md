# UC19: Werbung & Marketing / Creative Asset Management — Asset-Katalogisierung und Markenkonformitätsprüfung

🌐 **Language / Sprache**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for ONTAP"]
        DATA["Creative Assets<br/>.jpeg/.png/.tiff (Bilder)<br/>.mp4/.mov (Video)<br/>.psd (Designdateien)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Täglich 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC-Ausführung<br/>• Mediendatei-Erkennung<br/>• Format + Größenfilter (5 GB Limit)<br/>• Manifest-Generierung"]
        VA["2️⃣ Visual Analyzer Lambda<br/>• Asset-Abruf über S3 AP<br/>• Rekognition DetectLabels (80% Schwellenwert)<br/>• Rekognition DetectModerationLabels<br/>• Rekognition DetectText<br/>• Bis zu 50 Tags/Asset"]
        TC["3️⃣ Text Compliance Lambda<br/>• Textract Textextraktion (us-east-1 Cross-Region)<br/>• Laden der Markenterminologie-Richtlinien JSON<br/>• Bedrock InvokeModel — Markenkonformitätsprüfung<br/>• Ergebnis: konform / nicht-konform + übereinstimmende Begriffe"]
        RL["4️⃣ Report Lambda<br/>• Asset-Katalog-Generierung (JSON + CSV)<br/>• Moderationsverstoß-Kennzeichnung (requires-review)<br/>• CloudWatch EMF Metrics Emission<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        CATALOG["reports/{execution-id}/asset-catalog.json"]
        CSV["reports/{execution-id}/asset-catalog.csv"]
        FLAGGED["reports/{execution-id}/flagged-assets.json"]
        ERROUT["errors/{execution-id}/{filename}.json"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> VA
    DISC --> TC
    VA --> RL
    TC --> RL
    RL --> CATALOG
    RL --> CSV
    RL --> FLAGGED
    RL --> ERROUT
```

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for ONTAP | Creative Asset Speicher |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Täglicher Auslöser (00:00 UTC) |
| Step Functions | Workflow-Orchestrierung (paralleler Map State) |
| Lambda | Compute (Discovery, Visual Analyzer, Text Compliance, Report) |
| Amazon Rekognition | Visuelle Analyse (Labels, Moderation, Texterkennung) |
| Amazon Textract | Text-Overlay-Extraktion (us-east-1 Cross-Region) |
| Amazon Bedrock | Markenrichtlinien-Konformitätsinferenz (Claude / Nova) |
| SNS | Moderationsverstoß-Alarmbenachrichtigung |
| CloudWatch + X-Ray | Observability (EMF Metrics, Tracing) |
