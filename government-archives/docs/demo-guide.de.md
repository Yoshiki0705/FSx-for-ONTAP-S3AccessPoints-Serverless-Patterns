# UC16 Demoskript (30-Minuten-Slot)

🌐 **Language / 언어 / 语言 / 語言 / Langue / Sprache / Idioma**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

> Hinweis: Diese Übersetzung wurde von Amazon Bedrock Claude erstellt. Beiträge zur Verbesserung der Übersetzungsqualität sind willkommen.

## Voraussetzungen

- AWS-Konto, ap-northeast-1
- FSx for NetApp ONTAP + S3 Access Point
- `government-archives/template-deploy.yaml` bereitstellen (`OpenSearchMode=none` zur Kostensenkung)

## Zeitplan

### 0:00 - 0:05 Einführung (5 Minuten)

- Anwendungsfall: Digitalisierung der Verwaltung öffentlicher Dokumente für Kommunen und Behörden
- Belastung durch gesetzliche Fristen (20 Werktage) für FOIA / Informationsfreiheitsanfragen
- Herausforderung: PII-Erkennung und Schwärzung dauern manuell mehrere Stunden

### 0:05 - 0:10 Architektur (5 Minuten)

- Kombination aus Textract + Comprehend + Bedrock
- 3 Modi für OpenSearch (none / serverless / managed)
- Automatische Verwaltung der NARA GRS-Aufbewahrungsfristen

### 0:10 - 0:15 Bereitstellung (5 Minuten)

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-uc16-demo \
  --parameter-overrides \
    DeployBucket=<your-deploy-bucket> \
    S3AccessPointAlias=<your-ap-ext-s3alias> \
    VpcId=<vpc-id> \
    PrivateSubnetIds=<subnet-ids> \
    NotificationEmail=ops@example.com \
    OpenSearchMode=none \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 0:15 - 0:22 Verarbeitungsausführung (7 Minuten)

```bash
# Beispiel-PDF (mit vertraulichen Informationen) hochladen
aws s3 cp sample-foia-request.pdf \
  s3://<s3-ap-arn>/archives/2026/05/req-001.pdf

# Step Functions ausführen
aws stepfunctions start-execution \
  --state-machine-arn <uc16-StateMachineArn> \
  --input '{"opensearch_enabled": "none"}'
```

Ergebnisse überprüfen:
- `s3://<output-bucket>/ocr-results/archives/2026/05/req-001.pdf.txt` (Rohtext)
- `s3://<output-bucket>/classifications/archives/2026/05/req-001.pdf.json` (Klassifizierungsergebnis)
- `s3://<output-bucket>/pii-entities/archives/2026/05/req-001.pdf.json` (PII-Erkennung)
- `s3://<output-bucket>/redacted/archives/2026/05/req-001.pdf.txt` (geschwärzte Version)
- `s3://<output-bucket>/redaction-metadata/archives/2026/05/req-001.pdf.json` (Sidecar)

### 0:22 - 0:27 FOIA-Fristenverfolgung (5 Minuten)

```bash
# FOIA-Anfrage registrieren
aws dynamodb put-item \
  --table-name <fsxn-uc16-demo>-foia-requests \
  --item '{
    "request_id": {"S": "REQ-001"},
    "status": {"S": "PENDING"},
    "deadline": {"S": "2026-05-25"},
    "requester": {"S": "jane@example.com"}
  }'

# FOIA Deadline Lambda manuell ausführen
aws lambda invoke \
  --function-name <fsxn-uc16-demo>-foia-deadline \
  --payload '{}' \
  response.json && cat response.json
```

SNS-Benachrichtigungs-E-Mail überprüfen.

### 0:27 - 0:30 Zusammenfassung (3 Minuten)

- Pfad zur OpenSearch-Aktivierung (mit `serverless` für vollständige Suche)
- GovCloud-Migration (FedRAMP High-Anforderungen)
- Nächste Schritte: Interaktive FOIA-Antwortgenerierung mit Bedrock-Agenten

