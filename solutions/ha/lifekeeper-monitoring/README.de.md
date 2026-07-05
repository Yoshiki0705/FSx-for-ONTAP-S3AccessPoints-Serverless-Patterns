# HA LifeKeeper Monitoring — FSx for ONTAP S3 AP Pattern

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

## Überblick

Ein Serverless-Pattern, das die Protokolle und Failover-Ereignisse eines mit **SIOS LifeKeeper** aufgebauten Hochverfügbarkeits-Clusters (HA) nicht-invasiv über die S3 Access Points von **Amazon FSx for NetApp ONTAP** erfasst und analysiert.

Die von Amazon Bedrock (Nova Pro) unterstützte **Ursachenanalyse (Root Cause Analysis)** und das **Cluster-Health-Scoring** ermöglichen eine schnelle Ursachenermittlung bei Failover und eine frühzeitige Anzeichenerkennung.

---

## Zielszenario

In Unternehmensumgebungen werden SAP, Oracle und geschäftskritische Anwendungen mit SIOS LifeKeeper HA-geschützt, und FSx for ONTAP Multi-AZ wird als gemeinsam genutzter Speicher verwendet.

**Herausforderungen**:
- Die Ursachenermittlung nach einem Failover ist zeitaufwendig
- Die Analyse von LifeKeeper-Protokollen erfordert viel manuelle Arbeit und hängt von individuellem Fachwissen ab
- Das Hinzufügen eines Überwachungsagenten auf HA-Cluster-Knoten erhöht die Anzahl der Fehlerpunkte
- Die Unterscheidung zwischen Fehlern der Speicherebene (FSx for ONTAP) und der Anwendungsebene (LifeKeeper) ist schwierig

**Lösung**:
Verwenden Sie FSx for ONTAP S3 Access Points, um die von LifeKeeper geschriebenen Protokolle **nicht-invasiv** über eine Serverless-Analysepipeline zu verarbeiten. Die KI-gestützte automatische Analyse reduziert den Betriebsaufwand.

---

## Kombination aus SIOS LifeKeeper + FSx for ONTAP

### Einordnung in die Architektur

| Ebene | Zuständigkeit | HA-Umfang |
|---------|------|------------|
| Speicher | FSx for ONTAP Multi-AZ | Datenverfügbarkeit, AZ-Redundanz, automatisches Failover |
| Anwendung | SIOS LifeKeeper | VIP-Steuerung, Dienstüberwachung, automatische Wiederherstellung |
| Analyse (dieses Pattern) | S3 AP + Serverless + Bedrock | Nicht-invasive Protokollanalyse, KI-Ursachenanalyse |

### Was ist SIOS LifeKeeper

Eine von SIOS Technology bereitgestellte HA-Clustering-Software für Linux/Windows. Sie sorgt für Hochverfügbarkeit geschäftskritischer Anwendungen auf AWS.

**Wesentliche Merkmale**:
- Anwendungsbewusste Recovery Kits (direkte Überwachung von SAP S/4HANA, Oracle, NFS, IP usw.)
- Cross-AZ-Failover (2 AZs innerhalb einer einzigen Region)
- VIP-Verwaltung (Elastic IP / Secondary IP)
- Split-Brain-Vermeidung durch redundante Kommunikationspfade
- Offiziell als AWS Partner Solution verfügbar

**Referenz**: Astro Malaysia hat SIOS LifeKeeper in einer SAP + Oracle on AWS Umgebung eingesetzt und eine Verfügbarkeit von 99,99 % erreicht.

### FSx for ONTAP Shared-Disk-Unterstützung (V10 und höher)

Ab LifeKeeper V10.0.1 kann FSx for ONTAP direkt als Shared Disk geschützt werden. Zuvor war nur DataKeeper (Block-Replikation) verfügbar; durch das Hinzufügen einer Shared-Disk-Konfiguration wird eine einfachere HA-Konfiguration möglich.

