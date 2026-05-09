# Sequenzierungs-QC und Varianten-Aggregation -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur Qualitätskontrolle (QC) und Varianten-Aggregation für Genomsequenzierungsdaten.

**Kernbotschaft**: Sequenzierungsdatenqualität automatisch validieren und Varianten aggregieren, damit Forscher sich auf die Analyse konzentrieren können.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
FASTQ-Upload → QC-Validierung → Varianten-Calling → Statistische Aggregation → QC-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle QC großer Sequenzierungsdaten ist zeitaufwändig

### Section 2 (0:45–1:30)
> Upload: FASTQ-Dateien ablegen startet die Pipeline

### Section 3 (1:30–2:30)
> QC und Variantenanalyse: Automatische Qualitätsvalidierung und Varianten-Calling

### Section 4 (2:30–3:45)
> Ergebnisse: QC-Metriken und Variantenstatistiken

### Section 5 (3:45–5:00)
> QC-Bericht: Umfassender Qualitätsbericht und Empfehlungen für Folgeanalysen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (QC Validator) | Sequenzierungs-Qualitätsvalidierung |
| Lambda (Variant Caller) | Varianten-Calling |
| Lambda (Stats Aggregator) | Variantenstatistik-Aggregation |
| Amazon Athena | QC-Metrik-Analyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
