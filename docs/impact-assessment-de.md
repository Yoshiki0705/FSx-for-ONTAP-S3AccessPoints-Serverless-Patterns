# Leitfaden zur Bewertung der Auswirkungen auf bestehende Umgebungen

🌐 **Language / 言語**: [日本語](impact-assessment.md) | [English](impact-assessment-en.md) | [한국어](impact-assessment-ko.md) | [简体中文](impact-assessment-zh-CN.md) | [繁體中文](impact-assessment-zh-TW.md) | [Français](impact-assessment-fr.md) | [Deutsch](impact-assessment-de.md) | [Español](impact-assessment-es.md)

## Überblick

Dieses Dokument bewertet die Auswirkungen auf bestehende Umgebungen bei der Aktivierung von Funktionen jeder Phase und bietet sichere Aktivierungsverfahren und Rollback-Methoden.

> **Umfang**: Phase 1–5 (wird bei Hinzufügen neuer Phasen aktualisiert)

Designprinzipien:
- **Phase 1 (UC1–UC5)**: Unabhängige CloudFormation-Stacks. Nur ENI-Erstellung
- **Phase 2 (UC6–UC14)**: Unabhängige Stacks + Cross-Region API-Aufrufe
- **Phase 3 (Übergreifende Verbesserungen)**: Erweiterungen bestehender UCs. Opt-in (standardmäßig deaktiviert)
- **Phase 4 (Produktions-SageMaker, Multi-Account, Event-Driven)**: UC9-Erweiterungen + neue Templates. Opt-in
- **Phase 5 (Serverless Inference, Kosten, CI/CD, Multi-Region)**: Opt-in (standardmäßig deaktiviert)

---

## Phase 1–2: Basis- und erweiterte UCs

| Parameter | Standard | Auswirkung |
|-----------|----------|-----------|
| EnableS3GatewayEndpoint | "true" | ⚠️ Konflikt mit bestehendem S3 Gateway EP |
| EnableVpcEndpoints | "false" | Interface VPC Endpoints erstellt |
| CrossRegion | "us-east-1" | Cross-Region API-Aufrufe (Latenz 50–200ms) |
| MapConcurrency | 10 | Beeinflusst Lambda-Parallelitätsquote |

## Phase 3: Übergreifende Verbesserungen

| Parameter | Standard | Auswirkung |
|-----------|----------|-----------|
| EnableStreamingMode | "false" | Neue UC11-Ressourcen (Polling nicht betroffen) |
| EnableSageMakerTransform | "false" | ⚠️ SageMaker-Pfad zum UC9-Workflow hinzugefügt |
| EnableXRayTracing | "true" | ⚠️ X-Ray Trace-Übertragung beginnt |

## Phase 4: Produktionserweiterungen

| Parameter | Standard | Auswirkung |
|-----------|----------|-----------|
| EnableRealtimeEndpoint | "false" | ⚠️ Dauerkosten (~$166/Monat) |
| EnableDynamoDBTokenStore | "false" | Neue DynamoDB-Tabelle |

## Phase 5: Serverless Inference, Kosten, CI/CD, Multi-Region

| Parameter | Standard | Auswirkung |
|-----------|----------|-----------|
| InferenceType | "none" | "serverless" ändert Routing |
| EnableScheduledScaling | "false" | ⚠️ Ändert Scaling bestehender Endpoints |
| EnableAutoStop | "false" | ⚠️ Stoppt inaktive Endpoints |
| EnableMultiRegion | "false" | ⚠️ **Irreversibel** — DynamoDB Global Table |

---

## Empfohlene Aktivierungsreihenfolge

| Reihenfolge | Funktion | Phase | Risiko |
|-------------|----------|-------|--------|
| 1 | UC1-Bereitstellung | 1 | Niedrig |
| 2 | Observability | 3 | Niedrig |
| 3 | CI/CD | 5 | Keines |
| 4–6 | Streaming / SageMaker / Serverless | 3–5 | Niedrig |
| 7–8 | Real-time / Scaling | 4–5 | Mittel ⚠️ |
| 9 | Multi-Region | 5 | Hoch ⚠️ **Irreversibel** |

---

*Dieses Dokument ist der Leitfaden zur Bewertung der Auswirkungen auf bestehende Umgebungen für FSxN S3AP Serverless Patterns.*
