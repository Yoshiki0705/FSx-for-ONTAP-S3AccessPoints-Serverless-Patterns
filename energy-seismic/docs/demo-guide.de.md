# Bohrloch-Anomalieerkennung und Compliance-Berichterstattung -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur Anomalieerkennung in Bohrlochdaten und automatischen Compliance-Berichterstellung.

**Kernbotschaft**: Anomalien in Bohrlochdaten automatisch erkennen und Compliance-Berichte sofort erstellen.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
Bohrlochdaten-Erfassung → Signalvorverarbeitung → Anomalieerkennung → Vorschriftenabgleich → Compliance-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Anomaliesuche in großen Datenmengen ist ineffizient

### Section 2 (0:45–1:30)
> Upload: Bohrloch-Logdateien ablegen startet die Analyse

### Section 3 (1:30–2:30)
> Erkennung: KI-gestützte Musteranalyse erkennt Anomalien automatisch

### Section 4 (2:30–3:45)
> Ergebnisse: Liste erkannter Anomalien und Schweregradklassifikation

### Section 5 (3:45–5:00)
> Compliance-Bericht: Vorschriftenvergleich und Korrekturempfehlungen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Signal Processor) | Bohrloch-Signalvorverarbeitung |
| Lambda (Anomaly Detector) | KI-gestützte Anomalieerkennung |
| Lambda (Compliance Checker) | Vorschriften-Compliance-Prüfung |
| Amazon Athena | Aggregierte Anomaliehistorie-Analyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
