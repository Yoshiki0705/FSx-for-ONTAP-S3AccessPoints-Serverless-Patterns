# archive-verify-delete: Archivierung allein mit S3-API-Aufrufen, kopieren, prüfen, nach Freigabe löschen
🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)
📚 **Dokumentation**: [Architecture (EN)](docs/architecture.en.md) | [アーキテクチャ (JA)](docs/architecture.md)
## Überblick
Dieses Muster verschiebt selten gelesene Dateien eines Amazon-FSx-for-NetApp-ONTAP-Volumes (FSx for ONTAP) in S3-Glacier-Speicherklassen. Lesen, Schreiben und Löschen von Dateien erfolgen über die S3-API von S3 Access Points; dafür wird kein NFS-Mount verwendet. Zwei Dinge brauchen mehr: Die Auswahl nach dem Zeitpunkt des letzten Zugriffs (`selection=ATIME`) und die Erfassung von Attributen nutzen die ONTAP-REST-API (eine Lambda-Funktion im VPC, ONTAP-Zugangsdaten, der Verwaltungsendpunkt), und das Zurücksetzen von Eigentümer, Modus und Änderungszeit nach einer Wiederherstellung erfordert einen Host, der das Volume per NFS einhängt.
Eine Datei durchläuft die folgenden Schritte. Eine Datei, deren Bedingungen in einem Schritt nicht mehr erfüllt sind, wird vom Löschen ausgenommen.
1. Größe, ETag, SHA-256 und CRC64NVME im Ledger (einer DynamoDB-Tabelle) erfassen
2. Mit `CopyObject` unter Angabe der Speicherklasse in einen Archiv-Bucket kopieren (Schlüssel `<prefix><runId>/<original key>`)
3. Die vom Bucket zurückgegebene Prüfsumme mit dem Wert im Ledger vergleichen
4. Eine Person gibt die Liste der übereinstimmenden Dateien frei. Die Freigabe wird im Ledger als `APPROVED` festgehalten und abgelehnt, wenn der Freigebende derselbe Principal ist, der den Lauf gestartet hat (Standard; verglichen werden angegebene Werte, das ist kein Identitätsnachweis)
5. Nur Dateien, die das Ledger als `APPROVED` ausweist, werden gelöscht, nachdem geprüft wurde, dass ETag und Größe am Access Point noch denen im Ledger entsprechen

Zum Wiederherstellen sucht das Muster die Dateien im Ledger, fordert im Bucket die Wiederherstellung an, wartet auf deren Abschluss, kopiert die Dateien mit `CopyObject` zurück in den Access Point und liest dann jede wiederhergestellte Datei zurück und vergleicht sie mit SHA-256 und CRC64NVME des Ledgers.
Dieses Muster verwendet weder S3 Object Lock noch S3 Glacier Vault Lock, AWS Backup Vault Lock, SnapLock oder Snapshot-Sperren, und keines davon kommt in der Vorlage vor. Es wird keine Aufbewahrungsfrist gesetzt, daher können Objekte im Archiv-Bucket von jedem mit Berechtigung gelöscht werden.
Die Annahmen dieses Musters und der Vergleich mit anderen Ansätzen stehen in [Vergleich von 9 Mechanismen zum Verschieben von Dateien in Archivklassen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/reference/comparison/archive-tiering-library-options.md).
## Was gemessen wurde und was nicht
| Kategorie | Inhalt |
|---|---|
| Komponenten, die einzeln je einmal in einer realen Umgebung geprüft wurden (im obigen Vergleich festgehalten; 2026-11-24 und 2026-11-26, ap-northeast-1, erste Generation `SINGLE_AZ_1`, ONTAP 9.19.1P4D1, Volume im UNIX-Stil, Benutzer des Access Points ist UNIX root) | Mit `ChecksumAlgorithm=SHA256` bei `CopyObject` war `ChecksumSHA256` des Buckets `FULL_OBJECT` und gleich dem SHA-256 der Datei (bis 8 MiB). Bei einer 5,5-GiB-Multipart-Kopie wurde SHA-256 zu `COMPOSITE`, und CRC64NVME war `FULL_OBJECT` und gleich. `--copy-source-if-match` mit einem alten ETag lieferte `PreconditionFailed`. `DeleteObject` des Access Points unterstützt `If-Match` nicht. Eine SDK-Integration von Step Functions akzeptierte den Alias des Access Points als `Bucket` |
| In diesem Repository geprüft | Unit-Tests mit moto sowie Tests der Struktur von State Machine und IAM. Keine Verbindung zu AWS. Sieben in den obigen End-to-End-Läufen gefundene Fehler (Aufrufberechtigung für die ONTAP-REST-Funktion, TLS-Prüfung, Fehlername bei einer doppelten Wiederherstellungsanforderung, Logging-Berechtigung der State Machines, 403 von `HeadObject`, Veröffentlichungsberechtigung für Alarme) wurden mit Tests behoben, die sie reproduzieren |
| Im Lauf mit sieben Dateien einschließlich 5,5 GiB je einmal geprüft (2026-11-26, gleiche Umgebung wie oben, `selection=ATIME`, `GLACIER`, 7 Dateien) | Auswahl nach `accessed_time` und Erfassung von uid, gid, mode, mtime und atime über die ONTAP-REST-API (die Wurzel ist die Volume-Wurzel, der Pfad hat keinen führenden Schrägstrich; `unix_permissions` kommt als ganze Zahl `640` zurück). `ItemReader` und `ResultWriter` der Distributed Map. Eine 5,5-GiB-Multipart-Kopie über Fargate (mit `CopySourceIfMatch`; CRC64NVME gleich dem Ledger). Hash-Berechnung einer 5,3-GB-Datei (rund 4,94 GiB) in Lambda (69,8 s, 2048 MB konfiguriert, 152 MB genutzt). Die zweite Kopie. Löschen nach Freigabe. Eine Datei, die während des Wartens auf die Freigabe über NFS überschrieben wurde, wurde `CHANGED` und nicht gelöscht. Eine abgelehnte Freigabe löschte nichts. Wiederherstellung mit `Expedited` (einschließlich der 5,5-GiB-Datei) und gleiches SHA-256 bei den 6 wiederhergestellten Dateien (die siebte der 7 Dateien war überschrieben worden und wurde weder gelöscht noch wiederhergestellt). Wiederherstellung von uid, gid, mode und mtime mit `reapply.sh` |
| Im Lauf zu Ausschlüssen und Freigabe je einmal geprüft (2026-11-26, gleiche Umgebung, `GLACIER`, zweite Kopie aktiv. Probelauf mit `selection=ATIME`, echter Lauf mit `selection=MTIME` und Attributen aus ONTAP REST. Dateien von 64 B bis 1 MiB und eine 51 GiB große Sparse-Datei) | Punkte, die der Lauf mit sieben Dateien einschließlich 5,5 GiB nicht abdeckte. Mit `maxFiles=50` lagen drei 64-B-Dateien und eine Datei mit 131.071 B unter der Mindestgröße, und eine Datei mit 131.073 B blieb in der Auswahl. `*.vmdk` und ein Legal-Hold-Präfix wurden ausgeschlossen. Die 51 GiB große Sparse-Datei wurde als `SKIPPED_TOO_LARGE` erfasst und nicht kopiert. Eine wiederverwendete `runId` und eine Eingabe für einen echten Lauf ohne `requestedBy` endeten als Eingabefehler. Eine Freigabe mit demselben ARN wie der Starter endete als `APPROVAL_REFUSED`, und nichts wurde gelöscht. Der direkte Aufruf der Funktion `delete` ohne Freigabe lieferte `NOT_APPROVED` und löschte nichts. Mit einem anderen Freigebenden wurden 3 Dateien gelöscht, und die 1 Datei, die während des Wartens neu geschrieben wurde, blieb als `CHANGED`. Bei Einträgen, die zur Simulation einer Unterbrechung auf `DELETING` gesetzt waren, erfasste eine Wiederholung durch dieselbe Ausführung `DELETED` (`already gone on retry`), eine andere Ausführung wurde abgelehnt, und `reconcile` erfasste `DELETED` (diese Prüfung lief auf dem Code vor der Prüfung des Ausführungsstatus; auf dem aktuellen Code ist der Pfad für Wiederholung und Fortsetzung nur durch Unit-Tests abgedeckt und nicht auf realer Hardware gelaufen). Nach der Wiederherstellung waren 3 Dateien `RESTORE_VERIFIED`. Alarme wurden (nach einer Korrektur) in das mit KMS verschlüsselte Topic veröffentlicht |
| In der Prüfung des direkten Aufrufs je einmal geprüft (2026-11-26, gleiches Konto und gleicher Access Point, `selection=MTIME`, `GLACIER`, ohne Fargate, acht Dateien mit 256 KiB, `MapConcurrency=1`) | Das Stoppen der Ausführung direkt nach der Freigabe ließ 7 `APPROVED`-Einträge zurück. Der direkte Aufruf der Funktion `delete` mit dem `claim` einer anderen Ausführung lieferte `NOT_APPROVED` (`approval not current`). Vor der Korrektur machte ein Aufruf, dessen `claim` die ARN der gestoppten Ausführung selbst war, 1 Datei zu `DELETED`. Nach dem Hinzufügen der Prüfung des Ausführungszustands lieferte derselbe Aufruf `NOT_APPROVED` (`claiming execution is not running`). `reconcile` setzte die 7 Einträge auf `VERIFIED` zurück. Ein normales Löschen in einer laufenden Ausführung endete mit 7 Dateien `DELETED`. Der Parameter mit dem Task-Token war nach einer Freigabe und nach einer Ablehnung weg. Das Token war mit dem KMS-Schlüssel des Stacks verschlüsselt |
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
Zustandsübergänge im Lauf zu Ausschlüssen und Freigabe (2026-11-26, kleine Dateien, zweite Kopie aktiv, `MapConcurrency=2`), je ein Lauf; sie hängen von Dateigröße und Pfad ab.

