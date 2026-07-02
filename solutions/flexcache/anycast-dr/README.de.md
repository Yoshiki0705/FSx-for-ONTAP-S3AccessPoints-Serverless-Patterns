# FlexCache AnyCast / DR Pattern

🌐 **Language / Sprache**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Dieses Pattern bietet Designleitfäden, Simulationsdemos und betriebliche Designdokumente für die Implementierung von ONTAP FlexCache AnyCast- und DR-Konfigurationen (Disaster Recovery) in Kombination mit FSx for ONTAP × S3 Access Points × AWS Serverless-Diensten.

## Gelöste Probleme

| Problem | FlexCache AnyCast / DR Lösung |
|---------|-------------------------------|
| Leseleistung für geografisch verteilte Teams | Hot Data vom nächsten FlexCache bereitstellen |
| Cloud Bursting für EDA/Media/HPC | On-Premises Origin + Cloud FlexCache reduziert WAN-Transfers |
| Lesekontinuität während DR | Cache-basierte Lesevorgänge auch bei Origin-Ausfall |
| WAN-Transfervolumen reduzieren | Nur Hot Data cachen, Delta-Transfers |
| Komplexität der Client-Mount-Konfiguration | Einzelner Mountpoint über AnyCast IP |

## Erfolgskennzahlen

| Kennzahl | Ziel |
|----------|------|
| Ausfallerkennungszeit | < 30 Sek. |
| DNS-Propagierungszeit | < 60 Sek. |
| Lesekontinuität während Failover | > 99,9% |
| Cache-Trefferquote (Hot Data) | > 80% |
| WAN-Transfer-Reduktion | > 60% |

---

## Bereitstellung

Stellen Sie mit der AWS SAM CLI bereit (ersetzen Sie die Platzhalter-Parameter für Ihre Umgebung):

```bash
# パラメータファイルを編集
cp params/staging.json params/flexcache-anycast-demo.json
# 必要なパラメータを設定

# デプロイ
# Voraussetzung: AWS SAM CLI erforderlich. „sam build“ verpackt Code und Shared Layer automatisch.
sam build

sam deploy \
  --stack-name flexcache-anycast-demo \
  --capabilities CAPABILITY_NAMED_IAM \
  --resolve-s3 \
  --parameter-overrides \
    SimulationMode=true \
    CacheEndpoints="cache-a.example.com,cache-b.example.com" \
    HealthCheckIntervalMinutes=5
```

> **Hinweis**: `template.yaml` ist für die Verwendung mit der AWS SAM CLI (`sam build` + `sam deploy`) vorgesehen.
> Für eine direkte Bereitstellung mit `aws cloudformation deploy` verwenden Sie stattdessen `template-deploy.yaml` (erfordert das vorherige Packen der Lambda-Zip-Dateien und das Hochladen in einen S3-Bucket).

## Governance-Hinweis

> Dieses Pattern bietet technische Architekturberatung. Es stellt keine rechtliche, Compliance- oder regulatorische Beratung dar. Organisationen sollten qualifizierte Fachleute konsultieren.
