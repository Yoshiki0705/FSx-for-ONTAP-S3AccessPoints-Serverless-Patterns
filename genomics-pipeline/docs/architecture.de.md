# UC7: Genomik — Qualitätsprüfung und Varianten-Aggregation

🌐 **Language / 言語**: [日本語](architecture.md) | [English](architecture.en.md) | [한국어](architecture.ko.md) | [简体中文](architecture.zh-CN.md) | [繁體中文](architecture.zh-TW.md) | [Français](architecture.fr.md) | Deutsch | [Español](architecture.es.md)

## End-to-End-Architektur (Eingabe → Ausgabe)

---

## Architekturdiagramm

```mermaid
flowchart TB
    subgraph INPUT["📥 Eingabe — FSx for NetApp ONTAP"]
        DATA["Genomdaten<br/>.fastq/.fastq.gz (Sequenzen)<br/>.bam (Alignments)<br/>.vcf/.vcf.gz (Varianten)"]
    end

    subgraph S3AP["🔗 S3 Access Point"]
        ALIAS["S3 AP Alias<br/>ListObjectsV2 / GetObject (Streaming)"]
    end

    subgraph TRIGGER["⏰ Auslöser"]
        EB["EventBridge Scheduler<br/>rate(4 hours)"]
    end

    subgraph SFN["⚙️ Step Functions Workflow"]
        DISC["1️⃣ Discovery Lambda<br/>• Ausführung im VPC<br/>• S3 AP Dateierkennung<br/>• .fastq/.bam/.vcf Filter<br/>• Manifest-Generierung"]
        QC["2️⃣ QC Lambda<br/>• Streaming-Download<br/>• Read-Zählung<br/>• Q30-Score-Berechnung<br/>• GC-Gehalt-Berechnung<br/>• Qualitätsmetriken-Ausgabe"]
        VA["3️⃣ Variant Aggregation Lambda<br/>• VCF-Datei-Parsing<br/>• total_variants Aggregation<br/>• SNP/InDel-Zählung<br/>• Ti/Tv-Verhältnis-Berechnung<br/>• Variantenstatistik-Ausgabe"]
        ATH["4️⃣ Athena Analysis Lambda<br/>• Aktualisierung des Glue Data Catalog<br/>• Ausführung von Athena SQL-Abfragen<br/>• Identifikation von Proben unter dem Qualitätsschwellenwert<br/>• Statistische Analyse"]
        SUM["5️⃣ Summary Lambda<br/>• Bedrock InvokeModel<br/>• Comprehend Medical (us-east-1)<br/>• Biomedizinische Entitätsextraktion<br/>• Forschungszusammenfassung<br/>• SNS-Benachrichtigung"]
    end

    subgraph OUTPUT["📤 Ausgabe — S3 Bucket"]
        QCOUT["qc-metrics/*.json<br/>Qualitätsmetriken"]
        VAROUT["variant-stats/*.json<br/>Variantenstatistiken"]
        ATHOUT["athena-results/*.csv<br/>Qualitätsschwellenwert-Analyse"]
        REPORT["reports/*.md<br/>Forschungszusammenfassung"]
    end

    subgraph NOTIFY["📧 Benachrichtigung"]
        SNS["Amazon SNS<br/>Email / Slack<br/>(Benachrichtigung bei Zusammenfassungsabschluss)"]
    end

    DATA --> ALIAS
    ALIAS --> DISC
    EB --> SFN
    DISC --> QC
    QC --> VA
    VA --> ATH
    ATH --> SUM
    QC --> QCOUT
    VA --> VAROUT
    ATH --> ATHOUT
    SUM --> REPORT
    SUM --> SNS
```

---

## Datenfluss im Detail

### Eingabe
| Element | Beschreibung |
|---------|--------------|
| **Quelle** | FSx for NetApp ONTAP Volume |
| **Dateitypen** | .fastq/.fastq.gz (Sequenzen), .bam (Alignments), .vcf/.vcf.gz (Varianten) |
| **Zugriffsmethode** | S3 Access Point (ListObjectsV2 + GetObject) |
| **Lesestrategie** | FASTQ: Streaming-Download (speichereffizient), VCF: vollständiger Abruf |