| Protokoll | Erforderliches Recovery Kit | Hinweise |
|-----------|-------------------|------|
| iSCSI | DMMP Recovery Kit | Erforderlich bei Verwendung von FSx for ONTAP auf AWS |
| NFS | NAS Recovery Kit | Standardmäßige NFS-Shared-Disk-Konfiguration |

> Ein Validierungsartikel von SIOS bcblog (2026-05-08) bestätigt, dass der Switchover in einer Konfiguration mit RHEL 9.6 + LifeKeeper v10.0.1 + FSx for ONTAP (iSCSI/NFS) korrekt funktioniert.

### Der Mehrwert von FSx for ONTAP

- **Multi-AZ Shared Storage**: von beiden LifeKeeper-Knoten über NFS/iSCSI erreichbar
- **Automatisches Speicher-Failover**: verarbeitet AZ-Ausfälle der Speicherebene automatisch
- **Snapshot**: bewahrt den Datenzustand vor und nach dem Failover
- **S3 Access Points**: nicht-invasiver Datenzugriffspfad für die Protokollanalyse
- **Multiprotokoll**: stellt SMB + NFS + iSCSI + S3 API aus einem einzigen Volume bereit und vermeidet doppelte Datenhaltung
- **Cloud-nativ**: kann direkt über die AWS Management Console genutzt werden (keine separate Lizenz erforderlich)

> „Der große Vorteil besteht darin, dass man die Daten nicht nach S3 kopieren muss, um sie zu nutzen, sondern die Daten auf FSx for ONTAP direkt über die S3-API verwenden kann" — aus dem [SIOS bcblog Interview-Artikel](https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/) (Content was rephrased for compliance with licensing restrictions)

### Öffentliche Referenzen

| Ressource | Herausgeber | URL |
|------|--------|-----|
| Hochverfügbarkeitslösung mit SIOS LifeKeeper und Amazon FSx for NetApp ONTAP | AWS JAPAN APN Blog | https://aws.amazon.com/jp/blogs/psa/high-availability-solution-with-sios-lifekeeper-and-amazon-fsx-for-netapp-ontap/ |
| Hochverfügbarkeitsdesign mit NetApp ONTAP und LifeKeeper | SIOS Technology (bcblog) | https://bcblog.sios.jp/netapp-ontap-lifekeeper-high-availability-design/ |
| Amazon FSx for NetApp ONTAP als LifeKeeper Shared Disk verwenden | SIOS Technology (bcblog) | https://bcblog.sios.jp/amazon-fsx-netapp-ontap-lifekeeper-shared-disk/ |
| SIOS Protection Suite for Linux on AWS | AWS Partner Solutions | https://aws.amazon.com/solutions/partners/sios-protection-suite/ |
| LifeKeeper for Linux — Architecture Guide | AWS Quick Start | https://aws-ia.github.io/cfn-ps-sios-protection-suite/ |
| Deploying HA SAP with SIOS on AWS | AWS Blog (2019) | https://aws.amazon.com/blogs/awsforsap/deploying-highly-available-sap-systems-using-sios-protection-suite-on-aws/ |
| Using SIOS to Protect your Critical Core on AWS | AWS Blog (2020) | https://aws.amazon.com/blogs/awsforsap/using-sios-to-protect-your-critical-core-on-aws/ |
| SQL Server HA with FSx for ONTAP | AWS Blog (2022) | https://aws.amazon.com/blogs/modernizing-with-aws/sql-server-high-availability-amazon-fsx-for-netapp-ontap/ |
| Oracle HA with FSx for ONTAP | AWS Blog (2025) | https://aws.amazon.com/blogs/architecture/building-highly-available-oracle-databases-with-amazon-fsx-for-netapp-ontap/ |
| Astro Malaysia 99.99% Uptime | GlobeNewsWire (2025) | https://www.globenewswire.com/news-release/2025/11/20/3191959/0/en/ |
| LifeKeeper for Linux (AWS Marketplace) | AWS Marketplace | https://aws.amazon.com/marketplace/pp/prodview-5pxfcgrksorlo |

