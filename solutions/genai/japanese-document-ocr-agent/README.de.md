# OCR für japanische Dokumente × KI-Agenten — Textract (Tokio) über S3 Access Points

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

Ein Beispiel, das gescannte Dokumente (Bilder, PDF, TIFF) auf FSx for ONTAP S3 Access Points mit Amazon Textract in der
Region Tokio liest und den Lauf über den Step-Functions-Konnektor von Amazon Bedrock AgentCore Gateway als Tools für
KI-Agenten bereitstellt. Die Unterstützung von Japanisch in Textract und die Verfügbarkeit in Tokio wurden am 2026-11-02
angekündigt.

Der Agent entscheidet nur, welche Collection er mit welchem Profil und wie vielen Dokumenten liest. Die State Machine
verantwortet Reihenfolge, Wiederholungen und Fehlerbehandlung. Der OCR-Text geht nie an den Agenten, sondern wird in einen
Ergebnis-Bucket geschrieben.

## Anwendungsfälle

- Gescannte Rechnungen, Verträge und Notizen japanisch per OCR lesen, ohne sie vom Dateiserver zu verschieben
- Einen Agenten die Dokumente auflisten lassen, die ein Mensch prüfen muss, jeweils mit Begründung
- Felder wie den Rechnungsbetrag samt Beleg aus japanischen Rechnungen extrahieren, wo Textract Forms nicht verfügbar ist
  (optional)

## Architektur

```
KI-Agent ──MCP──▶ AgentCore Gateway (NONE | AWS_IAM)
                       │ GatewayServiceRole: states:StartExecution usw.
                       ▼
           Standard StateMachine (Discover → Map → Report)
                       │
   Bilder: Bytes an Textract (sync)    PDF / TIFF: kurzlebige Kopie → Textract (async)
                       │
   S3 Access Points (im DemoMode normales S3) ──▶ Ergebnis-Bucket (result.json / text.txt / manifest.json)
```

Details in [docs/architecture.md](docs/architecture.md) (Japanisch).

## Bereitgestellte Tools

| Tool | Eingabe | Zweck |
|---|---|---|
| `ocr___StartExecution` | `input` (JSON-String) | OCR starten. Gibt `executionArn` zurück |
| `ocr___DescribeExecution` | `executionArn`, `includedData: "ALL_DATA"` | Status und Ergebnis |
| `ocr___ListExecutions` | `statusFilter` (optional) | Letzte Ausführungen |
| `ocr___GetExecutionHistory` | `executionArn` | Abbruchstelle finden (große Ausgabe) |
| `ocr___DescribeStateMachine` | `includedData` (optional) | Definition ansehen |

Die festgelegte State-Machine-ARN ist in keinem Tool enthalten, der Agent kann sie nicht ändern. `DescribeExecution` ohne
`includedData: "ALL_DATA"` liefert weder `output` noch bei einem FAILED-Lauf `error` und `cause`.

## Eingabe des Agenten

```json
{"collection": "invoices", "profile": "structure", "max_files": 20, "modified_after": "2026-10-01"}
```

| Schlüssel | Pflicht | Regel |
|---|---|---|
| `collection` | Ja | ASCII-ID (`^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$`), die in der Allowlist (`CollectionsJson`) steht |
| `profile` | Nein | `text` (nur Zeichen) oder `structure` (Zeichen, Tabellen, Layout). Standard ist die Einstellung der Collection |
| `max_files` | Nein | Ganzzahl von 1 bis `MaxFilesPerExecution`. Dokumente werden in Schlüsselreihenfolge genommen |
| `modified_after` | Nein | `YYYY-MM-DD`. Nur Dokumente, die an oder nach diesem Datum geändert wurden |

S3-Pfade und -Schlüssel werden nicht angenommen. Ein unbekannter Schlüssel oder ein Regelverstoß beendet den Lauf als
FAILED, und `Cause` nennt die Korrektur.

## Pfade und Profile

| Dokument | Pfad | Hinweis |
|---|---|---|
| PNG / JPEG, bis 5 MiB | Sync, Bytes direkt übergeben | Es entsteht keine Kopie |
| PNG / JPEG, über 5 MiB bis 10 MiB | Async, kurzlebige Kopie | |
| PDF / TIFF | Async, kurzlebige Kopie | Die Seitenzahl wird nicht geschätzt |