| Ausführung | Dateien | Dauer | Zustandsübergänge (übergeordnet + untergeordnete Map-Ausführungen) | Je Datei |
|---|---|---|---|---|
| Probelauf `e2e2-dry1` | 4 | 66 s (einschließlich rund 20 s Warten auf die Freigabe) | 12 + 60 = 72 | 18 |
| echter Lauf `e2e2-real2` (3 gelöscht, 1 `CHANGED`) | 4 | 45 s (einschließlich des Wartens auf die Freigabe) | 14 + 64 = 78 | 19,5 |
| Wiederherstellung `e2e2-rest2` (Expedited, mit Prüfung, 1 `EXISTS`) | 4 | 192 s | 4 + 52 = 56 | 14 |
### Im End-to-End-Lauf gefundene und behobene Fehler
Jeder wurde mit einem Test behoben, der ihn reproduziert.
| # | Symptom | Ursache und Behebung |
|---|---|---|
| 1 | Ein Lauf mit `selection=ATIME` schlug im Auswahlschritt fehl | Der Rolle der Archiv-State-Machine fehlte `lambda:InvokeFunction` für die ONTAP-REST-Funktion. Die Berechtigung wurde ergänzt |
| 2 | Die ONTAP-REST-Funktion scheiterte mit `CERTIFICATE_VERIFY_FAILED` | Sie prüfte TLS immer, doch das Zertifikat des Verwaltungsendpunkts von FSx for ONTAP ist nicht von einer öffentlichen CA signiert. Der Parameter `OntapVerifySsl` (Standard `false`) wurde ergänzt |
| 3 | Eine doppelte Wiederherstellungsanforderung wurde zu einem Dateifehler | Die SDK-Integration von Step Functions gibt `RestoreAlreadyInProgress` als `S3.S3Exception` zurück, sodass das `Catch` für `S3.RestoreAlreadyInProgressException` nicht griff. Eine laufende Wiederherstellung wird jetzt in die Warteschleife geleitet |
Der Lauf zu Ausschlüssen und Freigabe (2026-11-26) fand drei weitere Fehler und behob sie.

