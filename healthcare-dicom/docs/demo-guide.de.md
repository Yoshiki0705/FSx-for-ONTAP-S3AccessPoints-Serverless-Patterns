# DICOM-Anonymisierungs-Workflow -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine automatische Anonymisierungs-Pipeline für DICOM-Dateien. Patientenidentifikationsdaten werden entfernt, um einen sicheren Forschungsdatenaustausch zu ermöglichen.

**Kernbotschaft**: Patientendaten automatisch aus DICOM-Dateien entfernen für konformen und sicheren Datenaustausch.

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

```
DICOM-Upload → Metadaten-Extraktion → PHI-Erkennung → Anonymisierung → Validierungsbericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Forschungsdatenaustausch erfordert Einhaltung der Patientenschutzvorschriften

### Section 2 (0:45–1:30)
> Upload: DICOM-Dateien ablegen startet automatische Verarbeitung

### Section 3 (1:30–2:30)
> PHI-Erkennung und Anonymisierung: KI-gestützte Erkennung und automatische Maskierung

### Section 4 (2:30–3:45)
> Ergebnisse: Überprüfung anonymisierter Dateien und Verarbeitungsstatistiken

### Section 5 (3:45–5:00)
> Validierungsbericht: Compliance-Bericht erstellen und Datenaustausch genehmigen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (DICOM Parser) | DICOM-Metadaten-Extraktion |
| Lambda (PHI Detector) | KI-gestützte Erkennung personenbezogener Daten |
| Lambda (Anonymizer) | Anonymisierungsverarbeitung |
| Amazon Athena | Aggregierte Ergebnisanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
