# Unfallbild-Schadensbewertung und Schadenmeldungsbericht -- Demo Guide

🌐 **Language / 言語**: [日本語](demo-guide.md) | [English](demo-guide.en.md) | [한국어](demo-guide.ko.md) | [简体中文](demo-guide.zh-CN.md) | [繁體中文](demo-guide.zh-TW.md) | [Français](demo-guide.fr.md) | Deutsch | [Español](demo-guide.es.md)

## Executive Summary

Diese Demo zeigt eine Pipeline zur fotobasierten Schadensbewertung und automatischen Schadenmeldungsberichterstellung.

**Kernbotschaft**: KI analysiert automatisch Schäden auf Unfallfotos und erstellt sofort Schadenmeldungsberichte.

**Voraussichtliche Dauer**: 3–5 min

---

## Workflow

```
Foto-Upload → Schadensbereich-Erkennung → Schweregradbewertung → Kostenschätzung → Schadenmeldungsbericht
```

---

## Storyboard (5 Sections / 3–5 min)

### Section 1 (0:00–0:45)
> Problemstellung: Manuelle fotobasierte Schadensbewertung ist zeitaufwändig

### Section 2 (0:45–1:30)
> Upload: Unfallfotos ablegen startet die Bewertung

### Section 3 (1:30–2:30)
> KI-Schadensanalyse: Automatische Erkennung von Schadensbereichen und Schweregradklassifikation

### Section 4 (2:30–3:45)
> Ergebnisse: Kostenschätzung pro Bereich und Gesamtbewertung

### Section 5 (3:45–5:00)
> Schadenmeldungsbericht: Automatisch erstellter Bericht mit Bearbeitungsempfehlungen

---

## Technical Notes

| Component | Role |
|-----------|------|
| Step Functions | Workflow-Orchestrierung |
| Lambda (Damage Detector) | KI-gestützte Schadensbereich-Erkennung |
| Lambda (Severity Assessor) | Schweregradbewertung |
| Lambda (Cost Estimator) | Reparaturkostenschätzung |
| Amazon Athena | Aggregierte Schadenhistorie-Analyse |

---

*Dieses Dokument dient als Produktionsleitfaden für technische Demonstrationsvideos.*
