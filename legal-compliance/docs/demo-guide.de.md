# Dateiserverberechtigungs-Audit — Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt einen automatisierten Audit-Workflow zur Erkennung übermäßiger Zugriffsberechtigungen auf Dateiservern. Er analysiert NTFS-ACLs und generiert Compliance-Berichte.

**Kernbotschaft**: Automatisierung von Berechtigungsaudits mit sofortiger Visualisierung von Risiken.

**Voraussichtliche Dauer**: 3–5 min

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



---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Audits für Tausende Ordner sind unrealistisch

### Section 2 (0:45–1:30)
> Workflow-Auslösung: Zielvolumen angeben und Audit starten

### Section 3 (1:30–2:30)
> ACL-Analyse: ACLs sammeln und Richtlinienverstöße erkennen

### Section 4 (2:30–3:45)
> Ergebnisüberprüfung: Verstöße und Risikostufen sofort erfassen

### Section 5 (3:45–5:00)
> Compliance-Bericht: Automatische Generierung mit priorisierten Maßnahmen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (ACL Collector) | NTFS-ACL-Metadaten-Sammlung |
| Lambda (Policy Checker) | Richtlinienverstoß-Regelabgleich |
| Lambda (Report Generator) | Audit-Bericht über Bedrock |
| Amazon Athena | SQL-Analyse der Verstoßdaten |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