| # | Symptom | Ursache und Behebung |
|---|---|---|
| 4 | Die Bereitstellung schlug mit `The state machine IAM Role is not authorized to access the Log Destination` fehl | Den Rollen der State Machines fehlten `logs:CreateLogDelivery` und die zugehörigen Berechtigungen, die das Ausführungs-Logging braucht. Sie wurden ergänzt |
| 5 | Eine Wiederholung des Löschens und `reconcile` erhielten von `HeadObject` bei einer gelöschten Datei 403 | Für einen Aufrufer ohne `s3:ListBucket` liefert `HeadObject` bei einem fehlenden Schlüssel 403 statt 404. `s3:ListBucket` wurde für die Funktionen `delete` und `restore` ergänzt, in IAM und in der Access-Point-Richtlinie |
| 6 | Die Benachrichtigungen der CloudWatch-Alarme schlugen mit `CloudWatch Alarms is not authorized to perform: SNS:Publish` fehl | Die Schlüsselrichtlinie erlaubte CloudWatch, die Topic-Richtlinie aber nur EventBridge. Eine Anweisung für `cloudwatch.amazonaws.com` wurde ergänzt |
| 7 | Ein Deployment ohne Fargate (`FargateImageUri` leer) schlug mit `is not authorized to create managed-rule` fehl (Prüfung des direkten Aufrufs) | Beide Definitionen enthalten `ecs:runTask.sync`-Zustände, und Berechtigungen der Rolle wie `events:PutRule` werden beim Erstellen der State Machine geprüft. Die Berechtigung lag innerhalb der Bedingung `UseFargate`. Die Bedingung wurde entfernt |
### Im End-to-End-Lauf beobachtetes Verhalten
Dies wurde nicht als Fehler behandelt.
- Mit `selection=ATIME` aktualisieren die eigenen Lesezugriffe des Musters `accessed_time`. Nach einem Lauf mit `dryRun=true` setzen die Lesezugriffe der Hash-Berechnung die atime jeder Datei auf die Laufzeit, sodass dieselbe Eingabe mit `dryRun=false` nichts auswählt (sie endete mit 0 Dateien, als der echte Lauf auf den Probelauf folgte). Verwende `selection=MTIME`, um direkt nach einem Probelauf den echten Lauf auf denselben Kandidaten auszuführen (`LastModified` ändert sich beim Lesen nicht)
- Zum ETag lauten die offizielle Formulierung und die Messung hier so. Die offizielle Seite ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), gelesen am 2026-11-26) sagt "The ETag reflects changes only to the contents of an object, not its metadata". In einer Messung in dieser Umgebung lieferten drei Dateien mit gleicher Größe und gleicher mtime, aber verschiedenem Inhalt denselben ETag. Das Muster geht daher davon aus, dass die Prüfung von ETag und Größe vor dem Löschen eine Inhaltsänderung nicht erkennt, die Größe und mtime beibehält. Ein Überschreiben gleicher Größe, das die mtime während des Wartens auf die Freigabe aktualisierte, wurde erkannt (Schritt 3 des ersten Laufs und der zweite echte Lauf) [E-023]
- Wird die letzte Datei eines Verzeichnisses über den Access Point gelöscht, verschwindet auch das nun leere übergeordnete Verzeichnis (beobachtet bei `arc-e2e/large/`). Das `CopyObject` der Wiederherstellung legt es neu an
- Wiederhergestellte Dateien hatten den Eigentümer 0:1, den Modus 644 und als mtime den Zeitpunkt der Wiederherstellung. Das als root auf einem Host, der das Volume per NFS einhängt, ausgeführte erzeugte `reapply.sh` stellte uid, gid, mode und mtime wieder her (1234:5678, 640, 2020-01-02 03:04:05), ohne das SHA-256 des Inhalts zu ändern
- Die State Machine für die Wiederherstellung wählt auch eine als `CHANGED` zurückgebliebene Datei aus, wenn der Archiv-Bucket ihre Kopie enthält. Hat der Access Point den Schlüssel bereits, bleibt er als `EXISTS` und wird nicht überschrieben (einmal bei der Wiederherstellung im Lauf zu Ausschlüssen und Freigabe beobachtet)
- Die `Expedited`-Wiederherstellungsanforderung für die 5,5-GiB-Datei wurde angenommen und war nach rund 4 Minuten abgeschlossen
### Nicht geprüft
- Dauer und Kosten bei vielen Dateien. Durchsatz des Dateisystems und Latenz der Clients bei anderen Nebenläufigkeitseinstellungen
- Wartezeit bei `Standard`- und `Bulk`-Wiederherstellungen (nur `Expedited` wurde ausgeführt)
- Wiederholung bei `S3.SlowDownException` (der von der SDK-Integration zurückgegebene Name wurde nicht beobachtet; eine Abweichung derselben Art wie bei Fehler 3 ist möglich)
- Löschungen und Freigaben in den CloudTrail-Datenereignissen. S3-Datenereignisse (`DeleteObject` und andere) werden nur erfasst, wenn für einen Trail Datenereignisse aktiviert sind. Dieser Lauf prüfte nicht, ob der Trail des Kontos Datenereignisse für diesen Access Point enthält. `SendTaskSuccess` ist ein Verwaltungsereignis; auch dessen Eintrag wurde nicht geprüft
- Die Ablehnung und die Annahme einer Freigabe wurden mit demselben SSO-Principal verglichen, der in der Freigabeausgabe verschiedene ARNs angab. Der Wert des Freigebenden ist eine Angabe des Aufrufers, ein anderer IAM-Principal sollte also dasselbe Ergebnis liefern, doch ein echter zweiter Principal wurde nicht verwendet
- Kopieren und Wiederherstellen von Dateien über 50 GiB (geprüft wurde nur, dass sie mit einer Sparse-Datei aus der Auswahl ausgenommen werden)
- NTFS-Volumes, Nicht-root-Benutzer, zweite Generation, Multi-AZ
- Bei der Wiederherstellung der Pfad `EXISTS` über das Nicht-Auswählen von `CHANGED`-Dateien hinaus (eine gleichnamige Datei auf NFS)
- Abwarten, bis `ApprovalPendingAlarm` tatsächlich auf `ALARM` wechselt (geprüft wurde nur, dass die Metrik veröffentlicht wird)
- Ein Fall mit 0 Kandidaten ist ungeklärt. Ein Lauf rund 10 Sekunden nach dem Zurücksetzen der atime mit `touch -d` lieferte keine Kandidaten. Eine Prüfung rund 17 Minuten später lieferte die Werte von 2020, und weitere Prüfungen lieferten ebenfalls 6 Dateien. Die Ursache wurde nicht ermittelt, und der Fall trat nicht erneut auf
- Ein Lauf des Pfads für Wiederholung und Fortsetzung des Löschens (`DELETING` mit demselben `claimedBy`) auf realer Hardware. Die Wiederholungsprüfung oben lief auf dem Code vor der Prüfung des Ausführungsstatus. Auf dem aktuellen Code ist dieser Pfad nur durch Unit-Tests abgedeckt
### Verbleibendes Schreibfenster vor dem Löschen
Bei der Prüfung vor dem Löschen bleibt ein Schreibfenster. Das `DeleteObject` des Access Points unterstützt kein bedingtes Löschen, daher wird ein Schreibzugriff zwischen der Prüfung mit `HeadObject` und dem Löschen nicht erkannt. Das Fenster entspricht einem API-Hin-und-Rück-Aufruf.
## Ablauf
### Archivierung
`olderThanDays` ist erforderlich. `dryRun` ist standardmäßig `true`. Ein Lauf mit `dryRun=false` braucht den ARN des startenden Principals in `requestedBy`, wenn `RequireSeparateApprover=true` gilt (Standard).
| Schritt | Verarbeitung | Umsetzung |
|---|---|---|
| 1. Auswählen | `MTIME`: `LastModified` aus `ListObjectsV2` des Access Points. `ATIME`: `accessed_time` aus der ONTAP-REST-API (Lambda im VPC). Die Ausschlüsse anwenden (Tabelle unten) | `select`, `ontap_rest` |
| 2. Erfassen | Größe, ETag, SHA-256, CRC64NVME und, falls verfügbar, uid, gid, mode, mtime, atime im Ledger. Lambda bis 5 GiB, darüber Fargate | `record`, Fargate-Task |
| 3. Kopieren | Bis 5 GiB: `copyObject` per SDK-Integration (`SHA256`, der ETag aus dem Ledger als `CopySourceIfMatch`). Darüber: Multipart-Kopie durch Fargate (`CRC64NVME`) | Step Functions, Fargate |
| 4. Prüfen | Größe und Prüfsumme aus `HeadObject` des Buckets (`ChecksumMode=ENABLED`) mit dem Ledger vergleichen. Eine Abweichung bleibt als `MISMATCH` und die Datei wird vom Löschen ausgenommen | `ledger` |
| 5. Zweite Kopie (optional) | Vom Access Point in einen anderen Bucket derselben Region kopieren und ebenso prüfen. Bei Abweichung wird die Datei vom Löschen ausgenommen | Step Functions, `ledger` |
| 6. Freigeben | Die Liste der Übereinstimmungen nach `manifests/<runId>.json` schreiben, per SNS benachrichtigen und mit `waitForTaskToken` warten. Die Benachrichtigung weist darauf hin, wenn es nur eine Kopie gibt und wenn Dateien nicht wiederhergestellt werden können | `approval` |
| 7. Freigabe erfassen | Nur bei `dryRun=false`. Ablehnen, wenn der Freigebende der Starter ist. Andernfalls jede aufgeführte Datei im Ledger von `VERIFIED` auf `APPROVED` setzen und `manifests/<runId>-approval.json` schreiben | `approval` |
| 8. Löschen | Nur Dateien, die das Ledger als `APPROVED` ausweist. ETag und Größe je Datei prüfen; bei Gleichheit `DeleteObject`, sonst als `CHANGED` behalten | `delete` |
| 9. Erfassen | `manifests/<runId>-result.json` und EMF-Metriken (Anzahlen, Bytes, Ausschlüsse). `COMPLETED_WITH_ERRORS`, wenn `DELETING`- oder `APPROVED`-Einträge übrig bleiben | `summarize` |
Auch mit `dryRun=true` läuft die Ausführung bis Schritt 6. Es werden Kopien angelegt, und der Speicher in der Archivklasse wird berechnet (mit einer Mindestspeicherdauer). Halte `maxFiles` beim Ausprobieren klein. Es wird nichts gelöscht.
Die Status im Ledger durchlaufen `SELECTED`, `RECORDED`, `COPIED`, `VERIFIED`, `APPROVED`, `DELETING`, `DELETED`, `RESTORED`, `RESTORE_VERIFIED`, mit den Ausgängen `CHANGED`, `MISMATCH`, `FAILED`, `SKIPPED_TOO_LARGE` und `RESTORE_MISMATCH`. Nur `APPROVED`-Dateien (und, wenn eine zweite Kopie verlangt wird, deren zweite Kopie ebenfalls geprüft ist) können gelöscht werden.