## Häufig gestellte Fragen und Antworten

**F. Ist eine Anpassung an das japanische Informationsfreiheitsgesetz (30 Tage) möglich?**  
A. Ja, durch Anpassung von `REMINDER_DAYS_BEFORE` und der fest codierten 20 Werktage (US-Bundesfeiertage → japanische Feiertage).

**F. Wo werden die ursprünglichen PII gespeichert?**  
A. Nirgendwo. `pii-entities/*.json` enthält nur SHA-256-Hashes, `redaction-metadata/*.json` ebenfalls nur Hash + Offset. Wiederherstellung erfordert erneute Ausführung vom Originaldokument.

**F. Wie können die Kosten für OpenSearch Serverless gesenkt werden?**  
A. Minimum 2 OCU = ca. $350/Monat. Außerhalb der Produktion wird Abschaltung empfohlen.
A. Mit `OpenSearchMode=none` überspringen oder `OpenSearchMode=managed` + `t3.small.search × 1` auf ~$25/Monat reduzieren.

---

## Über das Ausgabeziel: Auswählbar mit OutputDestination (Pattern B)

UC16 government-archives unterstützt seit dem Update vom 11.05.2026 den Parameter `OutputDestination`
(siehe `docs/output-destination-patterns.md`).

**Betroffene Workloads**: OCR-Text / Dokumentklassifizierung / PII-Erkennung / Schwärzung / OpenSearch-Vorstufen-Dokumente

**2 Modi**:

### STANDARD_S3 (Standard, wie bisher)
Erstellt einen neuen S3-Bucket (`${AWS::StackName}-output-${AWS::AccountId}`) und
schreibt AI-Ergebnisse dorthin. Nur das Manifest der Discovery Lambda wird in den S3 Access Point
geschrieben (wie bisher).

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=STANDARD_S3 \
    ... (andere erforderliche Parameter)
```

### FSXN_S3AP ("no data movement"-Pattern)
OCR-Text, Klassifizierungsergebnisse, PII-Erkennungsergebnisse, geschwärzte Dokumente und Schwärzungsmetadaten werden
über den FSxN S3 Access Point auf **dasselbe FSx ONTAP-Volume** wie die Originaldokumente zurückgeschrieben.
Mitarbeiter der öffentlichen Dokumentenverwaltung können AI-Ergebnisse direkt innerhalb der bestehenden SMB/NFS-Verzeichnisstruktur einsehen.
Es wird kein Standard-S3-Bucket erstellt.

```bash
aws cloudformation deploy \
  --template-file government-archives/template-deploy.yaml \
  --stack-name fsxn-government-archives-demo \
  --parameter-overrides \
    OutputDestination=FSXN_S3AP \
    OutputS3APPrefix=ai-outputs/ \
    S3AccessPointName=eda-demo-s3ap \
    ... (andere erforderliche Parameter)
