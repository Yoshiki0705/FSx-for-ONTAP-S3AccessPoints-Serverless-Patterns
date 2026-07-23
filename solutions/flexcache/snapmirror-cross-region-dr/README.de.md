# SnapMirror Cross-Region DR + S3 Access Points Pattern

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | [Deutsch](README.de.md) | [Español](README.es.md)

## Überblick

Ein Disaster-Recovery-Muster, das über S3 Access Points gesammelte Daten mittels SnapMirror Asynchronous in eine regionsübergreifende Zielumgebung repliziert und bei Failover automatisch einen neuen S3 AP am Zielvolume erstellt.

Im Normalbetrieb werden Daten über den S3 AP auf dem Quellvolume aufgenommen. Bei einem DR-Ereignis orchestriert eine Lambda-Funktion das Failover in ~3 Minuten: SnapMirror break → Junction Path → S3 AP-Erstellung.

## Architektur

```mermaid
graph TB
    subgraph "Normalbetrieb (Region A)"
        WRITER[Writer Lambda]
        S3AP_SRC[S3 Access Point<br/>Quelle]
        SRC_VOL[Quellvolume<br/>vol_sm_dr_source]
    end
    subgraph "Replikation"
        SM[SnapMirror Async<br/>Zeitplan: 5-Minuten-Intervalle]
    end
    subgraph "DR-Failover (Region B)"
        FAILOVER[Failover Lambda]
        S3AP_DST[S3 Access Point<br/>Ziel<br/>(bei Failover erstellt)]
        DST_VOL[Zielvolume (DP)<br/>vol_sm_dr_dest]
        SNS[SNS-Benachrichtigung]
        CLIENT[Anwendungen<br/>(wechseln zum neuen S3 AP)]
    end

    WRITER -->|PutObject| S3AP_SRC
    S3AP_SRC --> SRC_VOL
    SRC_VOL -->|Inkrementelle<br/>Replikation| SM
    SM --> DST_VOL
    FAILOVER -->|1. Break SM<br/>2. Set junction<br/>3. Create AP| DST_VOL
    FAILOVER --> S3AP_DST
    FAILOVER --> SNS
    SNS --> CLIENT
    CLIENT -->|S3 API| S3AP_DST
```

## Schlüsselkomponenten

| Komponente | Beschreibung |
|-----------|-------------|
| Quellvolume + S3 AP | Datenaufnahmepunkt (Region A). Normalbetrieb |
| SnapMirror Async | Inkrementelle Replikation auf Volume-Ebene (RPO = Zeitplanintervall) |
| Zielvolume (DP) | Datenschutzvolume (schreibgeschützt bis Break). Erstellt über FSx API (SM-VAL-009) |
| Failover Lambda | Automatisiert: Break → Junction → S3 AP-Erstellung. RTO ~3 Min. |
| SNS Topic | Benachrichtigt Anwendungen über neuen S3 AP-Endpunkt nach Failover |

## RTO / RPO

| Metrik | Wert | Hinweise |
|--------|:----:|---------|
| **RTO** | ~3 Minuten | SnapMirror break (sofort) + Junction-Propagierung (~2 Min.) + S3 AP-Erstellung (~30s) |
| **RPO** | ≤ SnapMirror-Zeitplan | Standard 5-Minuten-Zeitplan. Daten seit letztem Transfer können verloren gehen |

## Voraussetzungen

- 2 FSx for ONTAP-Cluster in verschiedenen Regionen
- VPC Peering mit Cluster/SVM Peering eingerichtet
- DP-Zielvolume erstellt über `aws fsx create-volume` (nicht allein über ONTAP REST API — SM-VAL-009)
- SnapMirror-Beziehung initialisiert und im Status `snapmirrored`
- fsxadmin-Anmeldedaten in Secrets Manager (beide Regionen)
- Lambda VPC-Zugriff auf Ziel-ONTAP-Management-IP (Port 443)

## Bereitstellung

```bash
# 1. Stack bereitstellen (erstellt Quellvolume, Ziel-DP-Volume, Failover Lambda, SNS)
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-sm-dr \
  --parameter-overrides file://params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Quell-S3 AP + SnapMirror-Beziehung erstellen
#    (siehe PostDeployInstructions in den Stack-Ausgaben)

# 3. Failover testen (Testlauf)
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{"dry_run": true}' \
  /tmp/dr-dryrun.json
```

## Failover ausführen

```bash
# DR-Failover auslösen
aws lambda invoke \
  --function-name fsxn-sm-dr-failover-dev \
  --payload '{}' \
  /tmp/dr-result.json

# Ergebnis prüfen
cat /tmp/dr-result.json
# → {"s3_access_point": {"arn": "...", "alias": "..."}, ...}
```

## Überprüfung

```bash
# Nach dem Failover vom Ziel-S3 AP lesen
aws s3api list-objects-v2 \
  --bucket <dest-s3-ap-alias>

aws s3api get-object \
  --bucket <dest-s3-ap-alias> \
  --key test/sample.txt \
  /tmp/recovered.txt
```

## Technische Einschränkungen

| Einschränkung | Details |
|--------------|---------|
| Nur SnapMirror Asynchronous | Synchroner Modus wird für S3 NAS Bucket-Volumes NICHT unterstützt |
| SVM-DR nicht unterstützt | SVM mit S3 NAS Bucket blockiert SVM-DR. Nur SnapMirror auf Volume-Ebene |
| DP-Volume über FSx API | SM-VAL-009: Nur über ONTAP REST API erstellte Volumes sind für FSx API unsichtbar, blockiert S3 AP |
| S3 AP wird nicht übertragen | SM-002: S3 AP ist eine AWS-Schicht-Ressource. Neuer AP am Ziel erforderlich |
| Client-Anwendungsupdate | Neuer AP hat anderen ARN/Alias. Anwendungen müssen Endpunkt wechseln |
| SnapMirror-Zeitplan | FSx for ONTAP Minimum: 5-Minuten-Intervalle |

## Aufräumen (Reihenfolge kritisch — SM-VAL-011)

```bash
# ⚠️ Exakte Reihenfolge einhalten, um verwaiste Ressourcen zu vermeiden

# 1. SnapMirror-Beziehung löschen (vom ZIEL-Cluster)
#    ONTAP REST: DELETE /api/snapmirror/relationships/<uuid>?destination_only=true
#    Dann von der QUELLE: snapmirror release (ONTAP CLI)

# 2. SVM Peers löschen (BEIDE Cluster) — beide Seiten abfragen bis num_records: 0

# 3. Cluster Peers löschen (beide Cluster)

# 4. VPC Peering löschen (erst nach Bestätigung von Schritt 2)

# 5. S3 Access Points trennen/löschen (Quelle und Ziel, falls erstellt)
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <src-arn>
aws fsx detach-and-delete-s3-access-point --s3-access-point-arn <dest-arn>

# 6. CloudFormation-Stack löschen
aws cloudformation delete-stack --stack-name fsxn-sm-dr
```

## Referenzen

- [NetApp Docs: S3 multiprotocol — Data protection](https://docs.netapp.com/us-en/ontap/s3-multiprotocol/index.html)
- [NetApp KB: SVM DR of S3 buckets](https://kb.netapp.com/on-prem/ontap/DP/SnapMirror-KBs/Is_SVM_Disaster_Recovery_(SVM_DR)_of_S3_buckets_supported%3F)
- [AWS Docs: FSx for ONTAP SnapMirror](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/scheduled-replication.html)
- [AWS Docs: FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [NetApp Docs: FlexCache supported features](https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html)
