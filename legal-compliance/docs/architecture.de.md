# UC1: Recht / Compliance — Dateiserver-Audit & Datengovernance

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        FILES["Dateiserver-Daten<br/>Dateien mit NTFS-ACLs"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / ONTAP REST API"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(24 hours)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateiliste<br/>• ONTAP-Metadaten-Sammlung<br/>• Sicherheitsstil-Überprüfung"]
        ACL["2️⃣ ACL Collection Lambda<br/>• ONTAP REST API-Aufrufe<br/>• file-security-Endpunkt<br/>• NTFS ACL / CIFS-Freigabe-ACL-Abruf<br/>• JSON Lines-Ausgabe nach S3"]
        ATH["3️⃣ Athena Analysis Lambda<br/>• Glue Data Catalog aktualisieren<br/>• Athena SQL-Abfragen ausführen<br/>• Erkennung übermäßiger Berechtigungen<br/>• Erkennung veralteter Zugriffe<br/>• Erkennung von Richtlinienverstößen"]
        RPT["4️⃣ Report Generation Lambda<br/>• Amazon Bedrock (Nova/Claude)<br/>• Compliance-Bericht-Erstellung<br/>• Risikobewertung & Abhilfevorschläge<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        ACLDATA["acl-data/*.jsonl<br/>ACL-Informationen (datumspartitioniert)"]
        ATHENA["athena-results/*.csv<br/>Ergebnisse der Verstoßerkennung"]
        REPORT["reports/*.md<br/>KI-Compliance-Bericht"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Email / Slack"]
    end

    FILES --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> ACL
    ACL --> ATH
    ATH --> RPT
    ACL --> ACLDATA
    ATH --> ATHENA
    RPT --> REPORT
    RPT --> SNS
```

---

## Datenfluss-Details

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | Alle Dateien (mit NTFS-ACLs) |
| **Zugriffsmethode** | S3 Access Point (Dateiliste) + ONTAP REST API (ACL-Informationen) |
| **Lesestrategie** | Nur Metadaten (Dateiinhalte werden nicht gelesen) |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Discovery | Lambda (VPC) | Dateien über S3 AP auflisten, ONTAP-Metadaten sammeln |
| ACL Collection | Lambda (VPC) | NTFS ACL / CIFS-Freigabe-ACL über ONTAP REST API abrufen |
| Athena Analysis | Lambda + Glue + Athena | SQL-basierte Erkennung übermäßiger Berechtigungen, veralteter Zugriffe, Richtlinienverstöße |
| Report Generation | Lambda + Bedrock | Compliance-Bericht in natürlicher Sprache erstellen |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| ACL-Daten | `acl-data/YYYY/MM/DD/*.jsonl` | ACL-Informationen pro Datei (JSON Lines) |
| Athena-Ergebnisse | `athena-results/{id}.csv` | Ergebnisse der Verstoßerkennung (übermäßige Berechtigungen, verwaiste Dateien usw.) |
| Compliance-Bericht | `reports/YYYY/MM/DD/compliance-report-{id}.md` | Von Bedrock erstellter Bericht |
| SNS-Benachrichtigung | Email | Zusammenfassung der Audit-Ergebnisse und Berichtsstandort |

---

## Wichtige Designentscheidungen

1. **S3 AP + ONTAP REST API Kombination** — S3 AP für Dateilisten, ONTAP REST API für detaillierten ACL-Abruf (Zwei-Stufen-Ansatz)
2. **Kein Lesen von Dateiinhalten** — Für Audit-Zwecke werden nur Metadaten/Berechtigungsinformationen gesammelt, um Datenübertragungskosten zu minimieren
3. **JSON Lines + Datumspartitionierung** — Balance zwischen Athena-Abfrageeffizienz und historischer Nachverfolgung
4. **Athena SQL für Verstoßerkennung** — Flexible regelbasierte Analyse (Everyone-Berechtigungen, 90 Tage ohne Zugriff usw.)
5. **Bedrock für Berichte in natürlicher Sprache** — Sicherstellung der Lesbarkeit für nicht-technisches Personal (Rechts-/Compliance-Teams)
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Enterprise-Dateispeicher (mit NTFS-ACLs) |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Periodischer Auslöser (tägliches Audit) |
| Step Functions | Workflow-Orchestrierung |
| Lambda | Compute (Discovery, ACL Collection, Analysis, Report) |
| Glue Data Catalog | Schema-Verwaltung für Athena |
| Amazon Athena | SQL-basierte Berechtigungsanalyse & Verstoßerkennung |
| Amazon Bedrock | KI-Compliance-Bericht-Erstellung (Nova / Claude) |
| SNS | Benachrichtigung über Audit-Ergebnisse |
| Secrets Manager | ONTAP REST API-Anmeldeinformationsverwaltung |
| CloudWatch + X-Ray | Observability |