```

**Rücklesen in der Kettenstruktur**:

UC16 hat eine Kettenstruktur, bei der nachfolgende Lambdas die Ergebnisse vorheriger Stufen zurücklesen (OCR → Classification →
EntityExtraction → Redaction → IndexGeneration). Daher lesen `get_bytes/get_text/get_json` in `shared/output_writer.py`
vom selben Destination zurück, in das geschrieben wurde.
Dadurch funktioniert das Rücklesen vom FSxN S3 Access Point auch bei `OutputDestination=FSXN_S3AP`,
und die gesamte Kette arbeitet mit einem konsistenten Destination.

**Hinweise**:

- Angabe von `S3AccessPointName` wird dringend empfohlen (IAM-Berechtigung sowohl für Alias- als auch ARN-Format)
- Objekte über 5 GB sind mit FSxN S3AP nicht möglich (AWS-Spezifikation), Multipart-Upload erforderlich
- ComplianceCheck Lambda verwendet nur DynamoDB und wird daher nicht von `OutputDestination` beeinflusst
- FoiaDeadlineReminder Lambda verwendet nur DynamoDB + SNS und wird nicht beeinflusst
- OpenSearch-Index wird separat über den Parameter `OpenSearchMode` verwaltet (unabhängig von `OutputDestination`)
- AWS-Spezifikationsbeschränkungen siehe
  [Abschnitt "AWS-Spezifikationsbeschränkungen und Workarounds" im Projekt-README](../../README.md#aws-仕様上の制約と回避策)
  und [`docs/output-destination-patterns.md`](../../docs/output-destination-patterns.md)

---

## Verifizierte UI/UX-Screenshots

Gleiche Richtlinie wie bei den Demos von Phase 7 UC15/16/17 und UC6/11/14: **UI/UX-Bildschirme, die Endbenutzer
im täglichen Betrieb tatsächlich sehen**. Technische Ansichten (Step Functions-Graph, CloudFormation
Stack-Events usw.) werden in `docs/verification-results-*.md` zusammengefasst.

### Verifizierungsstatus für diesen Anwendungsfall

- ✅ **E2E-Verifizierung**: SUCCEEDED (Phase 7 Extended Round, Commit b77fc3b)
- 📸 **UI/UX-Aufnahme**: ✅ Abgeschlossen (Phase 8 Theme D, Commit d7ebabd)

### Vorhandene Screenshots (Phase 7-Verifizierung)

![Step Functions Graph-Ansicht (SUCCEEDED)](../../docs/screenshots/masked/uc16-demo/step-functions-graph-succeeded.png)

![S3-Ausgabe-Bucket](../../docs/screenshots/masked/uc16-demo/s3-output-bucket.png)

![DynamoDB retention-Tabelle](../../docs/screenshots/masked/uc16-demo/dynamodb-retention-table.png)
### UI/UX-Zielbildschirme bei erneuter Verifizierung (empfohlene Aufnahmeliste)

- S3-Ausgabe-Bucket (ocr-results/, classified/, redacted/, compliance/)
- Textract OCR-Ergebnis JSON-Vorschau (Cross-Region us-east-1)
- Geschwärztes (Redaction) Dokumentvorschau
- DynamoDB retention-Tabelle (FOIA-Fristenverwaltung)
- FOIA-Erinnerungs-SNS-E-Mail-Benachrichtigung
- OpenSearch-Index (IndexGeneration-Ergebnis, wenn OpenSearchMode aktiviert)
- AI-Ergebnisse auf FSx ONTAP-Volume (im FSXN_S3AP-Modus)

### Aufnahmeleitfaden

1. **Vorbereitung**:
   - `bash scripts/verify_phase7_prerequisites.sh` zur Überprüfung der Voraussetzungen (gemeinsame VPC/S3 AP vorhanden)
   - `UC=government-archives bash scripts/package_generic_uc.sh` für Lambda-Pakete
   - `bash scripts/deploy_generic_ucs.sh UC16` zur Bereitstellung

2. **Beispieldaten platzieren**:
   - Beispiel-PDF/Bilder über S3 AP Alias mit Präfix `archives/` hochladen
   - Step Functions `fsxn-government-archives-demo-workflow` starten (Eingabe `{}`)

3. **Aufnahme** (CloudShell/Terminal schließen, Benutzername oben rechts im Browser schwärzen):
   - Überblick über S3-Ausgabe-Bucket `fsxn-government-archives-demo-output-<account>`
   - JSON-Vorschau der Ausgaben für OCR / Classification / Redaction-Phasen
   - Elementliste der DynamoDB retention-Tabelle
   - SNS FOIA-Erinnerungs-E-Mail

4. **Maskierung**:
   - `python3 scripts/mask_uc_demos.py government-archives-demo` für automatische Maskierung
   - Zusätzliche Maskierung gemäß `docs/screenshots/MASK_GUIDE.md` (bei Bedarf)

5. **Bereinigung**:
   - `bash scripts/cleanup_generic_ucs.sh UC16` zum Löschen
   - VPC Lambda ENI-Freigabe dauert 15-30 Minuten (AWS-Spezifikation)
