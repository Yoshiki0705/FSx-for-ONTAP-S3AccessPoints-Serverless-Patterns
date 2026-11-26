# archive-verify-delete: Archivierung allein mit S3-API-Aufrufen, kopieren, prüfen, nach Freigabe löschen
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)
📚 **Dokumentation**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Überblick
Dieses Muster verschiebt selten gelesene Dateien eines Amazon-FSx-for-NetApp-ONTAP-Volumes (FSx for ONTAP) in S3-Glacier-Speicherklassen. Das Volume wird nicht eingehängt. Verwendet werden ausschließlich S3-API-Aufrufe über S3 Access Points.
Eine Datei durchläuft die folgenden Schritte. Eine Datei, deren Bedingungen unterwegs nicht mehr erfüllt sind, wird vom Löschen ausgenommen.
1. Größe, ETag, SHA-256 und CRC64NVME im Ledger (einer DynamoDB-Tabelle) erfassen
2. Mit `CopyObject` unter Angabe der Speicherklasse in den Archiv-Bucket kopieren
3. Die vom Bucket zurückgegebene Prüfsumme mit dem Wert im Ledger vergleichen
4. Eine Person gibt die Liste der übereinstimmenden Dateien frei
5. Prüfen, dass ETag und Größe am Access Point denen im Ledger entsprechen, und dann die Datei vom Access Point löschen

