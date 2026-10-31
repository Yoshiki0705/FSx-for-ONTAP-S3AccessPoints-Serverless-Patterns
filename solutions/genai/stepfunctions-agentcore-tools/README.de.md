# Step Functions × AgentCore Gateway — Workflows als KI-Agenten-Tools

🌐 **Language / 言語**: [日本語](README.md) | [English](README.en.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [Français](README.fr.md) | Deutsch | [Español](README.es.md)

Ein Beispiel, das einen Standard-Step-Functions-Workflow (Ermitteln → Verarbeiten →
Bericht) über Dateien auf FSx for ONTAP S3 Access Points als KI-Agenten-Tools
bereitstellt — über den integrierten Step-Functions-Connector von Amazon Bedrock
AgentCore Gateway.

Der Agent entscheidet, wann der Workflow läuft und welche Eingabe er übergibt; die
State Machine garantiert die Reihenfolge der Schritte. Die festgelegte Abfolge bleibt
im Workflow, die Startentscheidung liegt beim Agenten.

## Anwendungsfälle

- Einen vorhandenen Step-Functions-Workflow vom Agenten aus starten, ohne die State Machine zu ändern
- Schritte und Freigaben im Workflow festhalten, nur die Ausführungsentscheidung an den Agenten delegieren
- Den Agenten über die Ausführungshistorie prüfen lassen, wie weit eine Ausführung fortgeschritten ist

## Architektur

```
KI-Agent ──MCP──▶ AgentCore Gateway (Step-Functions-Connector)
                    │ GatewayServiceRole → states:StartExecution usw.
                    ▼
           Standard StateMachine (Discover→Choice→Map→Report)
                    │
       Discovery / Processing / Report Lambda
                    │
              S3 Access Point (FSx for ONTAP / im DemoMode normales S3)
```

Details in [docs/architecture.md](docs/architecture.md).

## Bereitgestellte Tools

| Tool | Eingabe | Zweck |
|---|---|---|
| `workflow___StartExecution` | `input` (JSON-String) | Workflow starten |
| `workflow___ListExecutions` | `statusFilter` (optional) | Ausführungen auflisten (nur Standard) |
| `workflow___DescribeStateMachine` | `includedData` (optional) | Metadaten/Definition der State Machine |
| `workflow___DescribeExecution` | `executionArn`, `includedData` | Status und Ergebnis prüfen |
| `workflow___GetExecutionHistory` | `executionArn` | Schritt-Historie |

Der angeheftete State-Machine-ARN erscheint nicht im Tool und der Agent kann ihn nicht ändern.

## Parameter

| Parameter | Beschreibung | Standard |
|---|---|---|
| `S3AccessPointAlias` | S3-AP-Alias des FSx-for-ONTAP-Volumes (im DemoMode ein normaler Bucket-Name) | (erforderlich) |
| `DemoMode` | `true` läuft ohne FSx for ONTAP (normaler S3-Bucket) | `false` |
| `FilePrefix` | Zu durchsuchendes Präfix | `input/` |
| `BedrockModelId` | Zusammenfassungsmodell / Inferenzprofil-ID ([docs/bedrock-inference-profiles.md](../../../docs/bedrock-inference-profiles.md)) | `apac.amazon.nova-pro-v1:0` |
| `MaxFilesPerExecution` | Max. Dateien pro Ausführung | `100` |
| `NotificationEmail` | SNS-Benachrichtigungsziel (leer = überspringen) | `""` |
| `GatewayName` | Gateway-Name (vom Deploy-Skript verwendet) | `sfn-agentcore-tools-gateway` |

## Bereitstellung

Das Gateway und das Connector-Ziel sind erstklassige CloudFormation-Ressourcen
(`AWS::BedrockAgentCore::Gateway` / `GatewayTarget`), daher steckt das ganze Muster
in einer deklarativen Vorlage. Das Deploy-Skript ist ein `sam build` + `sam deploy`
Wrapper, der danach `tools/list` prüft.

```bash
# DemoMode (ohne FSx for ONTAP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias my-demo-bucket --demo-mode --stack-name sfn-agentcore-tools-demo

# Produktion (S3 AP)
./scripts/deploy-stepfunctions-agentcore.sh \
  --s3ap-alias <your-ap>-ext-s3alias --stack-name sfn-agentcore-tools

# Aufräumen
./scripts/deploy-stepfunctions-agentcore.sh --cleanup --stack-name sfn-agentcore-tools
```

Konversationsbeispiele und Verifizierungsschritte in [docs/demo-guide.md](docs/demo-guide.md).

## Human-Review-Schwellen

Die Processing-Lambda bewertet die Zusammenfassungs-Konfidenz mit `shared/human_review.py`.

| Konfidenz | Entscheidung |
|---|---|
| `>= 0.85` (Standard `HUMAN_REVIEW_AUTO_APPROVE_THRESHOLD`) | AUTO_APPROVE |
| `>= 0.30` (Standard `HUMAN_REVIEW_REJECT_THRESHOLD`) und `< 0.85` | HUMAN_REVIEW |
| `< 0.30` | REJECT |

Die Schwellen sind über Umgebungsvariablen überschreibbar. Die Entscheidung wird im
Ergebnis geführt; dieses Muster handelt nicht automatisch danach.

## Datenklassifizierung

Die Report-Lambda kennzeichnet die Ausgabe mit `data_classification` aus
`shared/data_classification.py` (Standard `INTERNAL`, änderbar über `DATA_CLASSIFICATION`).

## Governance Note

- Der Agent entscheidet nur über den Ausführungszeitpunkt und prüft den Status.
  Reihenfolge, Verzweigungen und Freigaben garantiert die State Machine; der Agent kann
  sie weder überspringen noch umordnen.
- Der angeheftete ARN wird nicht offengelegt, der Agent kann keine andere State Machine starten.
- KI-Zusammenfassung/-Klassifizierung ist ein **Unterstützungssignal**, keine
  Endentscheidung. Konfidenz unter der Schwelle wird zur menschlichen Prüfung geleitet.
- Task-Token-Operationen (`SendTaskSuccess` usw.) werden hier nicht offengelegt, da IAM
  sie nicht auf bestimmte Ausführungen begrenzen kann.
- Dies ist Governance-Leitlinie, kein Rechts- oder Compliance-Rat.

## Tests

```bash
python3 -m pytest solutions/genai/stepfunctions-agentcore-tools/tests/ -v
```

## Bekannte Stolpersteine

Die Same-Region-Einschränkung, ein Pin pro Operation, das `?`-Mojibake bei japanischen
Eingaben und der `\uXXXX`-Workaround sowie die Cedar-`input`-Grenze sind in
[docs/demo-guide.md](docs/demo-guide.md#既知の注意点) zusammengefasst.

## Referenzen

- [AWS Step Functions as Connector Target (offiziell)](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-step-functions.html)
- [AWS Step Functions workflows now available as AI agent tools (What's New)](https://aws.amazon.com/about-aws/whats-new/2026/10/step-functions-workflows-ai-agent-tools/)