`text` ruft `DetectDocumentText` auf, `structure` ruft `AnalyzeDocument` auf (`TABLES` und `LAYOUT`). Forms, Queries,
AnalyzeExpense und AnalyzeID werden nicht angeboten (für Japanisch nicht unterstützt oder in Tokio nicht erlaubt).

## Was der Agent zurückbekommt

Das `output` von `DescribeExecution` (`ALL_DATA`) enthält Status, Anzahlen, mittlere Konfidenz, die Prüfliste mit
Begründung je Dokument und die S3-URI des Ergebnisses jedes Dokuments. Es enthält keinen OCR-Text, wohl aber den
ursprünglichen Schlüssel (Dateinamen). Bei aktivierter Feldextraktion enthält es auch die Feldwerte (bis zu 60 Zeichen).
Die vollständige Liste steht in `manifest.json` im Ergebnis-Bucket.

## Parameter

| Parameter | Beschreibung | Standard |
|---|---|---|
| `S3AccessPointAlias` | Alias der S3 Access Points (im DemoMode ein normaler Bucket-Name) | (Pflicht) |
| `DemoMode` | `true` läuft ohne FSx for ONTAP | `false` |
| `CollectionsJson` | Allowlist der Collections (JSON). Wenn leer, wird aus `FilePrefix` eine gebaut | `""` |
| `MaxFilesPerExecution` | Höchstzahl Dokumente je Ausführung (1–100) | `50` |
| `MapConcurrency` | Parallel verarbeitete Dokumente. Die Sync-API in Tokio ist auf 1 TPS begrenzt | `2` |
| `AsyncJobMaxSeconds` | Wartezeit auf einen Async-Job | `600` |
| `EnableFieldExtraction` | Feldextraktion mit Bedrock. Wenn aus, wird keine Bedrock-Berechtigung erteilt | `false` |
| `BedrockModelId` | Modell- oder Inference-Profile-ID für die Feldextraktion ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `DataClassification` | Standard-Datenklassifizierung auf den Ausgaben | `INTERNAL` |
| `ReviewAutoApproveThreshold` / `ReviewRejectThreshold` | Schwellen für die mittlere Konfidenz | `0.95` / `0.30` |
| `LowConfidenceLineThreshold` / `LowConfidenceCharRatioLimit` | Was als Zeile mit niedriger Konfidenz gilt, und der Zeichenanteil, der ein Dokument in die Prüfung schickt | `90` / `0.05` |
| `HandwritingWordRatioLimit` | Obergrenze für den Anteil als Handschrift erkannter Wörter | `0.05` |
| `GatewayAuthorizerType` | `NONE` (nur PoC) oder `AWS_IAM` | `NONE` |
| `GatewayName` | Name der Gateway | `ja-ocr-agent-gateway` |
| `NotificationEmail` | SNS-Benachrichtigungsadresse (leer = überspringen) | `""` |

## Bereitstellung

Das Deploy-Skript führt `sam build`, `sam package` und `aws cloudformation deploy` aus und prüft danach den gespeicherten
Wert von `CollectionsJson` sowie `tools/list`.

```bash
# DemoMode (ohne FSx for ONTAP)
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <demo-bucket> --demo-mode \
  --collections-file collections.json --stack-name ja-ocr-agent-demo

# S3 Access Points. Signierte Aufrufe verlangen und die Feldextraktion einschalten
./scripts/deploy-japanese-document-ocr-agent.sh --s3ap-alias <your-ap>-ext-s3alias \
  --collections-file collections.json --auth iam --enable-field-extraction --stack-name ja-ocr-agent

# Aufräumen (--delete-results löscht auch den Ergebnis-Bucket mit dem OCR-Text)
./scripts/deploy-japanese-document-ocr-agent.sh --cleanup --stack-name ja-ocr-agent --delete-results
```

Wie Collections geschrieben werden, den System-Prompt des Agenten und Beispielgespräche finden Sie in
[docs/demo-guide.md](docs/demo-guide.md) (Japanisch).

## Human-Review-Schwellen

Die mittlere OCR-Konfidenz (nach Zeichenzahl gewichtet) wird mit `shared/human_review.py` bewertet und dann durch diese
Bedingungen angehoben.