---

## Funktionen

### Discovery Lambda
- Erkennt LifeKeeper-Protokolldateien über FSx for ONTAP S3 AP
- Klassifiziert Protokolle: Failover-Ereignisse / Health-Checks / Konfigurationsänderungen / Recovery-Kit-Protokolle
- Bewertet den Schweregrad automatisch (CRITICAL / HIGH / MEDIUM / LOW)

### Processing Lambda
- Erkennt Zustandsübergänge von LifeKeeper-Ressourcen (ISP→OSF, ISS→ISP usw.)
- Ursachenanalyse über Bedrock (Nova Pro)
- Berechnet einen Cluster-Health-Score (0-100)
- Unterscheidet Fehler der Speicherebene von denen der Anwendungsebene

### Report Lambda
- Erzeugt Health-Reports im Markdown-Format
- Sendet SNS-Failover-Alarme basierend auf Schweregrad-Schwellenwerten
- Enthält empfohlene Aktionen mit LifeKeeper-Befehlen (`lcdstatus`, Prüfung der Kommunikationspfade)

---

## Bereitstellung

### Voraussetzungen

- AWS SAM CLI
- Python 3.12
- FSx for ONTAP Dateisystem + S3 Access Point (nicht erforderlich, wenn DemoMode=true)
- Aktivierter Zugriff auf das Bedrock-Modell (Amazon Nova Pro)

### Schnellbereitstellung

```bash
# Bereitstellung im DemoMode (kein FSx for ONTAP erforderlich)
# Voraussetzung: AWS SAM CLI erforderlich. „sam build" verpackt Code und Shared Layer automatisch.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=true \
    S3AccessPointAlias=your-demo-bucket \
    OutputBucketName=your-output-bucket \
    NotificationEmail=your@email.com
```

> **Hinweis**: `template.yaml` wird mit der SAM CLI (`sam build` + `sam deploy`) verwendet.
> Für eine direkte Bereitstellung mit dem Befehl `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Verpacken der Lambda-Zip-Dateien und deren Upload nach S3).

### Produktionsbereitstellung

```bash
# Voraussetzung: AWS SAM CLI erforderlich. „sam build" verpackt Code und Shared Layer automatisch.
sam build
sam deploy --guided \
  --parameter-overrides \
    DemoMode=false \
    S3AccessPointAlias=your-fsxn-s3ap-alias-s3alias \
    OutputBucketName=your-output-bucket \
    NotificationEmail=ops-team@company.com \
    OntapSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ontap-creds-XXXXXX \
    ScheduleExpression="rate(5 minutes)" \
    FailoverAlertSeverity=HIGH \
    ClusterName=prod-sap-cluster \
    TriggerMode=HYBRID
```

### Parameter

| Parameter | Standard | Beschreibung |
|-----------|-----------|------|
| S3AccessPointAlias | (erforderlich) | FSx for ONTAP S3 AP Alias |
| DemoMode | false | Demo-Modus aktivieren |
| ScheduleExpression | rate(5 minutes) | Überwachungsintervall |
| TriggerMode | POLLING | POLLING / EVENT_DRIVEN / HYBRID |
| BedrockModelId | apac.amazon.nova-pro-v1:0 | Bedrock-Modell für die Analyse |
| FailoverAlertSeverity | CRITICAL | Mindestschweregrad für SNS-Alarme |
| ClusterName | lifekeeper-cluster | LifeKeeper-Clustername |
| OutputDestination | STANDARD_S3 | Ausgabeziel für Reports |
| LogRetentionInDays | 90 | Aufbewahrungsdauer von CloudWatch Logs |

---

## Tests

```bash
# Unit-Tests
python3 -m pytest solutions/ha/lifekeeper-monitoring/tests/ -v