### Verarbeitung
| Schritt | Service | Funktion |
|---------|---------|----------|
| Discovery | Lambda (VPC) | Erkennung von FASTQ/BAM/VCF-Dateien über S3 AP, Manifest-Generierung |
| QC | Lambda | Streaming-Extraktion von FASTQ-Qualitätsmetriken (Read-Zählung, Q30, GC-Gehalt) |
| Variant Aggregation | Lambda | VCF-Parsing für Variantenstatistiken (total_variants, snp_count, indel_count, ti_tv_ratio) |
| Athena Analysis | Lambda + Glue + Athena | SQL-basierte Identifikation von Proben unter dem Qualitätsschwellenwert, statistische Analyse |
| Summary | Lambda + Bedrock + Comprehend Medical | Erstellung der Forschungszusammenfassung, biomedizinische Entitätsextraktion |

### Ausgabe
| Artefakt | Format | Beschreibung |
|----------|--------|--------------|
| QC-Metriken | `qc-metrics/YYYY/MM/DD/{sample}_qc.json` | Qualitätsmetriken (Read-Zählung, Q30, GC-Gehalt, durchschnittlicher Qualitätsscore) |
| Variantenstatistiken | `variant-stats/YYYY/MM/DD/{sample}_variants.json` | Variantenstatistiken (total_variants, snp_count, indel_count, ti_tv_ratio) |
| Athena-Ergebnisse | `athena-results/{id}.csv` | Proben unter dem Qualitätsschwellenwert und statistische Analyse |
| Forschungszusammenfassung | `reports/YYYY/MM/DD/research_summary.md` | Von Bedrock generierter Forschungszusammenfassungsbericht |
| SNS-Benachrichtigung | Email | Benachrichtigung bei Zusammenfassungsabschluss und Qualitätswarnungen |

---

## Wichtige Designentscheidungen

1. **Streaming-Download** — FASTQ-Dateien können Dutzende GB erreichen; Streaming-Verarbeitung hält die Speichernutzung innerhalb des Lambda-Limits von 10 GB
2. **Leichtgewichtiges VCF-Parsing** — Extrahiert nur die für die statistische Aggregation minimal erforderlichen Felder, kein vollständiger VCF-Parser
3. **Comprehend Medical regionsübergreifend** — Nur in us-east-1 verfügbar, daher wird ein regionsübergreifender Aufruf verwendet
4. **Athena für Qualitätsschwellenwert-Analyse** — Parametrisierte Schwellenwerte (Q30 < 80 %, abnormaler GC-Gehalt usw.) mit flexibler SQL-Filterung
5. **Sequenzielle Pipeline** — Step Functions verwaltet Reihenfolgeabhängigkeiten: QC → Varianten-Aggregation → Analyse → Zusammenfassung
6. **Polling (nicht ereignisgesteuert)** — S3 AP unterstützt keine Ereignisbenachrichtigungen, daher wird eine periodische geplante Ausführung verwendet

---

## Verwendete AWS-Services

| Service | Rolle |
|---------|-------|
| FSx for NetApp ONTAP | Genomdatenspeicherung (FASTQ/BAM/VCF) |
| S3 Access Points | Serverloser Zugriff auf ONTAP-Volumes (Streaming-Unterstützung) |
| EventBridge Scheduler | Periodische Auslösung |
| Step Functions | Workflow-Orchestrierung (sequenziell) |
| Lambda | Berechnung (Discovery, QC, Variant Aggregation, Athena Analysis, Summary) |
| Glue Data Catalog | Schemaverwaltung für Qualitätsmetriken und Variantenstatistiken |
| Amazon Athena | SQL-basierte Qualitätsschwellenwert-Analyse und statistische Aggregation |
| Amazon Bedrock | Generierung des Forschungszusammenfassungsberichts (Claude / Nova) |
| Comprehend Medical | Biomedizinische Entitätsextraktion (us-east-1 regionsübergreifend) |
| SNS | Benachrichtigung bei Zusammenfassungsabschluss und Qualitätswarnungen |
| Secrets Manager | Verwaltung der ONTAP REST API-Anmeldedaten |
| CloudWatch + X-Ray | Observability |