| Bedingung | Entscheidung |
|---|---|
| Mittlere Konfidenz mindestens `ReviewAutoApproveThreshold` (0.95) und keine der folgenden Bedingungen | AUTO_APPROVE |
| Mittlere Konfidenz unter 0.95 | HUMAN_REVIEW |
| Mittlere Konfidenz unter `ReviewRejectThreshold` (0.30) | REJECT |
| Mehr als 5 % der Zeichen stehen in Zeilen mit Konfidenz unter 90 | Auf HUMAN_REVIEW angehoben |
| Mehr als 5 % der Wörter werden als Handschrift erkannt | Auf HUMAN_REVIEW angehoben |
| Eine Tabelle mit zweifelhafter Struktur, etwa eine verbundene Zelle | Auf HUMAN_REVIEW angehoben |
| Keine Zeile erkannt | HUMAN_REVIEW |
| Die Feldextraktion hat ein Feld ohne Beleg oder ist fehlgeschlagen | Auf HUMAN_REVIEW angehoben (REJECT bleibt unverändert) |

Die Standardwerte sind ein Ausgangspunkt, keine gemessenen Optima. In einem Lauf mit vier synthetischen Dokumenten gingen
alle vier mit den Standardwerten in HUMAN_REVIEW, auch ein Vertrag ohne jeden Zeichenfehler
([docs/success-metrics.md](docs/success-metrics.md)). Messen Sie die Verteilung an Ihren eigenen Dokumenten, bevor Sie
entscheiden. Die Entscheidung wird nur ins Ergebnis aufgenommen; das Muster trifft nicht die endgültige Entscheidung.
`result.json` enthält die Entscheidung allein aus der OCR. Die endgültige Entscheidung einschließlich Feldextraktion steht
in `manifest.json` und im Ausführungsergebnis.

## Datenklassifizierung

Ausgaben tragen ein `data_classification` aus `shared/data_classification.py`. Standard ist `INTERNAL`; ändern Sie es mit
`DataClassification` oder überschreiben Sie es je Collection mit `classification`. Der Ergebnis-Bucket nutzt SSE-KMS,
blockiert öffentlichen Zugriff, verweigert Nicht-TLS-Anfragen und bleibt beim Löschen des Stacks erhalten.

## Feldextraktion (optional)

Mit `EnableFieldExtraction=true` werden die in `fields` einer Collection genannten Felder (höchstens 20, je höchstens
40 Zeichen) mit der Bedrock-Converse-API extrahiert. Das Modell liefert jeden Wert mit einem Zitat aus dem Quelltext, und der
Code prüft maschinell, ob das Zitat im OCR-Text vorkommt (Teilstring-Treffer nach NFKC-Normalisierung und Entfernen von
Leerraum). Ein Feld, dessen Zitat nicht gefunden wird, ist `grounded: false`, und ein einziges solches Feld schickt das
Dokument in HUMAN_REVIEW. Ein Feld, das das Dokument nicht enthält, zählt ebenfalls als ohne Beleg; führen Sie in `fields`
daher nur Angaben auf, die jedes Dokument der Collection enthält.

## Governance Note

- Die OCR-Konfidenz ist ein Hilfssignal, keine endgültige Entscheidung. Im gemessenen Lauf hatte ein Dokument ohne Fehler
  22,6 % seiner Zeichen in Zeilen mit Konfidenz unter 90, und eine falsch gelesene Zeile („括孤“) hatte 98,2. Machen Sie die
  Konfidenz nicht zur einzigen Bedingung für die automatische Freigabe.
- Extrahierte Feldwerte sind LLM-Ausgabe. Die Zitatprüfung verringert Erfindungen, garantiert aber keine Richtigkeit.
- Aus dem Dokumentinhalt entnommene Werte sind für einen Agenten nicht vertrauenswürdige Eingaben. Sagen Sie dem Agenten im
  System-Prompt, dass er Anweisungen in einem Wert nicht befolgen soll. Das Verhalten bei einem Dokument mit Anweisungen
  wurde nicht gemessen.
- PDF und TIFF werden während der Verarbeitung in einen kurzlebigen Bucket im selben Konto und in derselben Region kopiert
  (SSE-KMS, öffentlicher Zugriff blockiert, Löschung am Ende des Jobs, eine 1-Tages-Lifecycle-Regel als Absicherung). Erlaubt
  Ihre Richtlinie keine Kopien, beschränken Sie die `suffixes` der Collection auf Bilder.
