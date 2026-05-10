# VFX-Rendering-Qualitätsprüfung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Qualitätsprüfungs-Pipeline für VFX-Rendering-Ausgaben. Automatische Frame-Verifizierung ermöglicht frühzeitige Erkennung von Artefakten.

**Kernbotschaft**: Automatische Verifizierung großer Mengen gerenderter Frames mit sofortiger Qualitätsproblem-Erkennung.

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
Render-Ausgabe (EXR/PNG) -> Frame-Analyse / Metadaten-Extraktion -> Qualitätsbewertung -> QC-Bericht (pro Shot)
```

---

## Storyboard (5 Sections / 3-5 min)

### Section 1 (0:00-0:45)
> Problemstellung: Visuelle Inspektion Tausender Frames ist unrealistisch

### Section 2 (0:45-1:30)
> Pipeline-Auslösung: Render-Abschluss startet automatisch QC

### Section 3 (1:30-2:30)
> Frame-Analyse: Pixel-Statistiken bewerten Frame-Qualität quantitativ

### Section 4 (2:30-3:45)
> Qualitätsbewertung: Automatische Klassifizierung problematischer Frames

### Section 5 (3:45-5:00)
> QC-Bericht: Sofortige Unterstützung für Re-Render-Entscheidungen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Frame Analyzer) | Frame-Metadaten/Pixel-Statistik-Extraktion |
| Lambda (Quality Checker) | Statistische Qualitätsbewertung |
| Lambda (Report Generator) | QC-Bericht über Bedrock |
| Amazon Athena | Aggregierte Frame-Statistik-Analyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
