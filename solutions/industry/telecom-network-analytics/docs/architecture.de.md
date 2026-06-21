# UC18: Telekommunikation / Netzwerkanalyse — CDR/Netzwerk-Log Anomalieerkennung und Compliance-Berichte

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for ONTAP"]
        DATA["Telekomdaten<br/>.csv/.asn1/.parquet (CDR-Dateien)<br/>syslog / SNMP trap (Netzwerkgeräte-Logs)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>cron(0 0 * * ? *) — Täglich 00:00 UTC"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• VPC-Ausführung<br/>• CDR/Syslog-Dateierkennung<br/>• Suffix-Filter angewendet<br/>• Manifest-Generierung"]
        CA["2️⃣ CDR Analyzer Lambda<br/>• CDR-Abruf über S3 AP<br/>• Anrufmetadaten-Extraktion<br/>(Anrufer-ID, Angerufener-ID, Dauer, Zeitstempel, Funkturm-ID)<br/>• Athena-Verkehrsstatistik-Abfragen<br/>(stündliches Anrufvolumen, Durchschnittsdauer, Spitzen-Gleichzeitigkeitsanrufe)"]
        LA["3️⃣ Log Analyzer Lambda<br/>• Syslog RFC 5424 Parsing<br/>• SNMP-Trap-Analyse<br/>• Geräteausfallserkennung<br/>(Link-Down, Hardware-Fehler, Prozessabsturz)<br/>• Kapazitätsschwellenüberschreitung (Standard 80%)"]
        AD["4️⃣ Anomaly Detector Lambda<br/>• Bedrock InvokeModel<br/>• 7-Tage rollierende Baseline<br/>• 3σ-Schwellen-Anomaliemarkierung<br/>• Anomalie-Bewertung"]
        RL["5️⃣ Report Lambda<br/>• Tägliche Netzwerkgesundheitsübersicht<br/>• Anomalie-Alarmbericht<br/>• S3-Ausgabe (reports/daily/{YYYY-MM-DD}/)<br/>• SNS-Benachrichtigung<br/>• CloudWatch EMF Metrics"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        CDROUT["reports/daily/{YYYY-MM-DD}/cdr-stats.json<br/>CDR-Verkehrsstatistik"]
        LOGOUT["reports/daily/{YYYY-MM-DD}/log-analysis.json<br/>Geräteausfallsanalyse"]
        ANOMOUT["reports/daily/{YYYY-MM-DD}/anomalies.json<br/>Anomalieerkennungsergebnisse"]
        ERROUT["errors/cdr/{filename}.json<br/>CDR-Parse-Fehleraufzeichnungen"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>E-Mail / Slack<br/>(Kritische Anomalie- und Ausfallsalarme)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> CA
    DISC --> LA
    CA --> AD
    LA --> AD
    AD --> RL
    CA --> CDROUT
    LA --> LOGOUT
    AD --> ANOMOUT
    RL --> ERROUT
    RL --> SNS
```

---

## Wichtige Designentscheidungen

1. **Parallele Verarbeitung von CDR und Syslog** — Parallelisierung über Step Functions Map State für Durchsatzverbesserung
2. **Athena für CDR-Aggregation im großen Maßstab** — Serverloses SQL für effiziente Aggregation massiver CDR-Datensätze
3. **7-Tage rollierende Baseline** — Statistische Anomalieerkennung unter Berücksichtigung von Wochentagscharakteristiken
4. **3σ-Schwelle für Anomaliemarkierung** — Erkennt nur statistisch signifikante Anomalien
5. **Fehlerisolation** — CDR-Parse-Fehler werden unter `errors/cdr/` aufgezeichnet ohne den gesamten Batch zu unterbrechen
6. **Polling-basiert** — S3 AP unterstützt keine Ereignisbenachrichtigungen

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|------|
| FSx for ONTAP | CDR/Netzwerk-Log-Speicher |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes |
| EventBridge Scheduler | Täglicher Auslöser (00:00 UTC) |
| Step Functions | Workflow-Orchestrierung (paralleler Map State) |
| Lambda | Compute (Discovery, CDR Analyzer, Log Analyzer, Anomaly Detector, Report) |
| Amazon Athena | CDR-Verkehrsstatistik SQL-Abfragen |
| Amazon Bedrock | Anomalieerkennung-Inferenz (Claude / Nova) |
| SNS | Kritische Anomalie- und Ausfallsalarmbenachrichtigungen |
| Secrets Manager | ONTAP REST API Zugangsdatenverwaltung |
| CloudWatch + X-Ray | Observability (EMF Metrics, Tracing) |