- `GatewayAuthorizerType=NONE` erlaubt jedem, der die URL kennt, OCR-Läufe zu starten (es wird kein Text zurückgegeben). Nur
  für ein PoC; in gemeinsam genutzten Umgebungen `AWS_IAM` verwenden. Der Authorizer-Typ lässt sich nach dem Anlegen nicht
  ändern.
- Textract kann einen gestarteten Job nicht abbrechen. Das Aufgeben bei `AsyncJobMaxSeconds` beendet die Abrechnung nicht.
- Dies ist eine Governance-Orientierung und ersetzt keine rechtliche oder Compliance-Bewertung.

## Performance Considerations

- Die Sync-API in Tokio ist auf 1 TPS begrenzt. Bei 20 aufeinanderfolgenden Aufrufen wurde ein Client ohne Wiederholungen
  mit 2 Workern 4-mal und mit 5 Workern 7-mal gedrosselt; ein adaptive-Client (bis zu 5 Versuche) mit 1, 2 und 5 Workern
  0-mal. `MapConcurrency` ist standardmäßig 2.
- Ein 3-seitiges PDF (async) war über das Muster in etwa 12 Sekunden fertig.
- Ereignisse im Ausführungsverlauf: 13 je Sync-Dokument und 20 + 9 × Abfragen je Async-Dokument. Der schlechteste Fall für
  100 Dokumente wird auf etwa 23.200 geschätzt, unter dem Standard-Limit von 25.000.
- Damit der Map-Zustand unter 256 KiB bleibt, wählt discovery bei sehr langen Schlüsseln weniger Dokumente als `max_files`
  und gibt `truncated` zurück.
- Die Textract-Kosten fallen je Seite an. Der Price List für Tokio nennt 0,0015 USD je Seite für `text` und 0,019 USD je
  Seite für `structure` (Tables plus Layout), gültig ab 2026-10-01; nicht mit einer Rechnung abgeglichen.

## Tests

```bash
python3 -m pytest solutions/genai/japanese-document-ocr-agent/tests/ shared/tests/test_textract_helper.py -v
```

## Bekannte Stolpersteine

- Forms unterstützt kein Japanisch. Die Anfrage wird angenommen, lieferte bei der Notiz aber mitten im Satz getrennte Paare.
- `DescribeExecution` braucht `includedData: "ALL_DATA"`. `GetExecutionHistory` lässt sich nicht seitenweise abrufen.
- Japanisch in einer Gateway-Eingabe wird zu `??`. Dieses Muster übergibt nur ASCII-IDs.
- `max_files` nimmt Dokumente in Schlüsselreihenfolge, ein beschädigtes erstes Dokument wird also jedes Mal gewählt.
- Die S3 Access Points der Prüfumgebung enthielten keine Bilder oder PDFs; ein OCR-Erfolg an einem echten Access Point
  wurde daher nicht bestätigt (Auflisten, Lesen und das Löschen der temporären Kopie schon). Siehe „既知の注意点“ in
  [docs/demo-guide.md](docs/demo-guide.md).

## Referenzen

- [Amazon Textract unterstützt weitere Sprachen, darunter Japanisch, und startet in Tokio (What's New)](https://aws.amazon.com/jp/about-aws/whats-new/2026/11/textract-tokyo-zurich/)
- [AWS Step Functions as Connector Target (offiziell)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- Verwandtes Muster: [stepfunctions-agentcore-tools](../stepfunctions-agentcore-tools/)

---

<!-- playbook-reading:start -->
## Vor dem Produktivbetrieb lesen

Wie sich die nach der Bereitstellung auftretenden Einschränkungen in Entwurfsentscheidungen übersetzen, steht im [FSx for ONTAP Adoption Playbook](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook) beschrieben. Liegt derselbe Inhalt an zwei Stellen, überlebt die nicht mehr gepflegte Kopie die korrigierte.

- [Datennutzung](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/data-utilization) — Einschränkungen des Zugriffs über einen Access Point (alle Patterns)
- [Sicherheit und Governance](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/domains/security-governance) — wo sich die Entscheidungen für dieses Pattern häufen
- [Aufbauen](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/tree/main/docs/en/playbooks/04-build) — vor dem Produktivbetrieb durchgehen (alle Patterns)
<!-- playbook-reading:end -->
