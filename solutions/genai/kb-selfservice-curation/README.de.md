# Self-Service-Kuratierung der Wissensdatenbank

🌐 **Language / Sprache**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Ein Muster, mit dem Fachanwender eine Datenquelle für Amazon Bedrock Knowledge Base **allein per Drag-and-drop im vertrauten Windows-Explorer** pflegen.

Ein **KI-spezifisches Volume/Ordner** auf FSx for ONTAP wird per SMB für jede Rolle/Abteilung freigegeben. Dieselben Daten werden **über S3 Access Points (Lesepfad)** als Datenquelle an eine Amazon Bedrock Knowledge Base angebunden; Dateiänderungen lösen die **automatische Ingestion** aus.

So wird aus „manuelles ETL/Kopieren/Ingestion durch die IT pro Anfrage" ein **demokratisiertes Modell, bei dem der Fachbereich sein Wissen selbst pflegt**.

## Vorher / Nachher

> **Hinweis**: verallgemeinerte Betriebsgeschichte mit maskierten Kunden-, Personen- und Teamnamen.

- **Vorher**: Anfrage des Fachbereichs → IT kopiert manuell von einem Windows Server auf EC2 → S3-Upload → manuelle Ingestion in Bedrock KB. Engpass pro Anfrage, doppelte Datenhaltung.
- **Nachher**: „Legt die Daten für die KI in diesen Windows-Ordner und pflegt sie selbst." Nutzer ziehen wie gewohnt per Drag-and-drop; die KB synchronisiert automatisch über S3 AP.

## Zwei Demo-Szenarien

Dieselbe Grundlage unterstützt je nach Betriebsreife zwei Stufen (siehe [Demo-Leitfaden](docs/demo-guide.md)):

| Szenario | Zusammenfassung | Ingestion-Auslöser |
|---------|------|-------------------|
| **A: Manuelle Praxis** | KI-Daten per Windows-Dateioperationen pflegen (Hinzufügen/Ändern/Löschen); Ingestion manuell ausgelöst (Konsole „Sync"/CLI) | Manuell |
| **B: Automatisierung** | Die manuelle Synchronisation aus A mit Lambda + Step Functions + EventBridge automatisieren (erkennen→ingestieren→warten→benachrichtigen) | Automatisch |

> Die Aktion des Fachanwenders (Drag-and-drop) ist in beiden gleich. Nur die Schritte nach der Ingestion unterscheiden sich – durch eine Person oder durch Serverless.

## Gelöste Probleme

| Problem | Lösung |
|------|--------|
| Wissensaktualisierung wartet auf manuelle IT-Arbeit | Fachbereich pflegt per Windows; automatische Ingestion |
| Doppelte Datenhaltung durch S3-Kopien | Direkte Datenquelle aus dem FSx-ONTAP-Original über S3 AP |
| Verpasste Ingestion/Aktualisierung | Änderungserkennung und automatische Ingestion |
| ETL/S3/Bedrock-Kenntnisse nötig | Nur Windows-Drag-and-drop |
| Unklare Datenverantwortung | Ordnerstruktur nach Rolle/Abteilung |

## Managed KB vs. Custom RAG

Dieser UC nutzt **managed Bedrock Knowledge Bases (Pattern C)**, um den Betriebsaufwand zu minimieren. Für Berechtigungsfilterung auf Dateiebene zur Suchzeit wählen Sie Custom RAG ([FC3 genai-rag-enterprise-files](../genai-rag-enterprise-files/), Pattern A).

> **Bereitstellungsvoraussetzung**: Erstellen Sie Knowledge Base und Datenquelle mit [`scripts/create_bedrock_kb.py`](../scripts/create_bedrock_kb.py) oder der Bedrock-Konsole und übergeben Sie deren IDs als Template-Parameter.

## Sicherheit

- Keine Datenbewegung (Original bleibt auf FSx for ONTAP; S3 AP nur lesend)
- Schreiben nur über SMB/NFS; der KI-Ingestion-Pfad (S3 AP) liest
- NTFS-ACLs pro Ordner trennen Schreibrechte je Abteilung
- Die S3-AP-Datenquellengrenze liegt auf Volume-/Präfixebene (Sichtbarkeitssteuerung pro Nutzer ist außerhalb des Umfangs)

## Bereitstellung

Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter für Ihre Umgebung):

> **Bereitstellungsvoraussetzung**: Diese Vorlage setzt eine vorhandene Amazon Bedrock Knowledge Base und Datenquelle (mit dem S3 AP verbunden) voraus. Da die Erstellung des OpenSearch-Serverless-Vektorindex nicht CloudFormation-nativ ist, erstellen Sie die Knowledge Base zuerst und übergeben deren `KnowledgeBaseId` / `DataSourceId` als Parameter (mit `scripts/create_bedrock_kb.py` im Repo-Stammverzeichnis oder der Bedrock-Konsole).

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name fsxn-kb-selfservice-curation \
  --parameter-overrides \
    S3AccessPointAlias=<your-s3ap-alias> \
    S3AccessPointName=<your-s3ap-name> \
    KnowledgeBaseId=<your-kb-id> \
    DataSourceId=<your-datasource-id> \
    NotificationEmail=<your-email@example.com> \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --region <your-region>
```

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket).

## Governance Note

> Dieses Muster bietet technische Architekturhinweise, keine rechtliche oder Compliance-Beratung. Konsultieren Sie qualifizierte Fachleute.