Eine bereits verwendete `runId` ist ein Eingabefehler. Um einen unterbrochenen Lauf fortzusetzen, übergib dieselbe `runId` mit `"resume": true` (siehe "Wiederaufnahme nach einem unterbrochenen Löschvorgang" unten). Der Archivschlüssel enthält die `runId`, sodass sich ein Probelauf und ein echter Lauf oder eine erneute Archivierung nach einer Änderung gegenseitig keine Objekte überschreiben. Ohne Versionierung löscht ein Überschreiben das frühere Objekt, was in Klassen mit Mindestspeicherdauer eine Gebühr für vorzeitiges Löschen bedeuten kann.

Was die Auswahl auslässt:

| Bedingung | Standard | Grund |
|---|---|---|
| Über 50 GiB | Ausgelassen und im Ledger als `SKIPPED_TOO_LARGE` erfasst. `allowOversize: true` nimmt sie auf | Die offizielle Seite ([Access point compatibility](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html), gelesen am 2026-11-26) sagt "Maximum object size is 50 GiB for uploads, but you can download objects larger than that". Eine Wiederherstellung schreibt über den Access Point, daher kann dieses Muster eine größere Datei dort nicht wiederherstellen (sie lässt sich direkt aus dem Bucket herunterladen) [E-021] |
| Unter `MinFileSizeBytes` | 131.072 Bytes (128 KiB). `minSizeBytes` in der Eingabe ändert den Wert | Laut [Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare) (gelesen am 2026-11-26) berechnen Standard-IA und Glacier Instant Retrieval mindestens 128 KB je Objekt, und Glacier Flexible Retrieval und Deep Archive fügen je Objekt 40 KB Metadaten hinzu (32 KB zum Preis dieser Klasse, 8 KB zum Preis von Standard). Bei kleinen Dateien ist das mehr als die Daten selbst |
| `ExcludePatterns` (Globs), `ExcludePrefixes` | `ExcludePatterns`: die Liste unten; `ExcludePrefixes`: leer | Die Werte des Stacks gelten immer; `excludePatterns` und `excludePrefixes` in der Eingabe können nur ergänzen. Trage hier Legal-Hold-Präfixe ein |

Schließe Datendateien von Iceberg-, Delta- oder Hive-Tabellen, Dateien einer laufenden Datenbank und VM-Disk-Images (`*.vmdk`, `*.vhd`, `*.qcow2` und ähnliche) stets aus. Das Muster verschiebt Dateien einzeln und weiß nichts von Tabellenmetadaten oder dem Prozess, der eine Datei geöffnet hält. Räume eine Tabelle mit deren eigenen Funktionen auf (Partitionen lösen, Snapshots ablaufen lassen) und wähle nur die danach verbleibenden Pfade aus. Ob etwas einem Legal Hold unterliegt, entscheidet deine Rechtsabteilung; das Muster trifft diese Entscheidung nicht.
Der Standardwert von `ExcludePatterns` ist ein Ausgangspunkt und keine vollständige Liste; er nennt Dateitypen, an denen häufig echter Schaden entsteht. VM-Disk-Images (`*.vmdk`, `*.vhd`, `*.vhdx`, `*.vdi`, `*.qcow2`) werden fortlaufend beschrieben, solange die VM läuft, eine Kopie Datei für Datei ist daher eine kaputte Kopie. Daten- und Logdateien von Datenbanken (`*.mdf`, `*.ndf`, `*.ldf` bei SQL Server; `*.ibd` bei MySQL InnoDB; `*.dbf` bei Oracle) hält die Datenbank geöffnet und beschreibt sie. Metadatenverzeichnisse von Tabellenformaten (`_delta_log/` bei Delta, `.hoodie/` bei Hudi, `metadata/` bei Iceberg) führen die Datendateien auf; werden nur die Datendateien verschoben, ist die Tabelle kaputt. Der Vergleich unterscheidet Groß- und Kleinschreibung (`*.VMDK` passt nicht). Ein Verzeichnis namens `metadata/`, das keine Iceberg-Tabelle ist, wird ebenfalls ausgeschlossen. Datendateien von Tabellen wie `*.parquet` stehen nicht im Standardwert; ergänze die Muster, die zu deinem Volume passen. Setze den Parameter nur auf leer, wenn das Volume nichts davon enthält.
### Wiederherstellung
Die Eingabe besteht aus `runId` und genau einem von `keys` oder `prefix`. `tier` (Standard `Bulk`) und `days` (Standard 7) sind optional.
1. `DELETED`-Dateien aus dem Ledger auswählen. `DELETING`- und `CHANGED`-Dateien werden ebenfalls ausgewählt, wenn der Archiv-Bucket ihre Kopie enthält (damit sich von einem unterbrochenen Löschvorgang zurückgebliebene Einträge wiederherstellen lassen)
2. Hat der Access Point den Schlüssel bereits, ihn als `EXISTS` belassen und nicht überschreiben
3. `RestoreObject` für Objekte in S3 Glacier Flexible Retrieval und S3 Glacier Deep Archive anfordern (bei S3 Glacier Instant Retrieval nicht nötig)
4. Das Warten erfolgt per Polling (alle `RestorePollMinutes` den Header `Restore` aus `HeadObject` lesen, nach `RestoreMaxWaitHours` aufgeben). EventBridge `Object Restore Completed` wird nicht verwendet; die EventBridge-Benachrichtigungen des Buckets sind aktiv, sodass sich dies später umstellen lässt
5. `CopyObject` vom Bucket zurück in den Access Point (Fargate ab 5 GiB). Das Ledger zeigt `RESTORED`
6. Die wiederhergestellte Datei über den Access Point zurücklesen, hashen und mit SHA-256, CRC64NVME und Größe im Ledger vergleichen (Fargate ab 5 GiB). Eine Übereinstimmung ist `RESTORE_VERIFIED`, eine Abweichung `RESTORE_MISMATCH`
7. Das Skript zum erneuten Setzen der Attribute `manifests/<runId>-reapply.sh` schreiben, nur für `RESTORE_VERIFIED`-Dateien

