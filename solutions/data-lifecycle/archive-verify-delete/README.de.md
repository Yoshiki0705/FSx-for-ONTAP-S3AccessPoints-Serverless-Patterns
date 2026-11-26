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
| In diesem Repository geprüft | Unit-Tests mit moto sowie Tests der Struktur von State Machine und IAM. Keine Verbindung zu AWS. Drei im obigen End-to-End-Lauf gefundene Fehler (Aufrufberechtigung für die ONTAP-REST-Funktion, TLS-Prüfung, Fehlername bei einer doppelten Wiederherstellungsanforderung) wurden mit Tests behoben, die sie reproduzieren |
| In einem End-to-End-Lauf auf einem realen System je einmal geprüft (2026-11-26, gleiche Umgebung wie oben, `selection=ATIME`, `GLACIER`, 7 Dateien) | Auswahl nach `accessed_time` und Erfassung von uid, gid, mode, mtime und atime über die ONTAP-REST-API (die Wurzel ist die Volume-Wurzel, der Pfad hat keinen führenden Schrägstrich; `unix_permissions` kommt als ganze Zahl `640` zurück). `ItemReader` und `ResultWriter` der Distributed Map. Eine 5,5-GiB-Multipart-Kopie über Fargate (mit `CopySourceIfMatch`; CRC64NVME gleich dem Ledger). Hash-Berechnung einer 5,3-GB-Datei (rund 4,94 GiB) in Lambda (69,8 s, 2048 MB konfiguriert, 152 MB genutzt). Die zweite Kopie. Löschen nach Freigabe. Eine Datei, die während des Wartens auf die Freigabe über NFS überschrieben wurde, wurde `CHANGED` und nicht gelöscht. Eine abgelehnte Freigabe löschte nichts. Wiederherstellung mit `Expedited` (einschließlich der 5,5-GiB-Datei) und gleiches SHA-256 bei den 6 wiederhergestellten Dateien (die siebte der 7 Dateien war überschrieben worden und wurde weder gelöscht noch wiederhergestellt). Wiederherstellung von uid, gid, mode und mtime mit `reapply.sh` |
### Umgebung und Ergebnis je Schritt
Die Umgebung ist ap-northeast-1, FSx for ONTAP der ersten Generation `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, ein Volume mit UNIX-Sicherheitsstil und ein Access Point, dessen Dateisystembenutzer UNIX root ist. Das Datum ist der 2026-11-26 (Zeiten in japanischer Normalzeit), und jeder Schritt wurde einmal ausgeführt. Die Konfiguration war `selection=ATIME`, `GLACIER`, eine zweite Kopie sowie Fargate auf arm64 mit 2 vCPU und 8 GiB. Die Daten waren 6 kleine Dateien (je drei mit 64 B und 8 MiB, Eigentümer 1234:5678, Modus 640, mtime und atime am 2020-01-02) und eine Datei mit 5.905.580.032 B.
| Schritt | Ergebnis | Dauer |
|---|---|---|
| 1. Bereitstellen | Erfolgreich. Zwei beim Ausführen gefundene Fehler wurden behoben und neu bereitgestellt | Rund 30 Minuten von der Vorbereitung bis zur Bereitstellung (16:19 bis 16:50) |
| 2. Probelauf (`dryRun=true`) | Nach den Korrekturen erfolgreich. Alle 7 Dateien `VERIFIED` (SHA-256 gleich bei 6, CRC64NVME gleich bei 1), auch die zweite Kopie `VERIFIED`. 0 Byte gelöscht, alle 7 Dateien blieben über NFS erhalten | 244 s (einschließlich rund 70 s Warten auf die Freigabe) |
| 3. Überschreiben während des Wartens auf die Freigabe | Eine Datei wurde über NFS mit 4 KiB gleicher Größe überschrieben (mtime aktualisiert). Nach der Freigabe wurde sie `CHANGED` (ETag oder Größe weicht ab) und nicht gelöscht | |
| 4. Echter Lauf (`dryRun=false`) und Freigabe | 6 Dateien `DELETED`, 1 Datei `CHANGED`. `bytesDeleted` war 5.922.357.440. Über NFS waren die 6 Dateien weg, nur die überschriebene blieb | 310 s (172 s bis zur Freigabeanforderung, rund 6 s von der Freigabe bis zum Ende) |
| 5. Wiederherstellung (`tier=Expedited`, `days=1`) | 6 Dateien `RESTORED` (einschließlich der 5,5-GiB-Datei). SHA-256 bei allen 6 gleich dem vor Schritt 1 über NFS erfassten Wert. Die `CHANGED`-Datei war kein Ziel | 287 s (die 5 kleinen Dateien in rund 2,5 Minuten; die Fargate-Kopie der 5,5 GiB dauerte 2 Min. 38 s) |
| 6. Freigabe abgelehnt (`send-task-failure`) | Die Ausführung endete als `REJECTED_OR_TIMED_OUT`, 3 Dateien blieben `VERIFIED`, `deletedBy` war leer, und alle 3 Dateien blieben über NFS erhalten | 16 s |
| Zusätzlich: Hash von 5,3 GB (rund 4,94 GiB) in Lambda | `VERIFIED` (SHA-256 gleich dem NFS-Wert), auch die zweite Kopie `VERIFIED` | Funktion `record` 69,8 s (2048 MB konfiguriert, 152 MB genutzt) |
| Zusätzlich: doppelte Wiederherstellungsanforderung | Die zweite Anforderung lieferte HTTP 409 `RestoreAlreadyInProgress`. Die SDK-Integration von Step Functions gibt sie als `S3.S3Exception` zurück | |
Danach wurden alle Ressourcen entfernt, und die Entfernung wurde durch erneutes Lesen bestätigt.
### Verbrauch (je ein Lauf, keine Rechnung)
| Lauf | Dateien | Dauer | Zustandsübergänge (übergeordnet + untergeordnete Map-Ausführungen) | Fargate-Tasks |
|---|---|---|---|---|
| Probelauf | 7 | 244 s | 12 + 107 = 119 | 2 (Hash und Kopie 96 s, zweite Kopie 35 s) |
| Echter Lauf | 7 | 310 s | 13 + 114 = 127 | 2 (94 s, 35 s) |
| Wiederherstellung | 6 | 287 s | 4 + 103 = 107 | 1 (156 s) |
| Ablehnung | 3 | 16 s | 10 + 45 = 55 | 0 |
- Summe der Lambda-Laufzeiten (CloudWatch; einschließlich fehlgeschlagener Aufrufe, ohne den 4,94-GiB-Lauf): `select` 13 Aufrufe 5,9 s, `ontap_rest` 11 Aufrufe 13,4 s (2 fehlgeschlagen), `record` 17 Aufrufe 11,7 s, `ledger` 34 Aufrufe 9,1 s, `approval` 6 Aufrufe 4,3 s, `delete` 7 Aufrufe 5,6 s, `summarize` 5 Aufrufe 5,1 s, `restore` 26 Aufrufe 9,2 s
- Fargate: 5 Tasks, insgesamt rund 416 s (2 vCPU, 8 GiB, arm64). DynamoDB (On-Demand): 68,5 RCU gelesen und 74 WCU geschrieben, summiert über alle Läufe
- Die Anzahl der S3-Anfragen wurde nicht gemessen (die Anfragemetriken waren nicht aktiviert)
### Drei im End-to-End-Lauf gefundene und behobene Fehler
Jeder wurde mit einem Test behoben, der ihn reproduziert.
| # | Symptom | Ursache und Behebung |
|---|---|---|
| 1 | Ein Lauf mit `selection=ATIME` schlug im Auswahlschritt fehl | Der Rolle der Archiv-State-Machine fehlte `lambda:InvokeFunction` für die ONTAP-REST-Funktion. Die Berechtigung wurde ergänzt |
| 2 | Die ONTAP-REST-Funktion scheiterte mit `CERTIFICATE_VERIFY_FAILED` | Sie prüfte TLS immer, doch das Zertifikat des Verwaltungsendpunkts von FSx for ONTAP ist nicht von einer öffentlichen CA signiert. Der Parameter `OntapVerifySsl` (Standard `false`) wurde ergänzt |
| 3 | Eine doppelte Wiederherstellungsanforderung wurde zu einem Dateifehler | Die SDK-Integration von Step Functions gibt `RestoreAlreadyInProgress` als `S3.S3Exception` zurück, sodass das `Catch` für `S3.RestoreAlreadyInProgressException` nicht griff. Eine laufende Wiederherstellung wird jetzt in die Warteschleife geleitet |
### Im End-to-End-Lauf beobachtetes Verhalten
Dies wurde nicht als Fehler behandelt.
- Mit `selection=ATIME` aktualisieren die eigenen Lesezugriffe des Musters `accessed_time`. Nach einem Lauf mit `dryRun=true` setzen die Lesezugriffe der Hash-Berechnung die atime der Dateien auf die Laufzeit, sodass dieselbe Eingabe mit `dryRun=false` nichts auswählt (sie endete mit 0 Dateien; beobachtet, als ein echter Lauf auf einen Probelauf folgte). Ein Probelauf lässt die Dateien also kürzlich gelesen aussehen. Soll der echte Lauf direkt nach einem Probelauf auf denselben Kandidaten laufen, verwende `selection=MTIME` (`LastModified` ändert sich beim Lesen nicht)
- Der ETag des Access Points folgt mtime und Größe, nicht dem Inhalt. Drei Dateien mit verschiedenem Inhalt, aber gleicher Größe und gleicher mtime lieferten denselben ETag. Die Prüfung von ETag und Größe vor dem Löschen erkennt daher keine Inhaltsänderung, die Größe und mtime beibehält. Ein Überschreiben, das die Größe beibehielt, aber die mtime aktualisierte, wurde erkannt (Schritt 3)
- Wird die letzte Datei eines Verzeichnisses über den Access Point gelöscht, verschwindet auch das nun leere übergeordnete Verzeichnis (beobachtet bei `arc-e2e/large/`). Das `CopyObject` der Wiederherstellung legt das übergeordnete Verzeichnis neu an
- Eine wiederhergestellte Datei hatte den Eigentümer 0:1, den Modus 644 und als Änderungszeit den Zeitpunkt der Wiederherstellung. Das als root auf einem Host, der das Volume per NFS einhängt, ausgeführte erzeugte `reapply.sh` stellte uid, gid, mode und mtime wieder her (1234:5678, 640, 2020-01-02 03:04:05), und das SHA-256 des Inhalts änderte sich nicht
- Der Lauf verwendete eine Access-Point-Richtlinie, die jede Rolle erlaubt (die Rollen der Funktionen `select`, `record`, `delete` und `restore`, die Fargate-Task-Rolle und die Rollen der beiden State Machines)
- Eine `Expedited`-Wiederherstellungsanforderung für 5,5 GiB wurde angenommen und war nach rund 4 Minuten oder weniger abgeschlossen
### Nicht geprüft
- Dauer und Kosten bei vielen Dateien
- Abschluss von `Standard`- und `Bulk`-Wiederherstellungen (nur `Expedited` wurde ausgeführt)
- Wiederholung bei `S3.SlowDownException` (der von der SDK-Integration zurückgegebene Name wurde nicht beobachtet, und eine Abweichung derselben Art wie bei Fehler 3 ist möglich)
- Einträge der Löschungen in den CloudTrail-Datenereignissen (ob der Trail des Kontos Datenereignisse für diesen Access Point erfasst, wurde nicht geprüft)
- NTFS-Volumes, Nicht-root-Benutzer, zweite Generation, Multi-AZ
- Verhalten, wenn der Access Point keine Richtlinie hat
- Der Pfad `EXISTS` bei der Wiederherstellung (eine gleichnamige Datei liegt bereits auf NFS); als Übersprung wurde nur beobachtet, dass die `CHANGED`-Datei nicht ausgewählt wurde
- Ein Lauf mit 0 Kandidaten ist ungeklärt. Ein Lauf rund 10 Sekunden nach dem Zurücksetzen der atime mit `touch -d` fand 0 Kandidaten. Eine Prüfung rund 17 Minuten später lieferte den Wert von 2020, und eine weitere Prüfung direkt nach `touch` lieferte 6 Dateien. Die Ursache wurde nicht ermittelt, und der Fall wurde nicht reproduziert
### Verbleibendes Schreibfenster vor dem Löschen
Bei der Prüfung vor dem Löschen bleibt ein Schreibfenster. Das `DeleteObject` des Access Points unterstützt kein bedingtes Löschen, daher wird ein Schreibzugriff zwischen der Prüfung mit `HeadObject` und dem Löschen nicht erkannt. Das Fenster entspricht einem API-Hin-und-Rück-Aufruf.
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
- Nur für `selection=ATIME` und die Erfassung von Attributen: ein VPC, Subnetze, das Secret mit den ONTAP-Zugangsdaten, der Verwaltungsendpunkt, die Volume-UUID und `OntapVerifySsl`. Das Zertifikat des Verwaltungsendpunkts von FSx for ONTAP ist nicht von einer öffentlichen CA signiert, daher ist der Standard `false` (keine Prüfung), und die ONTAP-Zugangsdaten werden dann über eine Verbindung gesendet, deren Gegenstelle nicht authentifiziert wird (der Pfad liegt im VPC). Mit `true` stoppte die Auswahl an einem Zertifikatsfehler (beobachtet). Nötig ist eine Route von der Lambda-Funktion im VPC zu Secrets Manager und S3 (VPC-Endpunkte oder NAT)
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
- Auf einem Volume im UNIX-Stil geprüft. Eine Inhaltsänderung, die Größe und mtime beibehält, wird von der Prüfung von ETag und Größe nicht erkannt (siehe „Im End-to-End-Lauf beobachtetes Verhalten“ oben). Ob `chown` den ETag ändert, wurde nicht geprüft
- Attribute werden über die Verzeichnisauflistung gelesen. Das Lesen des gesamten übergeordneten Verzeichnisses für eine einzelne Datei ist bei großen Verzeichnissen langsam
- Die Versionierung des Archiv-Buckets ist kein Object Lock. Versionen bleiben erhalten, aber jeder mit Berechtigung kann auch Versionen löschen
## Zugehörige Dokumente
- [Architecture (EN)](docs/architecture.en.md)
- [Hinweise zur Kompatibilität von S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Vergleich von 8 Mechanismen zum Verschieben von Dateien in Archivklassen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (auf Japanisch)

---

<!-- playbook-reading:start -->
## Vor dem Produktivbetrieb lesen

Wie sich die nach der Bereitstellung auftretenden Einschränkungen in Entwurfsentscheidungen übersetzen, steht im [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) beschrieben. Liegt derselbe Inhalt an zwei Stellen, überlebt die nicht mehr gepflegte Kopie die korrigierte.

- [Datennutzung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — Einschränkungen des Zugriffs über einen Access Point (alle Patterns)
- [Datensicherung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — wo sich die Entscheidungen für dieses Pattern häufen
- [Aufbauen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — vor dem Produktivbetrieb durchgehen (alle Patterns)
<!-- playbook-reading:end -->