# End-to-End-Test im DemoMode
# (legen Sie zuvor Beispielprotokolle im Demo-S3-Bucket ab)
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn> \
  --input '{"trigger": "manual", "cluster_name": "demo-cluster"}'
```

---

## Health-Score

| Score | Stufe | Bedeutung | Empfohlene Aktion |
|--------|--------|------|---------------|
| 90-100 | HEALTHY | Normal | Regelmäßige Reports prüfen |
| 70-89 | WARNING | Achtung | Kommunikationspfade und Speicher-E/A prüfen |
| 50-69 | DEGRADED | Beeinträchtigt | Zustand über LifeKeeper GUI/CLI prüfen, FSx for ONTAP überwachen |
| 0-49 | CRITICAL | Kritisch | Sofortiges Handeln. Zustand mit `lcdstatus` + ONTAP-Management-CLI prüfen |

---

## Verzeichnisstruktur

```
solutions/ha/lifekeeper-monitoring/
├── template.yaml              # SAM-Vorlage
├── samconfig.toml.example     # Beispiel für Bereitstellungskonfiguration
├── README.md                  # Dieses Dokument (Japanisch)
├── README.en.md               # English README + Success Metrics
├── functions/
│   ├── discovery/
│   │   └── handler.py         # LifeKeeper-Protokollerkennung
│   ├── processing/
│   │   └── handler.py         # Bedrock-Ursachenanalyse
│   └── report/
│       └── handler.py         # Reporterstellung, Alarme
├── statemachine/
│   └── workflow.asl.json      # Step-Functions-Definition
├── docs/
│   ├── architecture.md        # Architekturdetails
│   └── demo-guide.md          # Demo-Leitfaden (DemoMode)
└── tests/
    ├── conftest.py
    └── test_discovery.py      # Unit-Tests
```

---

## Verwandte Patterns

| Pattern | Bezug |
|---------|--------|
| `solutions/sap/erp-adjacent/` | IDoc-/Batch-Verarbeitung von LifeKeeper-geschützten SAP-Umgebungen |
| `solutions/event-driven/fpolicy/` | Sofortige Protokollerkennung über FPolicy-ereignisgesteuerte Auslösung |
| `solutions/flexcache/anycast-dr/` | Referenz für Multi-Region-DR-Konfigurationen |

---

## Governance Note

Dieses Pattern dient der **Unterstützung der betrieblichen Überwachung** von HA-Clustern. Zu beachten:

- KI-Analyseergebnisse sind **Referenzinformationen** für betriebliche Entscheidungen; es erfolgt keine automatische Failover-Steuerung oder Wiederherstellungsoperation
- LifeKeeper-Konfigurationsänderungen müssen stets über LifeKeeper GUI/CLI vorgenommen werden
- Failover-Entscheidungen sind den Health-Check-Mechanismen von LifeKeeper selbst zu überlassen
- Dieses Pattern ist auf ein **Human-in-the-loop** ausgelegt

---

## Performance Considerations

- **Überwachungsintervall**: Ein 5-Minuten-Intervall verursacht bis zu 5 Minuten Erkennungsverzögerung. Wenn Unmittelbarkeit erforderlich ist, kombinieren Sie die FPolicy-ereignisgesteuerte Auslösung mit `TriggerMode=HYBRID`
- **Protokollgröße**: Steuern Sie bei einer großen Anzahl von Protokolldateien die Batchgröße mit `MaxFilesPerExecution`
- **Bedrock-Kosten**: Achten Sie in Umgebungen mit häufigen Failovern auf die Bedrock-Aufrufkosten. Grenzen Sie die Analyseziele mit `FailoverAlertSeverity` ein
- **S3-AP-Durchsatz**: FSx for ONTAP S3 AP teilt sich die Bandbreite des gesamten Dateisystems. Erwägen Sie Snapshot-basierte Lesevorgänge, damit große Mengen an Protokolllesevorgängen die Geschäfts-E/A nicht beeinträchtigen

---

## License

MIT