Wiederhergestellte Dateien hatten den Eigentümer 0:1, den Modus 644 und als mtime den Zeitpunkt der Wiederherstellung (in der oben genannten Umgebung geprüft). `CopyObject` stellt die ursprünglichen Werte nicht wieder her.
Eine `RESTORE_MISMATCH`-Datei wird standardmäßig nicht für die Wiederherstellung ausgewählt: Ihre Kopie auf dem Access Point passte nicht zum Ledger, und eine Auswahl würde sie als `EXISTS` stehen lassen. Zum Wiederholen füge der Eingabe der Wiederherstellung `"retryMismatched": true` (JSON-Boolean) hinzu. Nur dann werden die Einträge ausgewählt, die das Ledger dieser `runId` aktuell als `RESTORE_MISMATCH` führt, und die abweichende Kopie auf dem Access Point wird durch die Kopie im Bucket überschrieben. Einträge in jedem anderen Status überschreiben nie eine vorhandene Datei, mit oder ohne Flag. Nach dem Überschreiben endet dasselbe Zurücklesen in `RESTORE_VERIFIED` oder `RESTORE_MISMATCH`.
### Wiederaufnahme nach einem unterbrochenen Löschvorgang
Eine Lambda-Funktion, die mitten im Löschen stehen bleibt oder ihre Wiederholungen aufgebraucht hat, kann Einträge im Ledger als `DELETING` oder `APPROVED` zurücklassen. Das Ergebnis zeigt dies als `COMPLETED_WITH_ERRORS`, `stuckDeleting` und `notDeleted`, und `FilesStuckDeletingAlarm` schlägt an. Wird die Archiv-State-Machine mit derselben `runId` und `"resume": true` gestartet, führt sie `reconcile` aus, das die Einträge wie unten beschrieben abschließt, und fordert dann für die verbleibenden Dateien eine neue Freigabe an.
| Ledger | Access Point | Ergebnis |
|---|---|---|
| `DELETING` | Keine Datei | `DELETED` (das Löschen war erfolgt; `reconciled: true`) |
| `DELETING`, `APPROVED` | Datei vorhanden, ETag und Größe gleich dem Ledger | Zurück zu `VERIFIED`; das Löschen braucht eine neue Freigabe |
| `DELETING`, `APPROVED` | Datei vorhanden, weicht vom Ledger ab | `CHANGED` |
| Beide | Die Ausführung, die den Eintrag hält, läuft noch | Unberührt |
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"runId": "<runId>", "olderThanDays": 0, "resume": true, "dryRun": false, "requestedBy": "<your IAM principal ARN>"}'
```
Muss ein als `DELETING` zurückgebliebener Eintrag zurückgeholt werden, stellt ihn die State Machine für die Wiederherstellung aus der Kopie im Archiv-Bucket wieder her.
## Freigabe
Die Benachrichtigung enthält das Task-Token nicht. Das Token liegt in einem SecureString im Systems Manager Parameter Store (`/<stack>/approvals/<runId>`). Freigebender ist, wer diesen Parameter lesen und `states:SendTaskSuccess` aufrufen darf.
```bash
TOKEN=$(aws ssm get-parameter --name /<stack>/approvals/<runId> --with-decryption --query Parameter.Value --output text)
aws stepfunctions send-task-success --task-token "$TOKEN" \
  --task-output "{\"approved\": true, \"approver\": \"$(aws sts get-caller-identity --query Arn --output text)\"}"
