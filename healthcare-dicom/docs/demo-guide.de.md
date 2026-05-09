# DICOM-Anonymisierungs-Workflow -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine automatische Anonymisierungs-Pipeline für DICOM-Dateien. Patientenidentifikationsdaten werden entfernt, um einen sicheren Forschungsdatenaustausch zu ermöglichen.

**Kernbotschaft**: Patientendaten automatisch aus DICOM-Dateien entfernen für konformen und sicheren Datenaustausch.

**Voraussichtliche Dauer**: 3–5 min

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
