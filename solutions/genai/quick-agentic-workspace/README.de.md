# Amazon Quick Agentic Workspace auf FSx for ONTAP

🌐 **Language / Sprache**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Ein Muster, das Amazon FSx for NetApp ONTAP **über S3 Access Points** als Datengrundlage für **Amazon Quick Suite** (den agentischen KI-Arbeitsbereich) nutzt. Daten, die Fachbereiche per Windows-Dateioperationen pflegen, werden über Quicks Funktionen (Index / Sight / Flows / Research) übergreifend genutzt.

Anders als UC29 (Self-Service-Ingestion in eine managed Bedrock-KB) fokussiert UC30 auf **einen agentischen Arbeitsbereich, der unstrukturierte Suche, BI und Aktionsautomatisierung vereint**.

> Amazon Quick Suite, veröffentlicht im Oktober 2025. Funktionen/Preise/Regionen sind zeitabhängig; siehe [aws.amazon.com/quick](https://aws.amazon.com/quick/).

## Quick-Funktionen und S3 AP

| Quick-Funktion | Daten (S3 AP) | Umsetzung |
|-----------|--------------|------|
| Quick Index / Research | `index/<role>/` (unstrukturiert) | S3 AP als schreibgeschützte Datenquelle |
| Quick Sight (BI) | `analytics/<role>/` (csv) | Glue/Athena (Athena Query Lambda) |
| Quick Flows | `flows/<role>/` (json) | Action API (API Gateway + Lambda + Bedrock) |

## Zwei Demo-Szenarien

| Szenario | Zusammenfassung |
|---------|------|
| **A: Manueller Arbeitsbereich** | Daten per Windows ablegen; Quick Index verbinden, Quick-Sight-Datasets erstellen, Quick Flows manuell ausführen |
| **B: Automatisierung** | Datenaufbereitung, BI-Abfragen und Aktionen serverless automatisieren (Data Prep / Athena Query / Action API) |

## Rollen × Services

Rollen entsprechen Amazon Quicks Zielen (sales, marketing, IT, operations, finance, legal + developers). Beispieldaten in [`sample-data/quick-workspace/`](sample-data/). Rollenlayout mit UC29 geteilt.

```
quick-workspace/
├── index/<role>/      … Quick Index / Research
├── analytics/<role>/  … Quick Sight (Athena)
└── flows/<role>/      … Quick Flows (Action API)
```

## Sicherheit

- Keine Datenbewegung (Original auf FSx for ONTAP; S3 AP nur lesend)
- Die Action API nutzt IAM-Authentifizierung (SigV4) — kein unauthentifizierter öffentlicher Endpunkt
- Least Privilege, Verschlüsselung (SSE-FSX/SSE-S3/TLS)
- Quick-Datenquellenverbindungen werden in der Quick-Konsole konfiguriert

## Bereitstellung

Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter für Ihre Umgebung):

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-quick-agentic-workspace \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket).

> **Amazon-Quick-Konfiguration**: Das Verbinden eines Index, das Erstellen von Datasets und das Ausführen von Flows liegen außerhalb des Umfangs dieser Vorlage. Konfigurieren Sie sie nach der Bereitstellung in der Amazon-Quick-Konsole (siehe [quick-console-setup](docs/quick-console-setup.md)).

## Governance Note

> Technische Architekturhinweise, keine rechtliche oder Compliance-Beratung. Quick-Funktionen/Preise ändern sich; offizielle Quellen prüfen.