# Reject:
aws stepfunctions send-task-failure --task-token "$TOKEN" --error Rejected --cause "<reason>"
```
Nach der Freigabe vergleicht die Funktion `approval` `approver` mit `requestedBy` der Start-Eingabe (`RequireSeparateApprover=true`, Standard). Derselbe Principal beendet den Lauf als `APPROVAL_REFUSED`, ohne etwas als `APPROVED` zu markieren. Ein Rollen-ARN und der ARN einer Sitzung dieser Rolle gelten als derselbe Principal. Andernfalls wird jede aufgeführte Datei im Ledger zu `APPROVED` mit `approvedBy`, `approvedAt` und dem Ausführungs-ARN. Die Funktion `delete` löscht nur Dateien mit diesem Eintrag; ein direkter Aufruf löscht nichts, was ihn nicht hat.

`approver` und `requestedBy` werden beide von den Aufrufern angegeben. `deletedBy` im Ledger wird aus `approvedBy` übernommen. Die Principals, die tatsächlich gestartet und freigegeben haben, stehen in den CloudTrail-Ereignissen `StartExecution` und `SendTaskSuccess`. Um die Funktionstrennung je Principal zu gewährleisten, trenne die startenden und die freigebenden Rollen in IAM. Der Vergleich von Starter und Freigebendem vergleicht zwei angegebene Werte. Er erzwingt nicht, dass ein anderer Principal freigegeben hat, und dieses Dokument behauptet das nicht. Die nachträgliche Kontrolle ist `userIdentity` in CloudTrail: gleiche die Principals ab, die `StartExecution` und `SendTaskSuccess` ausgeführt haben.
### Gültigkeit der Freigabe und Task-Token
Die Funktion `delete` löscht nur Einträge, deren Ledger-Status `APPROVED` ist, deren `approvalExecutionArn` der aktuellen Ausführung entspricht und deren `approvedAt` höchstens `ApprovalValidityHours` (Standard 24 Stunden) zurückliegt. Wird eine Ausführung nach der Freigabe gestoppt, bleiben die `APPROVED`-Einträge zwar stehen, passen aber nicht zum `claim` einer anderen Ausführung; ein direkter Aufruf der Funktion `delete` liefert daher `NOT_APPROVED`. Eine ältere Freigabe wird ebenso abgelehnt. `reconcile` setzt die übrigen Einträge auf `VERIFIED` zurück. Auch ein `claim`, der die ARN der gestoppten Ausführung selbst ist (das Ledger zeigt sie), wird abgelehnt, sofern diese Ausführung nicht `RUNNING` ist. Der Aufruf wird ebenfalls abgelehnt, wenn der Zustand der Ausführung nicht gelesen werden kann.

Das Task-Token wird gelöscht, wenn die Freigabe angenommen wird (Funktion `approval`), wenn die Freigabe durch denselben Principal wie den Starter abgelehnt wird, und nach einer Ablehnung, einem Timeout oder einer fehlgeschlagenen Ausführung (`summarize`). Ein Token, das eine Ausführung ohne Erreichen von `summarize` hinterlassen hat, löscht `watchdog`, sobald es älter ist als das Freigabe-Timeout plus eine Stunde. Das Token ist mit dem kundenverwalteten KMS-Schlüssel des Stacks verschlüsselt (Ausgabe `ApprovalTokenKeyArn`); zum Lesen braucht man `ssm:GetParameter` und `kms:Decrypt` auf diesen Schlüssel.

Beispiel einer IAM-Richtlinie für die Freigaberolle. IAM kann `states:SendTaskSuccess` und `states:SendTaskFailure` nicht auf eine Ressource begrenzen ([Step-Functions-Autorisierungsreferenz](https://docs.aws.amazon.com/service-authorization/latest/reference/list_awsstepfunctions.html), abgerufen am 2026-11-26) [E-024]; sie lassen sich also nicht auf die Ausführungen dieser State Machine beschränken. Wer das Token hält, kann diese Ausführung beantworten, einschränken lässt sich daher der Weg zum Token. Vergib `StartExecution` nicht an diese Rolle.
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadApprovalToken",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/<stack>/approvals/*"
    },
    {
      "Sid": "DecryptApprovalToken",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "<ApprovalTokenKeyArn>",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.<region>.amazonaws.com"}}
    },
    {
      "Sid": "ReportApproval",
      "Effect": "Allow",
      "Action": ["states:SendTaskSuccess", "states:SendTaskFailure"],
      "Resource": "*"
    }
  ]
}
```
## Attribute erneut setzen
Am Ende einer Wiederherstellung wird `manifests/<runId>-reapply.sh` geschrieben. Führen Sie es als root auf einem Host aus, der das Volume über NFS einhängt.
```bash
MOUNT_ROOT=/mnt/<volume> sh reapply.sh
```
Das Skript enthält nur `chown`, `chmod` und `touch -d`. Werte aus dem Ledger werden gegen strenge Formate geprüft, und jeder Schlüssel wird durch Quoting zu genau einem Shell-Wort. Ein Wert, der nicht passt, wird zu einem Kommentar und nicht ausgeführt. Ob die ONTAP-REST-API Eigentümer, Gruppe, Modus und Änderungszeit setzen kann, wurde nicht geprüft; dieser Weg ist daher nicht implementiert.
## Bereitstellung
### Voraussetzungen
- Sowohl der Alias als auch der ARN des Access Points (IAM braucht beide Formen; eine Richtlinie nur mit dem Alias wird bereitgestellt, aber zur Laufzeit abgelehnt)
- Eine Access-Point-Richtlinie. Dieser Stack erstellt den Access Point nicht (er erhält einen vorhandenen als Parameter) und verwaltet seine Richtlinie nicht; hänge sie nach dem Deployment wie unten gezeigt an. Ohne sie wird der erste S3-Aufruf zur Laufzeit abgelehnt
- Ein Name für den Archiv-Bucket (der Stack legt ihn an: `DeletionPolicy: Retain`, Block Public Access, standardmäßig SSE-S3, optional KMS, EventBridge-Benachrichtigungen aktiv, TLS erforderlich)
- Nur für `selection=ATIME` und die Erfassung von Attributen: VPC, Subnetze, ein Secret mit den ONTAP-Zugangsdaten, der Verwaltungsendpunkt, die Volume-UUID, `OntapVerifySsl`. Das Zertifikat des Verwaltungsendpunkts von FSx for ONTAP ist nicht von einer öffentlichen CA signiert, daher ist der Standard `false` (keine Prüfung). In diesem Modus werden die ONTAP-Zugangsdaten über eine Verbindung gesendet, deren Gegenstelle nicht authentifiziert wird (der Pfad bleibt im VPC). Mit `true` schlägt die Prüfung fehl, und der Lauf stoppt bei der Auswahl (an einem realen System beobachtet). Die Lambda-Funktion im VPC braucht eine Route zu Secrets Manager und S3 (VPC-Endpunkte oder NAT)
- Nur für Dateien über 5 GiB: ein Image in ECR. Der Access Point hat den Ursprung Internet, daher brauchen die Fargate-Subnetze ein NAT-Gateway oder eine öffentliche IP
- Ein bestätigtes Benachrichtigungsabonnement. Ein SNS-E-Mail-Abonnement bewirkt nichts, bis der Empfänger den Bestätigungslink anklickt; ohne Bestätigung sieht niemand die Freigabeanforderung
### Schritte
```bash
cd solutions/data-lifecycle/archive-verify-delete
cp samconfig.toml.example samconfig.toml   # replace every <PLACEHOLDER>
sam build && sam deploy
```
Hänge nach der Bereitstellung die Access-Point-Richtlinie an. Das Skript erzeugt aus den Rollen-ARNs in den Stack-Ausgaben eine Richtlinie, die `s3:DeleteObject` nur der Rolle der Funktion `delete` und `s3:PutObject` nur den Rollen für die Wiederherstellung gewährt.
```bash
aws cloudformation describe-stacks --stack-name <stack> --query 'Stacks[0].Outputs' > outputs.json
python3 tools/render_access_point_policy.py --outputs outputs.json \
  --access-point-arn arn:aws:s3:<region>:<account>:accesspoint/<name> > ap-policy.json
aws s3control put-access-point-policy --account-id <account> --name <name> --policy file://ap-policy.json
aws sns list-subscriptions-by-topic --topic-arn <NotificationTopicArn> \
  --query 'Subscriptions[].SubscriptionArn'   # no PendingConfirmation left
```
Hat der Access Point bereits eine Richtlinie, ersetzt dies sie; führe die vorhandenen Anweisungen zuvor zusammen.
Für Fargate baue das Image aus dem Repository-Stamm, übertrage es in dein eigenes ECR-Repository und setze `FargateImageUri`.
```bash
docker build --platform linux/arm64 \
  -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
```
Führe zuerst einen Lauf ohne `dryRun` aus (das heißt `true`).
```bash
aws stepfunctions start-execution --state-machine-arn <ArchiveStateMachineArn> \
  --input '{"olderThanDays": 365, "prefix": "projects/", "maxFiles": 20, "excludePatterns": ["*.vmdk"]}'
```
Zum Löschen übergib `"dryRun": false` als JSON-Boolean und trage den startenden Principal in `requestedBy` ein. Der String `"false"` ist ein Eingabefehler, und es wird nichts gelöscht.
## Verzeichnisstruktur
```
archive-verify-delete/
├── template.yaml                # SAM: bucket, ledger, 9 Lambda functions, 2 state machines, Fargate (optional), alarms
├── functions/{select,ontap_rest,record,ledger,approval,delete,summarize,restore,watchdog}/handler.py
├── statemachine/{archive,restore}.asl.json
├── fargate/{Dockerfile,entrypoint.py,requirements.txt}
├── tools/render_access_point_policy.py
├── tests/
├── docs/architecture.md, architecture.en.md
└── samconfig.toml.example
```
Die Fachlogik (Prüfsummen, Eingabeprüfung, Ledger, Prüfung nach der Wiederherstellung) liegt in [`shared/archive_verify/`](../../../shared/archive_verify/) und wird in `shared/tests/` getestet. Lese- und Schreibzugriffe auf den Access Point laufen über `shared/s3ap_helper.py`.
## Lokale Tests
```bash
python3 -m pytest solutions/data-lifecycle/archive-verify-delete/tests/ -v
python3 -m pytest shared/tests/test_archive_verify_*.py shared/tests/test_s3ap_helper_copy.py -v
```
Um zu bestätigen, dass eine defekte Löschentscheidung erkannt wird, wurden `test_does_not_delete_when_etag_changed` und `test_does_not_delete_when_size_differs_but_etag_equal` einmal gegen einen Stub ohne ETag-Vergleich ausgeführt; beide schlugen mit `assert 'DELETED' == 'CHANGED'` fehl. Die Prüfung des Freigabeeintrags und der Ausschluss ab 50 GiB wurden testgetrieben geschrieben und einmal gegen den früheren Code ausgeführt, wobei sie mit `assert 'DELETED' != 'DELETED'` und `KeyError: 'skippedTooLarge'` fehlschlugen, bevor sie implementiert wurden.
## Success Metrics
### Outcome
Selten gelesene Dateien nach Prüfung und menschlicher Freigabe in S3-Glacier-Speicherklassen verschieben, die Belegung des Volumes senken und verschobene Dateien über das Ledger finden und wiederherstellen können.
### Metrics
Zielwerte legst du selbst fest; hier werden keine genannt.
| Kategorie | Metrik | Definition |
|---|---|---|
| Business Outcome | Freigegebene Kapazität | Differenz des belegten Speichers des Volumes vor und nach dem Lauf (nach dem Aufräumen der Snapshots). `bytesDeleted` (`-result.json`) ist die Gesamtgröße der gelöschten Dateien, nicht der freigewordene Speicher: Solange Snapshots bestehen, sinkt die Belegung des Volumes nicht, und bei komprimierten oder deduplizierten Daten wird weniger Speicher frei als die logische Größe |
| Business Outcome | Erwartete monatliche Speicherersparnis | (GB, die aus dem Kapazitätspool verschoben wurden × Preisdifferenz) − (Speicher der Archivklasse, Overhead je Objekt, Abrufgebühren). Preise: siehe "Kostenabschätzung" unten |
| Technical KPI | Trefferquote der Prüfung | `VERIFIED` ÷ (`VERIFIED` + `MISMATCH`) |
| Technical KPI | Nicht gelöschte Dateien | Summe aus `CHANGED`, `MISMATCH` und `FAILED` |
| Technical KPI | Trefferquote der Wiederherstellungsprüfung | `RESTORE_VERIFIED` ÷ (`RESTORE_VERIFIED` + `RESTORE_MISMATCH`) |
| Quality KPI | Ohne Freigabe gelöschte Dateien | Muss 0 sein. `DELETED`-Einträge mit leerem `approvedBy` oder `approvedAt` zählen |
| Cost KPI | Lambda, Fargate, DynamoDB, S3-Anfragen, Zustandsübergänge und Speicher der Archivklasse je Lauf | Mit der Formel unter "Kostenabschätzung" aus einem gemessenen Lauf mit `dryRun=true` und kleinem `maxFiles` schätzen |
| Go / No-Go | Technisch: In einem Lauf in der realen Umgebung ist jede kopierte Datei `VERIFIED`, eine absichtlich erzeugte `CHANGED`-Datei wird nicht gelöscht, eine Selbstfreigabe durch den Starter wird abgelehnt, und wiederhergestellte Dateien sind `RESTORE_VERIFIED`. Geschäftlich: Die erwartete Ersparnis übersteigt den Betriebsaufwand (Freigabeaufwand, Bearbeitung von Wiederherstellungsanfragen); der Einstiegspunkt und die Zielreaktionszeit für Wiederherstellungsanfragen (einschließlich der Wiederherstellungszeit der Klasse) sind festgelegt; die Nutzer sind informiert | Verwende `dryRun=false` auf einem Produktiv-Volume erst, wenn alles erfüllt ist. Lege zuvor fest, wer jeweils entscheidet (Dateneigentümer, Freigebender, Betriebsverantwortlicher) |