Zum Wiederherstellen wird die Datei im Ledger gesucht, im Bucket die Wiederherstellung angefordert, auf deren Abschluss gewartet und die Datei mit `CopyObject` zurück in den Access Point kopiert.
Dieses Muster verwendet weder S3 Object Lock noch S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock oder Snapshot-Sperren, und die Vorlage enthält nichts davon. Es wird keine Aufbewahrungsfrist gesetzt, daher können Objekte im Archiv-Bucket von jedem mit Berechtigung gelöscht werden.
Die Annahmen dieses Musters und der Vergleich mit anderen Ansätzen stehen in [Vergleich von 8 Mechanismen zum Verschieben von Dateien in Archivklassen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (auf Japanisch).
## Was gemessen wurde und was nicht
| Kategorie | Inhalt |
|---|---|
| Komponenten, die einzeln je einmal in einer realen Umgebung geprüft wurden (im obigen Vergleich festgehalten; 2026-11-24 und 2026-11-26, ap-northeast-1, erste Generation `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, Volume im UNIX-Stil, Benutzer des Access Points ist UNIX root) | Mit `ChecksumAlgorithm=SHA256` bei `CopyObject` war `ChecksumSHA256` des Buckets `FULL_OBJECT` und gleich dem SHA-256 der Datei (bis 8 MiB). Bei einer 5,5-GiB-Multipart-Kopie wurde SHA-256 zu `COMPOSITE`, und CRC64NVME war `FULL_OBJECT` und gleich. `--copy-source-if-match` mit einem alten ETag lieferte `PreconditionFailed`. `DeleteObject` des Access Points unterstützt `If-Match` nicht. Eine SDK-Integration von Step Functions akzeptierte den Alias des Access Points als `Bucket` |
| In diesem Repository geprüft | Unit-Tests mit moto sowie Tests der Struktur von Zustandsautomat und IAM. Keine Verbindung zu AWS |
| Noch nicht geprüft | Ein durchgängiger Lauf des gesamten Musters in einer realen Umgebung. Dauer und Kosten bei vielen Dateien. Dauer der Hash-Berechnung in Lambda für Dateien nahe 5 GiB. Die Multipart-Kopie über Fargate in einer realen Umgebung. Wie das Stammverzeichnis in der ONTAP-REST-API anzugeben ist und die Darstellung von `unix_permissions`. `ItemReader` und `ResultWriter` von Distributed Map in einer realen Umgebung. Wiederherstellung aus den beiden Klassen, die eine Wiederherstellung erfordern. NTFS-Volumes, Benutzer außer root, zweite Generation, Multi-AZ |
Beim Prüfen vor dem Löschen bleibt ein Schreibfenster. `DeleteObject` des Access Points unterstützt kein bedingtes Löschen, daher wird ein Schreibvorgang zwischen der Prüfung mit `HeadObject` und dem Löschen nicht erkannt. Das Fenster entspricht einem API-Aufruf-Roundtrip.
## Ablauf
### Archivierung
`olderThanDays` ist in der Eingabe erforderlich, und `dryRun` ist standardmäßig `true`.
| Schritt | Verarbeitung | Umsetzung |
|---|---|---|
| 1. Auswählen | `MTIME`: `LastModified` aus `ListObjectsV2` des Access Points. `ATIME`: `accessed_time` aus der ONTAP-REST-API (Lambda im VPC) | `select`, `ontap_rest` |
| 2. Erfassen | Größe, ETag, SHA-256, CRC64NVME und, falls verfügbar, uid, gid, mode, mtime, atime im Ledger. Lambda bis 5 GiB, darüber Fargate | `record`, Fargate-Task |
| 3. Kopieren | Bis 5 GiB: `copyObject` per SDK-Integration (`SHA256`, der ETag aus dem Ledger als `CopySourceIfMatch`). Darüber: Multipart-Kopie durch Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Prüfen | Größe und Prüfsumme aus `HeadObject` des Buckets (`ChecksumMode=ENABLED`) mit dem Ledger vergleichen. Eine Abweichung bleibt als `MISMATCH` und die Datei wird vom Löschen ausgenommen | `ledger` |
| 5. Zweite Kopie (optional) | Vom Access Point in einen anderen Bucket derselben Region kopieren und ebenso prüfen. Bei Abweichung wird die Datei vom Löschen ausgenommen | Step Functions, `ledger` |
| 6. Freigeben | Die Liste der Übereinstimmungen nach `manifests/<runId>.json` schreiben, per SNS benachrichtigen und mit `waitForTaskToken` warten | `approval` |
| 7. Löschen | Nur bei `dryRun=false`. Je Datei ETag und Größe prüfen und bei Gleichheit `DeleteObject` aufrufen. Bei Abweichung bleibt `CHANGED` | `delete` |
| 8. Festhalten | `manifests/<runId>-result.json` und EMF-Metriken (Anzahl, Bytes) | `summarize` |
Mit `dryRun=true` läuft der Ablauf dennoch bis Schritt 6. Das heißt, es wird kopiert, und der Speicher der Archivklasse wird berechnet (S3 Glacier Deep Archive hat eine Mindestspeicherdauer). Verwenden Sie zum Ausprobieren ein kleines `maxFiles`. Es wird nichts gelöscht.
Die Ledger-Status gehen in der Reihenfolge `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `DELETED`, `RESTORED` voran, mit den Seitenausgängen `CHANGED`, `MISMATCH` und `FAILED`. Nur `VERIFIED`-Dateien (einschließlich der Prüfung der zweiten Kopie, wenn diese verlangt ist) können gelöscht werden.
### Wiederherstellung
Die Eingabe ist `runId` und genau eines von `keys` oder `prefix`. `tier` (Standard `Bulk`) und `days` (Standard 7) können angegeben werden.
1. Im Ledger die Dateien mit `DELETED` auswählen
2. Hat der Access Point bereits denselben Schlüssel, als `EXISTS` festhalten und nicht überschreiben
3. Für Objekte in S3 Glacier Flexible Retrieval und S3 Glacier Deep Archive `RestoreObject` anfordern (für S3 Glacier Instant Retrieval nicht nötig)
4. Der Abschluss wird per Polling abgefragt: alle `RestorePollMinutes` wird der Header `Restore` von `HeadObject` gelesen, und das Warten endet bei `RestoreMaxWaitHours`. Das EventBridge-Ereignis `Object Restore Completed` wird nicht verwendet. EventBridge-Benachrichtigungen sind am Bucket aktiviert, sodass später umgestellt werden kann
5. `CopyObject` vom Bucket in den Access Point (über 5 GiB per Fargate)
6. Das Ledger auf `RESTORED` setzen und das Skript zum erneuten Setzen der Attribute `manifests/<runId>-reapply.sh` schreiben

Eine wiederhergestellte Datei hatte den Eigentümer 0:1, den Modus 644 und als Änderungszeit den Zeitpunkt der Wiederherstellung (eine Prüfung in der obigen Umgebung). Die ursprünglichen Werte werden durch `CopyObject` nicht wiederhergestellt.
## Freigabe
Die Freigabe-Benachrichtigung enthält das Token nicht. Das Token liegt in einem SecureString von AWS Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). Die freigebende Person braucht die Berechtigung, diesen Parameter zu lesen, und `states:SendTaskSuccess`.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output '{"approved": true, "approver": "<your IAM principal ARN>"}'
# Ablehnen:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
`approver` ist eine Selbstauskunft. Der eingegebene Wert landet in `deletedBy` des Ledgers, aber den Nachweis, wer tatsächlich freigegeben hat, liefert das CloudTrail-Ereignis `SendTaskSuccess`. Ist `approver` leer oder `approved` nicht `true`, wird nichts gelöscht.
## Attribute erneut setzen
Am Ende einer Wiederherstellung wird `manifests/<runId>-reapply.sh` geschrieben. Führen Sie es als root auf einem Host aus, der das Volume über NFS einhängt.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
Das Skript enthält nur `chown`, `chmod` und `touch -d`. Werte aus dem Ledger werden gegen strenge Formate geprüft, und jeder Schlüssel wird durch Quoting zu genau einem Shell-Wort. Ein Wert, der nicht passt, wird zu einem Kommentar und nicht ausgeführt. Ob die ONTAP-REST-API Eigentümer, Gruppe, Modus und Änderungszeit setzen kann, wurde nicht geprüft; dieser Weg ist daher nicht implementiert.
## Bereitstellung
### Voraussetzungen
- Alias und ARN des Access Points (IAM braucht beide Formen; eine Richtlinie nur mit dem Alias lässt sich bereitstellen und wird zur Laufzeit trotzdem verweigert)
- Ein Name für den Archiv-Bucket (der Stack legt ihn mit `DeletionPolicy: Retain`, Block Public Access, standardmäßig SSE-S3, optional KMS, aktivierten EventBridge-Benachrichtigungen und erzwungenem TLS an)
- Nur für `selection=ATIME` und die Attributerfassung: ein VPC, Subnetze, das Secret mit den ONTAP-Zugangsdaten, der Verwaltungsendpunkt und die UUID des Volumes. Benötigt wird ein Weg von der Lambda-Funktion im VPC zu Secrets Manager und S3 (VPC-Endpunkte oder NAT)
- Nur für Dateien über 5 GiB: ein Image in ECR. Der Access Point hat Internet-Ursprung, daher brauchen die Fargate-Subnetze NAT oder eine öffentliche IP
### Schritte
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # <PLACEHOLDER> ersetzen
sam build && sam deploy
```
Für Fargate bauen Sie das Image vom Repository-Stammverzeichnis aus, pushen es in Ihr eigenes ECR-Repository und tragen es in `FargateImageUri` ein.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Starten Sie zuerst mit einer Eingabe ohne `dryRun` (also `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20}'
```
Zum Löschen übergeben Sie `"dryRun": false` als JSON-Boolean. Der String `"false"` ist ein Eingabefehler, und es wird nichts gelöscht.
## Verzeichnisstruktur
```
archive-verify-delete/
├── template.yaml                # SAM: Bucket, Ledger, 8 Lambda-Funktionen, 2 Zustandsautomaten, Fargate (optional)
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
Die Fachlogik (Prüfsummen, Eingabeprüfung, Ledger) liegt in [`shared/archive_verify/`](../../../shared/archive_verify/) und wird in `shared/tests/` getestet. Lese- und Schreibzugriffe auf den Access Point laufen über `shared/s3ap_helper.py`.
## Lokale Tests
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Um zu bestätigen, dass eine defekte Löschprüfung erkannt wird, wurden `test_does_not_delete_when_etag_changed` und `test_does_not_delete_when_size_differs_but_etag_equal` einmal gegen einen Stub ohne ETag-Vergleich ausgeführt; beide schlugen mit `assert 'DELETED' == 'CHANGED'` fehl. Mit wiederhergestellter Prüfung bestehen 29 Tests.
## Success Metrics
### Outcome
Selten gelesene Dateien nach Prüfung und menschlicher Freigabe in S3-Glacier-Speicherklassen verschieben, die Belegung des Volumes senken und verschobene Dateien über das Ledger finden und wiederherstellen können.
### Metrics
Zielwerte legt der Betreiber fest. Hier stehen keine Zahlen.
| Kategorie | Kennzahl | Definition |
|---|---|---|
| Business Outcome | Freigegebene Kapazität | `bytesDeleted` (`-result.json`). Die Belegung des Volumes sinkt nicht, solange Snapshots bestehen |
| Technical KPI | Übereinstimmungsquote der Prüfung | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Nicht gelöschte Dateien | Summe aus `CHANGED`, `MISMATCH` und `FAILED` |
| Quality KPI | Ohne Freigabe gelöschte Dateien | Muss 0 sein. `DELETED`-Einträge zählen, deren `deletedBy` leer ist |
| Cost KPI | Pro Lauf: Lambda, Fargate, DynamoDB, S3-Anfragen, Speicher der Archivklasse | Nicht gemessen. Zuerst mit `dryRun=true` und kleinem `maxFiles` abschätzen |
| Go / No-Go | In einem durchgängigen Lauf in einer realen Umgebung wird jede kopierte Datei `VERIFIED`, ein absichtlich erzeugtes `CHANGED` wird nicht gelöscht, und der SHA-256 einer wiederhergestellten Datei stimmt überein | `dryRun=false` nicht auf einem Produktions-Volume verwenden, bis dies erfüllt ist |
### Measurement Method
Ausführungsverlauf von Step Functions, `manifests/<runId>-result.json`, EMF-Metriken in CloudWatch (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `BytesVerified`, `BytesDeleted`) und das Ledger.
## Performance Considerations
Nicht gemessen. Die folgenden Punkte sind Entwurfsfaktoren.
- Die Quelldatei wird zweimal gelesen. Das erste Mal über den Access Point zur Hash-Berechnung, das zweite Mal serverseitig durch `CopyObject`. Leseanfragen werden berechnet, und bei Daten im Kapazitätspool fällt zusätzlich die Leseberechnung des Kapazitätspools an
- Die Parallelität ist `MapConcurrency` (Standard 10). Beginnen Sie klein und passen Sie sie an die Last auf Access Point und ONTAP an
- Das Limit von Lambda beträgt 15 Minuten. Die Lesegeschwindigkeit vom Access Point wurde nicht gemessen, daher ist unbekannt, ob der Standardwert von 5 GiB für `LargeFileThresholdBytes` ausreicht. Wenn nicht, senken Sie ihn; Fargate übernimmt dann mehr Dateien
- Beim Auflisten werden alle Ergebnisse von `ListObjectsV2` in den Speicher einer einzelnen Lambda-Funktion geladen. Ab einigen Millionen Objekten teilen Sie die Arbeit mit `prefix` auf
- `selection=ATIME` durchläuft Verzeichnisse per Tiefensuche. Das Scan-Limit beträgt 200.000 Einträge (`ONTAP_SCAN_LIMIT`); darüber hinaus wird das Teilergebnis zurückgegeben
- Die Wartezeit einer Wiederherstellung hängt von Klasse und `tier` ab. AWS nennt für S3 Glacier Deep Archive innerhalb von 12 Stunden bei Standard und innerhalb von 48 Stunden bei Bulk. Der Standardwert von `RestoreMaxWaitHours` ist 72
## Governance Note
> Dieses Muster bietet Orientierung zur technischen Architektur. Es stellt keine Rechts-, Compliance- oder Regulierungsberatung dar. Ziehen Sie qualifizierte Fachleute Ihrer Organisation hinzu.
- Das Prüfergebnis und die Freigabe sind unterstützende Signale für die endgültige Entscheidung einer Person. Es wird keine KI verwendet
- Wenn Aufbewahrungsfristen oder Unveränderbarkeit erforderlich sind, erfüllt dieses Muster sie nicht. Es verwendet weder Object Lock noch Vergleichbares, daher kann jeder mit Berechtigung löschen
- Klassifizierung der Ausgaben: Ledger und Manifeste enthalten Dateipfade, Größen, Hashes und Attribute (`dataClassification: operational-metadata`). Die Dateiinhalte gelangen in den Archiv-Bucket; behandeln Sie sie mit derselben Klassifizierung wie die Originaldaten
- Human Review: Die Freigabe ist bei jedem Lauf erforderlich. Eine automatische Freigabe anhand eines Konfidenzwerts gibt es nicht
- IAM: Nur die Rolle der Funktion `delete` besitzt `s3:DeleteObject`. Der Fargate-Task kopiert nur und hat keine Löschberechtigung. Niemand hat die Berechtigung, Ledger-Einträge zu löschen
- Audit: Freigabe und Löschung werden im Ledger (`deletedBy`, `deletedAt`), im Ausführungsverlauf von Step Functions und in CloudTrail festgehalten
## Einschränkungen und ungeprüfte Punkte
- Eine direkte Kopie von einem Access Point in einen Bucket einer anderen Region lieferte `AccessDenied` (ein Access Point, einmal). Die zweite Kopie zielt nur auf Buckets derselben Region
- Geprüft auf einem Volume im UNIX-Stil. Ob ein Überschreiben mit zurückgesetzter Änderungszeit oder `chown` am ETag erkannt wird, wurde nicht geprüft
- Attribute werden über die Verzeichnisauflistung gelesen. Das Lesen des gesamten übergeordneten Verzeichnisses für eine einzelne Datei ist bei großen Verzeichnissen langsam
- Die Versionierung des Archiv-Buckets ist kein Object Lock. Versionen bleiben erhalten, aber jeder mit Berechtigung kann auch Versionen löschen
## Zugehörige Dokumente
- [Architecture (EN)](docs/architecture.en.md)
- [Hinweise zur Kompatibilität von S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Vergleich von 8 Mechanismen zum Verschieben von Dateien in Archivklassen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (auf Japanisch)
