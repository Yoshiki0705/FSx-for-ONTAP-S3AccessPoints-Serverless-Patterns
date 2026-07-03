# SAP/ERP Adjacent File Workflow Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

Serverless-Pattern zur Verarbeitung von SAP-IDoc-Exporten, per HULFT abgelegten Dateien, EDI-Landing-Zone-Dateien und Batch-Job-Ausgaben, die auf FSx for ONTAP gespeichert und über S3 Access Points zugänglich sind.

## Use Cases

> **Scope note**: Dieses Pattern ist für SAP/ERP-nahe Datei-Landing-Zones wie IDoc-Exporte, EDI-Dateien, HULFT-Übertragungen, Audit-Extrakte und Batch-Ausgaben vorgesehen. Es ist nicht dafür gedacht, zertifizierte SAP-Integrationsmechanismen oder transaktionale ERP-Schnittstellen zu ersetzen. Für die SAP-zertifizierte Speicherintegration siehe die [AWS SAP on FSx for ONTAP documentation](https://docs.aws.amazon.com/sap/latest/sap-hana/sap-hana-amazon-fsx.html).

- **Verarbeitung von SAP-IDoc-Exporten**: Parsen und Zusammenfassen von IDoc-Flatfiles (ORDERS, INVOIC, DESADV)
- **HULFT-Dateiablage**: Verarbeitung von Dateien, die per HULFT/DataSpider zu FSx for ONTAP übertragen werden
- **EDI-Eingangsverarbeitung**: Verarbeitung von EDI-X12/EDIFACT-Dokumenten in Landing-Zones
- **Batch-Job-Ausgabe**: Analyse von Ausgaben aus Mainframe-Batch-Jobs, JCL-Ausgaben oder geplanten Berichten
- **ERP-Datenextrakt**: Verarbeitung von CSV/XML-Extrakten aus SAP, Oracle EBS oder anderen ERP-Systemen

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────────────┐ │
│  │  EventBridge │     │         Step Functions Workflow           │ │
│  │  Scheduler   │────▶│                                          │ │
│  │              │     │  ┌──────────┐  ┌──────────┐  ┌────────┐ │ │
│  │ rate(1 hour) │     │  │Discovery │─▶│Processing│─▶│ Report │ │ │
│  └──────────────┘     │  │ Lambda   │  │ Lambda   │  │ Lambda │ │ │
│                       │  └────┬─────┘  └────┬─────┘  └───┬────┘ │ │
│                       └───────┼─────────────┼─────────────┼──────┘ │
│                               │             │             │        │
│                               ▼             ▼             ▼        │
│                       ┌──────────────┐ ┌─────────┐  ┌─────────┐   │
│                       │ FSx for ONTAP│ │ Amazon  │  │  Amazon │   │
│                       │ via S3 AP    │ │ Bedrock │  │   SNS   │   │
│                       │              │ │ (Nova)  │  │         │   │
│                       │ ListObjectsV2│ │Summarize│  │ Email   │   │
│                       │ GetObject    │ │Classify │  │ Notify  │   │
│                       └──────────────┘ └─────────┘  └─────────┘   │
│                                              │                     │
│                                              ▼                     │
│                                        ┌──────────┐                │
│                                        │ S3 Output│                │
│                                        │  Bucket  │                │
│                                        └──────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

1. **Discovery** — Listet Dateien auf FSx for ONTAP über S3 Access Point auf (`ListObjectsV2`), gefiltert nach Präfix
2. **Processing** — Für jede Datei: liest den Inhalt über S3 AP (`GetObject`) und sendet ihn zur Zusammenfassung/Klassifizierung an Amazon Bedrock
3. **Report** — Erstellt eine Ausführungszusammenfassung, schreibt sie nach S3 und sendet eine SNS-Benachrichtigung

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `S3AccessPointAlias` | S3-AP-Alias für das FSx-for-ONTAP-Volume | (erforderlich) |
| `OntapSecretArn` | Secrets-Manager-ARN für ONTAP-Anmeldeinformationen | (erforderlich) |
| `ScheduleExpression` | Ausführungshäufigkeit | `rate(1 hour)` |
| `OutputBucketName` | S3-Bucket für Ergebnisse | (erforderlich) |
| `NotificationEmail` | E-Mail für SNS-Benachrichtigungen | (erforderlich) |
| `FilePrefix` | Zu scannendes Verzeichnispräfix | `idoc-export/` |
| `BedrockModelId` | Bedrock-Modell für die Zusammenfassung | `amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Maximale Anzahl Dateien pro Lauf | `100` |

## Deployment

```bash
# Voraussetzung: AWS SAM CLI ist erforderlich. sam build paketiert den Code und die gemeinsam genutzten Layer automatisch.
sam build
sam deploy --guided --stack-name fsxn-s3ap-sap-erp \
  --parameter-overrides \
    S3AccessPointAlias=my-sap-s3ap-alias \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:my-secret \
    OutputBucketName=my-sap-output-bucket \
    NotificationEmail=ops-team@example.com \
    FilePrefix="idoc-export/" \
    ScheduleExpression="cron(0 */2 * * ? *)"
```

> **Hinweis**: `template.yaml` wird mit der SAM CLI (`sam build` + `sam deploy`) verwendet.
> Für ein direktes Deployment mit dem Befehl `aws cloudformation deploy` verwenden Sie `template-deploy.yaml` (dies erfordert das vorherige Paketieren der Lambda-Zip-Dateien und deren Hochladen nach S3).

## Customization

### Change the file prefix for different landing zones:

- SAP IDoc: `FilePrefix=idoc-export/`
- HULFT: `FilePrefix=hulft-landing/`
- EDI: `FilePrefix=edi-inbound/`
- Batch: `FilePrefix=batch-output/`

### Adjust Bedrock prompt:

Bearbeiten Sie `functions/processing/index.py`, um den Zusammenfassungs-Prompt an Ihre Dokumenttypen anzupassen.

## Related

- [Enterprise Workload Examples](../docs/enterprise-workload-examples.md) — Vollständige Liste der Enterprise-Patterns
- [Quick Start Guide](../docs/quick-start.md) — Anleitung für das erste Deployment
- [Deployment Profiles](../docs/deployment-profiles.md) — Konfigurationsoptionen für die Produktion

---

## Kostenschätzung (monatliche Näherung)

> **Hinweis**: Das Folgende ist eine Näherung für die Region ap-northeast-1; die tatsächlichen Kosten variieren je nach Nutzung. Prüfen Sie die aktuellen Preise mit dem [AWS Pricing Calculator](https://calculator.aws/).

### Serverless-Komponenten (nutzungsbasierte Abrechnung)

| Dienst | Stückpreis | Angenommene Nutzung | Monatliche Näherung |
|---------|------|-----------|---------|
| Lambda | $0.0000166667/GB-sec | 3 Funktionen × 100 files/Tag | ~$1-5 |
| S3 API (GetObject/ListObjects) | $0.0047/10K requests | ~10K requests/Tag | ~$1.5 |
| Step Functions | $0.025/1K state transitions | ~1K transitions/Tag | ~$0.75 |
| Bedrock (Nova Lite) | $0.00006/1K input tokens | ~50K tokens/Ausführung | ~$3-10 |
| Athena | $5/TB scanned | N/A | ~$0.5-2 |
| SNS | $0.50/100K notifications | ~100 notifications/Tag | ~$0.15 |
| CloudWatch Logs | $0.76/GB ingested | ~1 GB/Monat | ~$0.76 |

### Fixkosten (FSx for ONTAP — vorhandene Umgebung vorausgesetzt)

| Komponente | Monatlich |
|--------------|------|
| FSx for ONTAP (128 MBps, 1 TB) | ~$230 (gemeinsam mit vorhandener Umgebung) |
| S3 Access Point | Keine zusätzlichen Gebühren (nur S3-API-Gebühren) |

### Gesamtnäherung

| Konfiguration | Monatliche Näherung |
|------|---------|
| Minimale Konfiguration (einmal täglich) | ~$5-15 |
| Standardkonfiguration (stündlich) | ~$15-50 |
| Große Konfiguration (hohe Frequenz + Alarme) | ~$50-150 |

> **Governance Caveat**: Kostenschätzungen sind Näherungen, keine garantierten Werte. Die tatsächlichen Gebühren variieren je nach Nutzungsmuster, Datenvolumen und Region.

---

## Lokales Testen

### Prüfung der Prerequisites

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
# Voraussetzung: AWS SAM CLI ist erforderlich. sam build paketiert den Code und die gemeinsam genutzten Layer automatisch.
sam build

# Discovery Lambda lokal ausführen
sam local invoke DiscoveryFunction --event events/discovery-event.json

# Mit Überschreibung von Umgebungsvariablen
sam local invoke DiscoveryFunction \
  --event events/discovery-event.json \
  --env-vars env.json
```

### Unit-Tests

```bash
python3 -m pytest tests/ -v
```

Weitere Einzelheiten finden Sie im [Schnellstart für lokales Testen](../docs/local-testing-quick-start.md).

---

## Ausgabebeispiel (Output Sample)

Beispielausgabe des SAP/ERP-Dateiverarbeitungs-Workflows:

```json
{
  "discovery": {
    "status": "completed",
    "object_count": 15,
    "prefix": "idoc-export/",
    "categories": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3}
  },
  "processing": [
    {
      "key": "idoc-export/ORDERS_20260523_001.idoc",
      "status": "completed",
      "category": "sap_idoc",
      "summary": "Kundenauftrags-IDoc (ORDERS05). Geschäftspartner: Sample Corporation, Bestellnummer: PO-2026-001, Betrag: 2,500,000 JPY",
      "document_type": "ORDERS05",
      "key_fields": ["BELNR", "KUNNR", "NETWR", "WAERK"]
    }
  ],
  "report": {
    "total_files": 15,
    "succeeded": 14,
    "failed": 1,
    "success_rate_pct": 93.3,
    "category_breakdown": {"sap_idoc": 8, "hulft_transfer": 4, "data_extract": 3},
    "report_key": "reports/sap-erp-summary-1716480000.json"
  }
}
```

> **Hinweis**: Das Obige ist eine Beispielausgabe; die tatsächlichen Werte variieren je nach Umgebung und Eingabedaten. Benchmark-Zahlen sind eine sizing reference, kein service limit.

---

## Governance Note

> Dieses Pattern bietet technische Architekturhinweise. Es handelt sich nicht um rechtliche, Compliance- oder regulatorische Beratung. Organisationen sollten qualifizierte Fachleute konsultieren.

---

## S3AP Compatibility

Zu Kompatibilitätsbeschränkungen, Fehlerbehebung und Trigger-Patterns für S3 Access Points for FSx for ONTAP siehe die [S3AP Compatibility Notes](../docs/s3ap-compatibility-notes.md).
---

## Performance Considerations

- Die Durchsatzkapazität von FSx for ONTAP wird von NFS/SMB/S3AP gemeinsam genutzt
- Die Latenz über den S3 Access Point verursacht einen Overhead von einigen zehn Millisekunden
- Steuern Sie beim Verarbeiten großer Dateimengen den Parallelitätsgrad über MaxConcurrency des Step Functions Map state
- Eine Erhöhung der Lambda-Speichergröße verbessert auch die Netzwerkbandbreite

> **Hinweis**: Die Performance-Zahlen dieses Patterns sind eine sizing reference, kein service limit. Die Performance in realen Umgebungen variiert je nach Durchsatzkapazität von FSx for ONTAP, Netzwerkkonfiguration und gleichzeitig laufenden Workloads.
