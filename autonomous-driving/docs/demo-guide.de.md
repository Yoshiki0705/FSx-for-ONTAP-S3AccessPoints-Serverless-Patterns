# Datenvorverarbeitungs-Pipeline für autonomes Fahren -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Vorverarbeitungs- und Annotations-Pipeline für autonome Fahrsensordaten. Große Fahrdatenmengen werden automatisch klassifiziert und Trainingsdatensätze erstellt.

**Kernbotschaft**: Sensordaten automatisch vorverarbeiten und annotierte Datensätze für KI-Training erstellen.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
Sensordatenerfassung → Formatkonvertierung → Frame-Klassifikation → Annotation-Generierung → Dataset-Bericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle Vorverarbeitung großer Fahrdaten ist ein Engpass

### Section 2 (0:45–1:30)
> Upload: Sensor-Logdateien ablegen startet die Pipeline

### Section 3 (1:30–2:30)
> Vorverarbeitung und Klassifikation: Automatische Formatkonvertierung und KI-Frame-Klassifikation

### Section 4 (2:30–3:45)
> Annotationsergebnisse: Überprüfung generierter Labels und Qualitätsstatistiken

### Section 5 (3:45–5:00)
> Dataset-Bericht: Trainingsbereitschaftsbericht und Qualitätsmetriken

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Format Converter) | Sensordaten-Formatkonvertierung |
| Lambda (Frame Classifier) | KI-gestützte Frame-Klassifikation |
| Lambda (Annotation Generator) | Automatische Annotation-Generierung |
| Amazon Athena | Dataset-Statistikanalyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