Die PoC-Planung und die Prüfungen vor dem Produktivbetrieb stehen in der [Checkliste zur Prüfung vor dem Produktivbetrieb](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/04-build/checklists/pre-production-review.md) und im [Inventar vor der Migration](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/playbooks/01-assess/checklists/inventory.md) des FSx for ONTAP Adoption Playbook (beide auf Japanisch). Für den PoC dieses Musters ergeben sich Werte je Datei, wenn `maxFiles` schrittweise auf 20, 200 und 2.000 erhöht und dabei die Dauer der übergeordneten Ausführung, die Zustandsübergänge und die Fargate-Sekunden erfasst werden. Eine PoC-Planungstabelle steht im Playbook unter [Einstieg in der eigenen Umgebung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/domains/data-utilization/notes/archive-use-cases-and-integrations.md#自環境での始め方) (auf Japanisch).
### Measurement Method
Verlauf und Logs der Step-Functions-Ausführungen (`/aws/vendedlogs/states/<stack>-archive` und `-restore`, ohne Ausführungsdaten), `manifests/<runId>-result.json`, `manifests/<runId>-approval.json`, CloudWatch-EMF-Metriken (`FilesVerified`, `FilesDeleted`, `FilesMismatch`, `FilesChanged`, `FilesFailed`, `FilesStuckDeleting`, `BytesVerified`, `BytesDeleted`, `RestoreVerified`, `RestoreMismatch`, `ApprovalPendingHours`) und das Ledger.

Alarme (alle an das Benachrichtigungs-Topic):

| Alarm | Bedingung |
|---|---|
| `ArchiveExecutionsFailedAlarm`, `RestoreExecutionsFailedAlarm` | Eine oder mehr fehlgeschlagene, abgelaufene oder abgebrochene Ausführungen in 5 Minuten |
| `ApprovalPendingAlarm` | Eine Freigabeanforderung wartet länger als `ApprovalAlarmHours` (Standard 24) |
| `FilesStuckDeletingAlarm` | Ein Lauf endete mit `DELETING`- oder `APPROVED`-Einträgen |
| `FilesMismatchAlarm` | Eine archivierte Kopie stimmte nicht überein (`MISMATCH`) |
| `RestoreMismatchAlarm` | Eine wiederhergestellte Datei stimmte nicht mit dem Ledger überein |
Das Benachrichtigungs-Topic wird mit einem vom Kunden verwalteten KMS-Schlüssel verschlüsselt. Der AWS-verwaltete Schlüssel (`alias/aws/sns`) hat eine Schlüsselrichtlinie, die nicht bearbeitet werden kann, und EventBridge und CloudWatch-Alarme können nur dann in ein verschlüsseltes Topic veröffentlichen, wenn ein vom Kunden verwalteter Schlüssel den Service-Principals `kms:GenerateDataKey*` und `kms:Decrypt` erlaubt ([Amazon SNS key management](https://docs.aws.amazon.com/sns/latest/dg/sns-key-management.html), gelesen am 2026-11-26). Der zweite Lauf bestätigte, dass die EventBridge-Fehlerbenachrichtigungen und die Alarmbenachrichtigungen ankommen. [E-022]
## Performance Considerations
Die Standard-Nebenläufigkeit beruht auf der einen Messung unten. Das Übrige sind Entwurfsfaktoren und wurde nicht gemessen.
- Jede Quelldatei wird zweimal gelesen: einmal über den Access Point zum Hashen und einmal serverseitig durch `CopyObject`. Leseanfragen werden berechnet, und bei Daten im Kapazitätspool fallen zusätzlich Gebühren für das Lesen aus dem Kapazitätspool an
- Die Nebenläufigkeit ist `MapConcurrency` (Standard 1, für Archivierung und Wiederherstellung). In einer Messung las eine Lambda-Funktion 5,3 GB (rund 4,94 GiB) in 69,8 Sekunden über den Access Point, rund 76 MB/s in einem Strom, was rund 60 % des Durchsatzes von 128 MBps dieser Umgebung entspricht. Zwei Ströme wären rund 152 MB/s und lägen über dieser Kapazität. Jede Datei wird zweimal gelesen, und dasselbe Volume bedient deine Nutzer, daher ist der Standard 1. Parallele Lesevorgänge wurden nicht gemessen. Beobachte vor einer Erhöhung `DataReadBytes` des Dateisystems und die Latenz der Clients während eines Laufs
- Der Standard von 5 GiB für `LargeFileThresholdBytes` folgt aus der Grenze von `CopyObject` mit einer einzelnen Anfrage. Bei der obigen Geschwindigkeit würden die 15 Minuten von Lambda rund 63 GiB abdecken, doch das ist ein einzelner Datenpunkt
- Die Auflistung lädt jedes Ergebnis von `ListObjectsV2` in den Speicher einer einzelnen Lambda-Funktion. Teile ab einigen Millionen Objekten mit `prefix` auf
- `selection=ATIME` durchläuft Verzeichnisse in die Tiefe. Die Scan-Grenze liegt bei 200.000 Einträgen (`ONTAP_SCAN_LIMIT`); darüber hinaus werden Teilergebnisse zurückgegeben
- Die Wartezeit der Wiederherstellung hängt von der Klasse und `tier` ab. AWS dokumentiert für S3 Glacier Deep Archive innerhalb von 12 Stunden bei Standard und 48 Stunden bei Bulk. `RestoreMaxWaitHours` ist standardmäßig 72. Bei Klassen mit langen Wartezeiten bedeutet ein größeres `RestorePollMinutes` weniger Zustandsübergänge durch Polling
- Fargate-Tasks sind durch `FargateTimeoutSeconds` begrenzt (Standard 7200 s). Jeder Task hat ein `TimeoutSeconds`, und ein Timeout wird wiederholt
## Kostenabschätzung
Es wurde keine Rechnung gemessen. Unten stehen gemessene Verbrauchswerte und veröffentlichte Bedingungen je Objekt, aus denen sich schätzen lässt.
Zustandsübergänge je Datei in den beiden Läufen (je ein Lauf):

| Ausführung | Zustandsübergänge je Datei | Quelle |
|---|---|---|
| Archivierung, Probelauf | 17 (119 ÷ 7), 18 (72 ÷ 4) | Lauf mit sieben Dateien einschließlich 5,5 GiB; Lauf zu Ausschlüssen und Freigabe |
| Archivierung, echter Lauf (einschließlich Löschen) | 18 (127 ÷ 7), 19,5 (78 ÷ 4) | Gleiche |
| Wiederherstellung (`Expedited`; der Lauf zu Ausschlüssen und Freigabe mit Prüfung) | 18 (107 ÷ 6), 14 (56 ÷ 4) | Gleiche |
Klassen mit langen Wartezeiten fügen bei jedem Poll Übergänge hinzu.
Speicherbedingungen je Objekt ([Comparing the Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html#sc-compare), gelesen am 2026-11-26):

| Klasse | Mindestspeicherdauer | Overhead je Objekt, Mindestgröße der Abrechnung |
|---|---|---|
| S3 Glacier Instant Retrieval | 90 Tage | Mindestgröße der Abrechnung je Objekt 128 KB |
| S3 Glacier Flexible Retrieval | 90 Tage | 40 KB Metadaten (32 KB zum Preis dieser Klasse, 8 KB zum Preis von S3 Standard) |
| S3 Glacier Deep Archive | 180 Tage | 40 KB Metadaten (gleiche Aufteilung) |
Formel: Monatskosten ≈ Dateien × Übergänge je Datei × Preis je Übergang + Dauer von Lambda und Fargate × Preis + Dateien × (Anfragepreise für `CopyObject`, `HeadObject`, `DeleteObject` und Ähnliches) + Speicher (Daten + Dateien × Overhead) × Preis der Klasse + Abrufgebühren bei der Wiederherstellung. Entnimm die Preise für deine Region und das Datum aus [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) und [AWS Step Functions pricing](https://aws.amazon.com/step-functions/pricing/); hier werden keine genannt.
## Governance Note
> Dieses Muster bietet technische Architekturhinweise. Es ist keine Rechts-, Compliance- oder Regulierungsberatung. Ziehe qualifizierte Fachleute hinzu.
- Prüfergebnisse und Freigabe sind unterstützende Signale für die endgültige Entscheidung einer Person. Es wird keine KI verwendet
- Das Muster erfüllt keine Anforderungen an Aufbewahrung oder Unveränderlichkeit. Object Lock und ähnliche Funktionen werden nicht verwendet, daher kann jeder mit Berechtigung löschen
- Klassifizierung der Ausgaben: Ledger und Manifeste enthalten Dateipfade, Größen, Hashes und Attribute. Ein Pfad kann den Namen einer Person oder eine Patienten- oder Fallkennung enthalten, daher tragen die Ausgaben standardmäßig `data_classification` `RESTRICTED` ("Restricted — Limited access" in `shared/data_classification.py`). Ist die Klassifizierung der Daten selbst strenger, setze den Parameter `DataClassification` darauf. Die Klassifizierung legst du fest. Dateiinhalte gehen in den Archiv-Bucket; behandle sie so, wie die Originaldaten klassifiziert sind
- Human Review: Für jeden Lauf ist eine Freigabe erforderlich. Es gibt keine konfidenzbasierte automatische Freigabe. Standardmäßig wird nichts gelöscht, wenn Starter und Freigebender derselbe Principal sind. Verglichen werden angegebene Werte; das ist kein Identitätsnachweis. Die nachgelagerte Kontrolle ist `userIdentity` in CloudTrail
- IAM: Nur die Rolle der Funktion `delete` hat `s3:DeleteObject` am Access Point, und nur die State Machine für die Wiederherstellung und die Fargate-Task-Rolle der Wiederherstellung haben dort `s3:PutObject`. Der Archiv-Fargate-Task kopiert nur und kann Quelldateien weder löschen noch überschreiben. Kein Principal kann Ledger-Einträge löschen
- Audit: Freigaben und Löschungen werden im Ledger (`approvedBy`, `approvedAt`, `requestedBy`, `deletedBy`, `deletedAt`), in `manifests/<runId>-approval.json` sowie im Verlauf und in den Logs von Step Functions festgehalten. CloudTrail erfasst die Löschungen nur, wenn für einen Trail S3-Datenereignisse aktiviert sind; dies wurde im Lauf nicht geprüft
- Anzahl der Kopien: Ohne zweite Kopie ist das Objekt im Archiv-Bucket nach dem Löschen die einzige Kopie. Die Freigabebenachrichtigung weist darauf hin
## Einschränkungen und ungeprüfte Punkte
- Ein direktes Kopieren vom Access Point in einen Bucket in einer anderen Region lieferte `AccessDenied` (ein Access Point, einmal). Die zweite Kopie zielt nur auf Buckets in derselben Region
- Auf einem Volume im UNIX-Stil geprüft. Eine Inhaltsänderung, die Größe und mtime beibehält, wird von der Prüfung von ETag und Größe nicht erkannt (siehe "Im End-to-End-Lauf beobachtetes Verhalten"). Ob `chown` den ETag ändert, wurde nicht geprüft
- Die Erfassung von Attributen nutzt Verzeichnislisten und liest für eine Datei das gesamte übergeordnete Verzeichnis; große Verzeichnisse sind langsam
- Versionierung im Archiv-Bucket ist kein Object Lock. Versionen bleiben erhalten, aber jeder mit Berechtigung kann sie löschen
- Dateien über 50 GiB werden standardmäßig nicht ausgewählt. Mit `allowOversize: true` aufgenommen, lassen sie sich nicht in den Access Point wiederherstellen; lade sie aus dem Bucket herunter
- `requestedBy` und `approver` sind angegebene Werte. Prüfe die Trennung je Principal mit IAM und CloudTrail
## Zugehörige Dokumente
- [Architecture (EN)](docs/architecture.en.md)
- [Hinweise zur Kompatibilität von S3 Access Points](../../../docs/s3ap-compatibility-notes.md)
- [Vergleich von 9 Mechanismen zum Verschieben von Dateien in Archivklassen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/reference/comparison/archive-tiering-library-options.md) (auf Japanisch)

---

<!-- playbook-reading:start -->
## Vor dem Produktivbetrieb lesen

Wie sich die nach der Bereitstellung auftretenden Einschränkungen in Entwurfsentscheidungen übersetzen, steht im [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) beschrieben. Liegt derselbe Inhalt an zwei Stellen, überlebt die nicht mehr gepflegte Kopie die korrigierte.

- [Datennutzung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — Einschränkungen des Zugriffs über einen Access Point (alle Patterns)
- [Datensicherung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-protection) — wo sich die Entscheidungen für dieses Pattern häufen
- [Aufbauen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — vor dem Produktivbetrieb durchgehen (alle Patterns)
<!-- playbook-reading:end -->
