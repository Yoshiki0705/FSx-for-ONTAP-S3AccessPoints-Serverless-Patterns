# IoT-Sensor-Anomalieerkennung und Qualitätsprüfung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt einen Workflow zur automatischen Erkennung von Anomalien in IoT-Sensordaten der Fertigungslinie und Generierung von Qualitätsberichten.

**Kernbotschaft**: Automatische Erkennung von Anomaliemustern in Sensordaten für frühzeitige Qualitätsproblem-Erkennung.

**Voraussichtliche Dauer**: 3-5 min

---

## Ausgabeziel: FSxN S3 Access Point (Pattern A)

Dieser UC gehört zum **Pattern A: Native S3AP Output**
(siehe `docs/output-destination-patterns.md`).

**Design**: Alle AI/ML-Artefakte werden über den FSxN S3 Access Point auf
**dasselbe FSx ONTAP Volume** wie die Quelldaten zurückgeschrieben. Kein separater
Standard-S3-Bucket wird erstellt ("no data movement"-Pattern).

**CloudFormation-Parameter**:
- `S3AccessPointAlias`: Eingabe-S3-AP-Alias
- `S3AccessPointOutputAlias`: Ausgabe-S3-AP-Alias (kann identisch mit Eingabe sein)

AWS-Spezifikationsbeschränkungen und Workarounds siehe
[README.de.md — AWS-Spezifikationsbeschränkungen](../../README.de.md#aws-spezifikationsbeschränkungen-und-workarounds).

---
## Workflow

```
Sensordaten (CSV/Parquet) -> Vorverarbeitung -> Anomalieerkennung / Statistische Analyse -> Qualitätsbericht (KI)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Problemstellung: Schwellenwert-Alarme verpassen echte Anomalien

### Section 2 (0:45-1:30)
> Datenaufnahme: Datenakkumulation startet automatisch Analyse

### Section 3 (1:30-2:30)
> Erkennung: Statistische Methoden erkennen nur signifikante Anomalien

### Section 4 (2:30-3:45)
> Inspektion: Problembereiche auf Linien-/Prozessebene identifizieren

### Section 5 (3:45-5:00)
> Bericht: KI präsentiert Ursachenkandidaten und Gegenmaßnahmen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Data Preprocessor) | Sensordaten-Normalisierung |
| Lambda (Anomaly Detector) | Statistische Anomalieerkennung |
| Lambda (Report Generator) | Qualitätsbericht über Bedrock |
| Amazon Athena | Aggregierte Anomalieanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
